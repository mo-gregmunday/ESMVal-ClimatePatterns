"""Diagnostic script to generate ocean and atmospheric parameters.

Description
-----------
Generates and saves energy-balance-model specific ocean and
atmospheric parameters from CMIP6 models. This diagnostic needs
preprocessed mean annual cubes, with no gridding requirements.
Default re-grid specification exists to decrease CPU-load and run-time.

Kappa and atmospheric parameter calculation mathematics kindly provided by
Dr. Chris Huntingford, CEH. (Huntingford & Cox, 2000)

Author
------
Gregory Munday (Met Office, UK)


Configuration options in recipe
-------------------------------
include_params: bool, optional (default: off)
    options: on, off
    def: if 'on', uses parameters supplied in 'params.json' to significantly
         reduce CPU load and run-time. Must be copied from output params.dat
         file, in same format.
parallelise: bool, optional (default: off)
    options: on, off
    def: parallelises code to run N models at once
parallel_threads: int, optional (default: null)
    options: any int, up to the amount of CPU cores accessible by user
    def: number of threads/cores to parallelise over. If 'parallelise: on' and
         'parallel_threads': null, diagnostic will automatically parallelise
         over N-1 accessible threads
"""

import json
import logging
import os
from pathlib import Path

import iris
import iris.coord_categorisation
import iris.cube
import numpy as np
import sub_functions as sf
from plotting import ebm_plots
from scipy import stats
from scipy.sparse.linalg import spsolve

from esmvaltool.diag_scripts.shared import run_diagnostic

logger = logging.getLogger(Path(__file__).stem)
params_file = os.path.join(os.path.dirname(__file__), 'params.json')


def compute_diagnostic(filename):
    """Compute an example diagnostic."""

    logger.debug("Loading %s", filename)
    cube = iris.load_cube(filename)

    logger.debug("Running example computation")
    cube = iris.util.squeeze(cube)
    return cube


def net_flux_calculation(toa_list):

    for cube in toa_list:
        if cube.var_name == "rsdt":
            rsdt = cube
        if cube.var_name == "rlut":
            rlut = cube
        if cube.var_name == "rsut":
            rsut = cube

    toa_net = rsdt - rlut - rsut
    toa_net.rename("Net Downward Radiative Flux At Top of Atmosphere Model")
    toa_net.var_name = "rtmt"

    return toa_net


def ocean_fraction_calc(sftlf):
    """Calculates land and ocean fractions for weights and EBM."""
    sftlf.coord("latitude").coord_system = iris.coord_systems.GeogCS(6371229.0)
    sftlf.coord("longitude").coord_system = iris.coord_systems.GeogCS(
        6371229.0)
    sftof = sftlf.copy()
    sftof.data = 100.0 - sftlf.data

    ocean_frac = sftof / 100
    land_frac = sftlf / 100

    # ocean fraction calculation
    weights_l = iris.analysis.cartography.area_weights(sftlf)
    weights_o = iris.analysis.cartography.area_weights(sftof)
    lf_area = sftlf.collapsed(
        ['latitude', 'longitude'], iris.analysis.SUM, weights=weights_l) / 1e12
    of_area = sftof.collapsed(
        ['latitude', 'longitude'], iris.analysis.SUM, weights=weights_o) / 1e12

    of = of_area.data / (of_area.data + lf_area.data)

    logger.info("Ocean fraction = ", of)

    return ocean_frac, land_frac, of


def kappa_parameter(f, toa_delta, tas_delta_ocean):

    rms = 10000.0
    kappa = -9999.9
    for i_kappa in range(0, 150):
        kappa_test = 20.0 + 20.0 * float(i_kappa)

        temp_ocean_top = kappa_calc(f, toa_delta, kappa_test)
        rms_local = np.sqrt(
            np.mean((temp_ocean_top - tas_delta_ocean)**2) /
            tas_delta_ocean.shape[0])
        if (rms_local <= rms):
            rms = rms_local
            kappa = kappa_test

    return kappa


