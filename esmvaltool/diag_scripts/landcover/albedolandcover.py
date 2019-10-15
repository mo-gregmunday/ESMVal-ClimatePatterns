"""
Look at this module for guidance how to write your own.

Read the README_PERSONAL_DIAGNOSTIC file associated with this example;

Module for personal diagnostics (example).
Internal imports from exmvaltool work e.g.:

from esmvaltool.preprocessor import regrid
from esmvaltool.diag_scripts.shared.supermeans import get_supermean

Pipe output through logger;

Please consult the documentation for help with esmvaltool's functionalities
and best coding practices.


"""


import copy
import glob
import itertools as it
import logging
import os
import sys
import warnings

from cartopy import crs # This line causes a segmentation fault in prospector
import cartopy.feature as cfeature
import iris
import matplotlib.pyplot as plt
import numpy as np
# specific imports for this diagnostic
from sklearn import linear_model

from esmvaltool.diag_scripts.shared import group_metadata, run_diagnostic
from esmvaltool.diag_scripts.shared._base import get_plot_filename


# This part sends debug statements to stdout
logger = logging.getLogger(os.path.basename(__file__))
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


# This suppresses a warning. Check if this is legitimate.
iris.FUTURE.netcdf_promote = True

warnings.filterwarnings("ignore", category=FutureWarning)


def _add_masks_albedolandcover(model_data, this_models_xxfracs, dia_cfg, cfg):

    total_frac = sum([model_data[key] for key in this_models_xxfracs])

    # Mask out regions where total_frac is too low
    fracmask = (total_frac.data.data < dia_cfg['threshold_sumpred'])

    # Start masking operations. Remember that a True means masked out.
    basemask = model_data['snc'].data.mask

    # Mask out regions where there is little snow
    snowmask = model_data['snc'].data.data < dia_cfg['thres_fsnow']
    snowfreemask = ~snowmask

    # Update the masks
    snowmask |= basemask
    snowmask |= fracmask
    snowfreemask |= basemask
    snowfreemask |= fracmask

    # Plotting intermezzo for the masks
    masksavedir = os.path.join(cfg['plot_dir'], 'masks/')
    if not os.path.exists(masksavedir):
        os.mkdir(masksavedir)

    template_time = model_data['snc'].coord('time')
    month_string = template_time.units.num2date(
        template_time.points)[0].strftime('%b')
    masksavename = '{0}-{1}'.format(
        month_string, model_data['snc'].attributes['model_id'])
    plt.imshow(total_frac.data[::-1])
    plt.savefig(masksavedir + masksavename + 'total_frac.'
                + cfg['output_file_type'])
    plt.imshow(fracmask[::-1])
    plt.savefig(masksavedir + masksavename + 'fracmask.'
                + cfg['output_file_type'])
    plt.imshow(snowmask[::-1])
    plt.title('snowmask')
    plt.savefig(masksavedir + masksavename + 'snowmask.'
                + cfg['output_file_type'])
    plt.imshow(snowfreemask[::-1])
    plt.title('snowfreemask')
    plt.savefig(masksavedir + masksavename + 'snowfreemask.'
                + cfg['output_file_type'])

    # TODO also add the snowmask
    mymask = copy.deepcopy(snowmask)

    for varkey in model_data:
        model_data[varkey].data.mask = mymask

    return model_data