def kappa_calc(f, toa_delta, kappa):

    # Set volumetric heat capacity for salt water
    cp = 4.04E6  # (J/K/m3)
    nyr = toa_delta.shape[0]

    n_pde = 20
    dt = (1.0 / float(n_pde)
          ) * 60.0 * 60.0 * 24.0 * 365.0  # Model timestep (seconds)
    temp_ocean_top = np.zeros(nyr)  # Array holds oceanic warming (K)
    # Set number of vertical layers and ocean depth
    n_vert = 254
    depth = 5000.0  # (metres)
    dz = depth / float(n_vert)  # (metres)

    s = (kappa / cp) * (dt / (dz * dz))

    # Now do the pde solving. First set up the arrays (and zero'd)
    t_ocean_old = np.zeros(n_vert + 1)
    t_ocean_new = np.zeros(n_vert + 1)

    C = np.zeros([n_vert + 1, n_vert + 1])
    D = np.zeros([n_vert + 1, n_vert + 1])
    E = np.zeros(n_vert + 1)

    # Conservation check for end of run - add up energy in.
    q_energy = 0.0

    # Now start loop over the different years.
    for j in range(0, nyr):
        factor1 = -toa_delta[j] / (kappa * f)
        factor2 = 0.0

        for k in range(0, n_pde):
            _ = j * n_pde + k

            # First set t_old as t_new ready for next iteration
            t_ocean_old = t_ocean_new

            # Sort out the top points, bottom points and then all for C
            C[0, 0] = s * (1.0 + dz * factor2) + 1
            C[0, 1] = -s
            C[n_vert, n_vert - 1] = -s
            C[n_vert, n_vert] = (1.0 + s)
            for m in range(1, n_vert):
                C[m, m - 1] = -s / 2.0
                C[m, m + 1] = -s / 2.0
                C[m, m] = 1.0 + s

            # Sort out the top points, bottom points and then all for D
            D[0, 0] = -s * (1.0 + dz * factor2) + 1
            D[0, 1] = s
            D[n_vert, n_vert] = (1.0 - s)
            D[n_vert, n_vert - 1] = s
            for m in range(1, n_vert):
                D[m, m - 1] = s / 2.0
                D[m, m + 1] = s / 2.0
                D[m, m] = 1.0 - s

            E[0] = -(kappa / cp) * (dt / dz) * (factor1 + factor1)

            # Now solve for U_{j+1}.
            # First put bits in to tri-diagonal things for "sparse.spdiags".
            C_sub = np.zeros(n_vert + 1)
            C_main = np.zeros(n_vert + 1)
            C_super = np.zeros(n_vert + 1)
            for m in range(0, n_vert + 1):
                C_main[m] = C[m, m]
            for m in range(0, n_vert):
                C_sub[m] = C[m + 1, m]
                C_super[m] = C[m, m + 1]

            # Now calculate the right-hand side (called b_rhs)
            e_mat = np.mat(E).transpose()
            t_ocean_old_mat = np.mat(t_ocean_old).transpose()
            b_rhs = np.dot(D, t_ocean_old_mat) + e_mat
            b_rhs = np.ravel(b_rhs)

            # Now perform the calculation to update the oceanic temperatures
            t_ocean_new = spsolve(C, b_rhs)

            # Update the cumulative heat entering ocean,
            # and also save to top ocean temperature
            q_energy = q_energy + dt * kappa * (-factor1 -
                                                (t_ocean_new[0] * factor2))

        temp_ocean_top[j] = t_ocean_new[0]

    # Check conservation of energy at end of run.
    # Compare against total heat in the final profile.
    q_energy_derived = 0.0
    for i in range(1, n_vert + 1):
        q_energy_derived = q_energy_derived + cp * 0.5 * (
            t_ocean_new[i] + t_ocean_new[i - 1]) * dz

    conserved = 100.0 * (q_energy_derived / q_energy)
    logger.info("Heat conservation check (%) = ", round(conserved, 2))

    return temp_ocean_top


def anomalies_calc(toa_cube, tas_cube, ocean_frac, land_frac):

    # TOA area weighting
    toa_delta_init = sf.area_avg(toa_cube, return_cube=False)
    toa_delta_land_init = sf.area_avg_landsea(toa_cube,
                                              ocean_frac,
                                              land_frac,
                                              land=True,
                                              return_cube=False)
    toa_delta_ocean_init = sf.area_avg_landsea(toa_cube,
                                               ocean_frac,
                                               land_frac,
                                               land=False,
                                               return_cube=False)

    # tas area weighting
    tas_delta_init = sf.area_avg(tas_cube, return_cube=False)
    tas_delta_land_init = sf.area_avg_landsea(tas_cube,
                                              ocean_frac,
                                              land_frac,
                                              land=True,
                                              return_cube=False)
    tas_delta_ocean_init = sf.area_avg_landsea(tas_cube,
                                               ocean_frac,
                                               land_frac,
                                               land=False,
                                               return_cube=False)

    init_list = [
        toa_delta_init, toa_delta_land_init, toa_delta_ocean_init,
        tas_delta_init, tas_delta_land_init, tas_delta_ocean_init
    ]

    # calculating anomalies
    delta_list = [x - np.mean(x[0:40]) for x in init_list]
    (toa_delta, toa_delta_land, toa_delta_ocean, tas_delta, tas_delta_land,
     tas_delta_ocean) = delta_list

    return (toa_delta, toa_delta_land, toa_delta_ocean, tas_delta,
            tas_delta_land, tas_delta_ocean)


def atmos_params_calc(rf, toa_delta_land, toa_delta_ocean, tas_delta_land,
                      tas_delta_ocean):

    # calculating lambda_ocean
    lambda_o_init = (rf - toa_delta_ocean) / tas_delta_ocean
    lambda_o = np.mean(lambda_o_init[-90:])

    # calculating lambda_land
    lambda_l_init = (rf - toa_delta_land) / tas_delta_land
    lambda_l = np.mean(lambda_l_init[-90:])

    # calculating nu-ratio
    nu_ratio_init = tas_delta_land / tas_delta_ocean
    nu_ratio = np.mean(nu_ratio_init[-90:])

    return lambda_o, lambda_l, nu_ratio


def save_params(model, f_ocean, kappa, lambda_o, lambda_l, nu_ratio):

    # saving atmospheric parameters
    dict = {
        str(model): {
            "model": str(model),
            "kappa_o": kappa,
            "lambda_l": lambda_l,
            "lambda_o": lambda_o,
            "mu": nu_ratio,
            "f_ocean": f_ocean,
        }
    }

    return dict


def create_regression_plot(tas_cube, rtmt_cube, tas_4x_cube, rtmt_4x_cube):

    # global average and anomalies of all cubes
    var_list = [tas_cube, rtmt_cube, tas_4x_cube, rtmt_4x_cube]
    avg_list = [sf.area_avg(x, return_cube=True) for x in var_list]
    avg_list = [x.data - np.mean(x.data[0:40]) for x in avg_list]

    # linear regression
    reg = stats.linregress(avg_list[2].data, avg_list[3].data)

    # calculate climate sensitivity 'Lambda'
    lambda_c = reg.slope
    logger.info("Lambda: ", lambda_c)

    # calculate forcing, using (2) from Sellar, A. et al. (2020)
    forcing = avg_list[1].data + (-lambda_c * avg_list[0].data)
    yrs = (1850 + np.arange(forcing.shape[0])).astype('float')

    return reg, avg_list, yrs, forcing, lambda_c


def return_forcing_cube(forcing, yrs, work_path):

    f_array = np.array([forcing, yrs])

    f_cube = iris.cube.Cube(f_array,
                            standard_name='toa_adjusted_radiative_forcing',
                            units='W m-2',
                            var_name='erf')

    iris.save(f_cube, work_path + "effective_forcing.nc")


def ebm_check(rad_forcing, of, kappa, lambda_o, lambda_l, nu_ratio, tas_delta):

    # runs the EBM tas prediction, with derived forcing
    temp_ocean_top = sf.kappa_calc_predict(rad_forcing, of, kappa, lambda_o,
                                           lambda_l, nu_ratio)
    temp_global = (of + (1 - of) * nu_ratio) * temp_ocean_top

    return temp_global, tas_delta