def _get_reconstructed_albedos(model_data, dia_cfg):
    alb_lc = np.zeros((3, ) + model_data['alb'].shape)
    alb_lc[...] = np.nan

    # Now loop over these arrays and do the math
    for (indices, maskbool) in np.ndenumerate(model_data['alb'].data.mask):
        if not maskbool: # Only if not masked we need to check neighbourhood
            i, j = indices
            # TODO change back
            #assert(model_data['snc'].data[i, j] < dia_cfg['thres_fsnow'])
            # Now check the local neighbourhood.
            # Create indices
            # Create the neighbourhood as bbox
            islice = slice(int(i - (dia_cfg['lonsize_BB'] - 1) / 2),
                           int(i + (dia_cfg['lonsize_BB'] - 1) / 2 + 1))
            jslice = slice(int(j - (dia_cfg['latsize_BB'] - 1) / 2),
                           int(j + (dia_cfg['latsize_BB'] - 1) / 2 + 1))
            bbox_mask = model_data['alb'].data.mask[islice, jslice]

            # Check if there are enough valid data points
            # in the neighbourhood bbox
            if np.sum((~bbox_mask).astype(int)) > dia_cfg['minnum_gc_bb']:
                lc_logical = np.full((3, ), True)
                lc_classes = [dia_cfg['lc1_class'], dia_cfg['lc2_class'],
                              dia_cfg['lc3_class']]
                lc_data = []
                # Loop over lc_classes
                for i_0 in range(3):
                    current_class = lc_classes[i_0]
                    # First flatten the array
                    lc_flattened = {}
                    for varkey in current_class:
                        lc_flattened[varkey] = model_data[varkey].data[
                            islice, jslice].compressed()
                    lc_sum = sum([lc_flattened[varkey]
                                  for varkey in current_class])
                    # Now check thresholds
                    if (np.var(lc_sum) > 0. and
                            len(lc_sum) >= dia_cfg['mingc']):
                        lc_data.append(lc_sum)
                        lc_logical[i_0] = True
                    else:
                        logger.info("Variance zero or not enough\
                               valid data for this landcover class")
                        lc_logical[i_0] = False
                # Now the multiple lin reg part
                x_0 = np.stack(lc_data)
                x_0 = x_0.swapaxes(0, 1)
                # Same mask, so shape is fine
                y_0 = model_data['alb'].data[islice, jslice].compressed()

                # Check that the system is not over_parameterised
                if len(y_0) > np.sum(lc_logical.astype(int)) + 1 and\
                        np.sum(lc_logical.astype(int)) > 0:
                    # Do multiple linear regression
                    linreg = linear_model.LinearRegression().fit(x_0, y_0)
                    intercept = linreg.intercept_
                    coefficients = linreg.coef_

                    # Now loop again and reconstruct albedo's
                    lc_reg = 0
                    for i_0 in range(3):
                        if lc_logical[i_0]:
                            alb_lc[i_0, i, j] = intercept\
                                + coefficients[lc_reg] * 100.
                            lc_reg = lc_reg + 1
    return alb_lc


def _write_albedochanges_to_disk(alb_lc, dia_cfg,
                                 template_cube, datadict, cfg):
    transition_cube = template_cube
    result_dict = {'lc1': alb_lc[0, :, :], 'lc2': alb_lc[1, :, :],
                   'lc3': alb_lc[2, :, :]}
    names = {'lc1': '-'.join(dia_cfg['lc1_class']),
             'lc2': '-'.join(dia_cfg['lc2_class']),
             'lc3': '-'.join(dia_cfg['lc3_class'])}
    for ikey, jkey in it.product(result_dict.keys(), result_dict.keys()):
        if not ikey == jkey:
            # Take out Frac for readability
            transition_name = "albedo_change_from_{0}_to_{1}".format(
                names[ikey], names[jkey]).replace('Frac', '')
            logger.info("Calculating: %s", transition_name)
            transition_cube.data = result_dict[jkey] - result_dict[ikey]
            transition_cube.rename(transition_name)
            # Get some usefull info for constructing the filenames
            month_string = template_cube.coord('time').units.num2date(
                template_cube.coord('time').points)[0].strftime('%b')
            basename = '{0}-{1}-{2}'.format(month_string,
                                            datadict['alb']['dataset'],
                                            transition_name)
            transition_cube.attributes['plottitle'] = month_string + '-'\
                + datadict['alb']['dataset']
            transition_cube.attributes['plotsuptitle'] = transition_name
            savename_nc = os.path.join(cfg['work_dir'],
                                       '{0}.nc'.format(basename))
            logger.info("Saving file as: %s", savename_nc)
            iris.save(transition_cube, savename_nc)


def _plot_cube(cube, cfg):
    """Plot the transition cube."""
    # Also plot the transition_cube
    if not cube.ndim == 2:
        raise ValueError("Cube should be two-dimensional")
    plt.clf()
    cow = plt.axes(projection=crs.PlateCarree())
    cow.add_feature(cfeature.LAND)
    iris.quickplot.pcolormesh(cube, vmin=-.24, vmax=.24, cmap='bwr')
    # Set title/suptitle for plot
    if 'plottitle' in cube.attributes:
        plt.title(cube.attributes['plottitle'])
    if 'suptitle' in cube.attributes:
        plt.suptitle(cube.attributes['plotsuptitle'])
    # Draw coast lines
    plt.gca().coastlines()
    # Get right path for saving plots from the cfg dictionary.
    basename = cube.attributes['model_id'] + cube.name().replace(' ', '_')
    savename_fig = get_plot_filename(basename, cfg)
    logger.info("Saving figure as: %s", savename_fig)
    plt.savefig(savename_fig)