def parallel_models(model):

    with run_diagnostic() as cfg:
        input_data = cfg["input_data"].values()
        params = cfg["include_params"]
        work_path = cfg["work_dir"] + "/"
        plot_path = cfg["plot_dir"] + "/"

    toa_list = iris.load([])
    toa_4x_list = iris.load([])

    for dataset in input_data:
        if dataset['dataset'] == model:
            input_file = dataset["filename"]

            # preparing single cube
            cube_initial = compute_diagnostic(input_file)

            if dataset["exp"] != "abrupt-4xCO2":
                if cube_initial.var_name == "sftlf":
                    sftlf_cube = cube_initial
                if cube_initial.var_name == "tas":
                    tas_cube = cube_initial
                if (not cube_initial.var_name == "tas"
                        or cube_initial.var_name == "sftlf"):
                    toa_list.append(cube_initial)
            if dataset["exp"] == "abrupt-4xCO2":
                if cube_initial.var_name == "tas":
                    tas_4x_cube = cube_initial
                if not cube_initial.var_name == "tas":
                    toa_4x_list.append(cube_initial)

    # calculating global, land and ocean TOA fluxes
    rtmt_cube = net_flux_calculation(toa_list)
    rtmt_4x_cube = net_flux_calculation(toa_4x_list)

    # calculating ocean fraction
    ocean_frac, land_frac, of = ocean_fraction_calc(sftlf_cube)

    # calculating TOA averages, subtracting mean of first 4 decades
    (toa_delta, toa_delta_land, toa_delta_ocean, tas_delta, tas_delta_land,
     tas_delta_ocean) = anomalies_calc(rtmt_cube, tas_cube, ocean_frac,
                                       land_frac)

    # calculating EBM parameter, Kappa
    if params is True:
        param_list = []
        for line in open(params_file, "r"):
            param_list.append(json.loads(line))

        for i in range(len(param_list[0])):
            sub_list = list(param_list[0][i].values())
            if sub_list[0]['model'] == model:
                kappa = sub_list[0]['kappa_o']
    else:
        kappa = kappa_parameter(of, toa_delta, tas_delta_ocean)

    reg, avg_list, yrs, rad_forcing, lambda_c = create_regression_plot(
        tas_cube, rtmt_cube, tas_4x_cube, rtmt_4x_cube)

    if params is True:
        param_list = []
        for line in open(params_file, "r"):
            param_list.append(json.loads(line))

        for i in range(len(param_list[0])):
            sub_list = list(param_list[0][i].values())
            if sub_list[0]['model'] == model:
                lambda_o = sub_list[0]['lambda_o']
                lambda_l = sub_list[0]['lambda_l']
                nu_ratio = sub_list[0]['mu']
    else:
        lambda_o, lambda_l, nu_ratio = atmos_params_calc(
            rad_forcing, toa_delta_land, toa_delta_ocean, tas_delta_land,
            tas_delta_ocean)

    temp_global, t_delta = ebm_check(rad_forcing, of, kappa, lambda_o,
                                     lambda_l, nu_ratio, tas_delta)

    model_work_dir, model_plot_dir = sf.make_model_dirs(
        cube_initial, work_path, plot_path)

    # saving forcing cube
    return_forcing_cube(rad_forcing, yrs, model_work_dir)

    # plotting
    ebm_plots(reg, avg_list, yrs, rad_forcing, lambda_c, temp_global, t_delta,
              model_plot_dir)

    return save_params(model, of, kappa, lambda_o, lambda_l, nu_ratio)


def main(cfg):

    # gets a description of the preprocessed data that we will use as input.
    input_data = cfg["input_data"].values()
    parallelise = cfg["parallelise"]
    threads = cfg["parallel_threads"]
    work_path = cfg["work_dir"] + "/"

    models = []

    for x in input_data:
        print(x)
        model = x['dataset']
        if model not in models:
            models.append(model)

    if parallelise is True:
        model_data = sf.parallelise(parallel_models, threads)(models)
    else:
        for model in models:
            model_data.append(parallel_models(model))

    file = open(work_path + "params.dat", 'a')
    file.write(json.dumps(model_data))
    file.close()


if __name__ == "__main__":

    with run_diagnostic() as config:
        main(config)