def main(cfg):
    """
    Calculate linear regression between albedo and xxfrac.

    Arguments:
    ---------
        cfg - nested dictionary of metadata

    """
    # Diagnostics cfg #TODO read from recipe
    dia_cfg = {
        'latsize_BB': 5,
        'lonsize_BB': 5,
        'threshold_sumpred': 90,
        'mingc': 3,
        'minnum_gc_bb': 15,
        'thres_fsnow': 0.1,
        'lc1_class': ['treeFrac'],
        'lc2_class': ['shrubFrac'],
        'lc3_class': ['grassFrac', 'cropFrac']
    }

    # assemble the data dictionary keyed by dataset name
    # this makes use of the handy group_metadata function that
    # orders the data by 'dataset'; the resulting dictionary is
    # keyed on datasets e.g. dict = {'MPI-ESM-LR': [var1, var2...]}
    # where var1, var2 are dicts holding all needed information per variable
    my_files_dict = group_metadata(cfg['input_data'].values(), 'dataset')
    all_short_names = ['alb', 'snc', 'cropFrac', 'treeFrac', 'grassFrac',
                       'shrubFrac', 'pastureFrac']

    # Loop over all datasets
    for dataset_name in my_files_dict:
        dataset_dict = my_files_dict[dataset_name]

        if dataset_name == 'Duveiller2018':
            logger.info("Only do plotting for dataset %s", dataset_name)
            cube = iris.load_cube(dataset_dict[0]['filename'])
            # Set plot title and plot suptitle
            cube.attributes['plottitle'] = cube.coord('time').units.num2date(
                cube.coord('time').points)[0].strftime('%b') + '-'\
                + 'Duveiller2018'
            cube.attributes['model_id'] = 'Duveiller2018'

            _plot_cube(cube, cfg)
            continue

        logger.info("Starting diagnostic for dataset %s", dataset_name)

        # Now reorder the dictionary in a meaningfull way, making data
        # accessible by short name
        datadict = {}
        for file_dict in dataset_dict:
            if file_dict['short_name'] in all_short_names:
                datadict[file_dict['short_name']] = file_dict

        # Define the different lc classes
        this_models_xxfracs = [key for key in datadict if 'Frac' in key]
        # Note that lc3 class depends on the classes available for this model
        lc3_class = dia_cfg['lc3_class']
        dia_cfg['lc3_class'] = [key for key in this_models_xxfracs
                                if key in lc3_class]

        # Load all data
        model_data = {fracKey: iris.load_cube(datadict[fracKey]['filename'])
                      for fracKey in this_models_xxfracs}
        # Load albedo and snow cover
        model_data['alb'] = iris.load_cube(datadict['alb']['filename'])
        model_data['snc'] = iris.load_cube(datadict['snc']['filename'])

        # Make sure that for each cube the dimension equals 2
        assert {c.ndim for _, c in model_data.items()} == set([2])

        # Add the appropriate masks to model_data
        model_data = _add_masks_albedolandcover(model_data,
                                                this_models_xxfracs,
                                                dia_cfg, cfg)

        # Now get albedo change due to landcover change
        alb_lc = _get_reconstructed_albedos(model_data, dia_cfg)

        # Calculate differences between them
        _write_albedochanges_to_disk(alb_lc, dia_cfg, model_data['snc'],
                                     datadict, cfg)

        # Loop through all nc files and plot them
        for ncfile in glob.glob(os.path.join(cfg['work_dir'], '*.nc')):
            transition_cube = iris.load_cube(ncfile)
            _plot_cube(transition_cube, cfg)


if __name__ == '__main__':
    # always use run_diagnostic() to get the config (the preprocessor
    # nested dictionary holding all the needed information)
    with run_diagnostic() as config:
        # list here the functions that need to run
        main(config)
