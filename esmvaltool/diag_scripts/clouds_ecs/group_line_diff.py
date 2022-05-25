"""Python example diagnostic."""
import logging
import os
from copy import deepcopy
from pathlib import Path
from pprint import pformat

import iris
import iris.plot as iplt
import iris.quickplot as qplt
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np

from esmvaltool.diag_scripts.shared import (
    group_metadata,
    run_diagnostic,
    get_plot_filename,
    save_data,
    save_figure,
    select_metadata,
    sorted_metadata,
    io,
)
from esmvaltool.diag_scripts.shared.plot import quickplot

logger = logging.getLogger(Path(__file__).stem)

VAR_NAMES = {
    'clt': 'total_cloud_fraction',
    'clivi': 'ice_water_path',
    'lwp': 'liquid_water_path',
    'swcre': 'shortwave_cloud_radiative_effect',
    'lwcre': 'longwave_cloud_radiative_effect',
    'netcre': 'net_cloud_radiative_effect',
}
LINE_LEGEND = {
    'ECS_high_hist': 'ECS_high',
    'ECS_med_hist': 'ECS_med',
    'ECS_low_hist': 'ECS_low',
}
LINE_COLOR = {
    'ECS_high_hist': 'royalblue',
    'ECS_high_scen': 'royalblue',
    'ECS_med_hist': 'green',
    'ECS_med_scen': 'green',
    'ECS_low_hist': 'orange',
    'ECS_low_scen': 'orange',
    'CMIP6': 'firebrick',
    'CMIP5': 'royalblue',
    'CMIP3': 'darkcyan',
    'OBS': 'black'
}
LINE_DASH = {
    'ECS_high_hist': 'solid',
    'ECS_high_scen': 'dashed',
    'ECS_med_hist': 'solid',
    'ECS_med_scen': 'dashed',
    'ECS_low_hist': 'solid',
    'ECS_low_scen': 'dashed',
    'CMIP6': 'solid',
    'CMIP5': 'solid',
    'CMIP3': 'solid',
    'OBS': 'solid'
}

def get_provenance_record(attributes, ancestor_files):
    """Create a provenance record describing the diagnostic data and plot."""
    #print(attributes)
    caption = ("Average {long_name} between {start_year} and {end_year} "
               "according to {dataset}.".format(**attributes))

    record = {
        'caption': caption,
        'statistics': ['mean'],
        'domains': ['global'],
        'plot_types': ['zonal'],
        'authors': [
            'andela_bouwe',
            'righi_mattia',
        ],
        'references': [
            'acknow_project',
        ],
        'ancestors': ancestor_files,
    }
    return record


def _get_cube_list(input_files):
    """Get :class:`iris.cube.CubeList` of input files."""
    cubes = iris.cube.CubeList()

    # Input files
    for filename in input_files:
        logger.info("Loading '%s'", filename)
        cube = _load_cube_with_dataset_coord(filename)
        cube.attributes['filename'] = filename
        cubes.append(cube)

    # Check metadata of cubes
    for cube in cubes:
        check_metadata(cube.attributes)

    return cubes


def _get_multi_model_mean(cubes, var):
    """Compute multi-model mean."""

    logger.debug("Calculating multi-model mean")
    datasets = []
    mmm = []
    for (dataset_name, cube) in cubes.items():
        datasets.append(dataset_name)
        mmm.append(cube.data)
    mmm = np.ma.array(mmm)
    dataset_0 = list(cubes.keys())[0]
    mmm_cube = cubes[dataset_0].copy(data=np.ma.mean(mmm, axis=0))
    attributes = {
        'dataset': 'MultiModelMean',
        'short_name': var,
        'datasets': '|'.join(datasets),
    }
    mmm_cube.attributes = attributes
    #print(mmm_cube)
    return  mmm_cube


def _get_multi_model_quantile(cubes, var, quantile):
    """Compute multi-model quantile."""

    logger.debug("Calculating multi-model %s quantile", quantile)
    datasets = []
    mmq = []
    for (dataset_name, cube) in cubes.items():
        datasets.append(dataset_name)
        mmq.append(cube.data)
    mmq = np.ma.array(mmq)
    dataset_0 = list(cubes.keys())[0]
    mmq_cube = cubes[dataset_0].copy(data=np.quantile(mmq, quantile, axis=0))
    attributes = {
        'dataset': 'MultiModel' + str(quantile),
        'short_name': var,
        'datasets': '|'.join(datasets),
    }
    mmq_cube.attributes = attributes
    #print(mmq_cube)
    return  mmq_cube


def compute_diagnostic(filename):
    """Compute an example diagnostic."""
    logger.debug("Loading %s", filename)
    cube = iris.load_cube(filename)

    if cube.var_name == 'pr':
      cube.units = cube.units / 'kg m-3'
      cube.data = cube.core_data() / 1000.
      cube.convert_units('mm day-1')
    elif cube.var_name == 'clivi':
        cube.convert_units('g/kg')
    elif cube.var_name == 'lwp':
        cube.convert_units('g/kg')

    logger.debug("Reading data")
    cube = iris.util.squeeze(cube)
    #print(cube)
    return cube


def compute_diff(filename1, filename2):
    """Compute difference between two cubes."""
    logger.debug("Loading %s", filename1)
    cube1 = iris.load_cube(filename1)
    cube2 = iris.load_cube(filename2)

    if cube1.var_name == 'pr':
      cube1.units = cube.units / 'kg m-3'
      cube1.data = cube.core_data() / 1000.
      cube1.convert_units('mm day-1')
      cube2.units = cube.units / 'kg m-3'
      cube2.data = cube.core_data() / 1000.
      cube2.convert_units('mm day-1')
    elif cube1.var_name == 'clivi':
        cube1.convert_units('g/kg')
        cube2.convert_units('g/kg')
    elif cube1.var_name == 'lwp':
        cube1.convert_units('g/kg')
        cube2.convert_units('g/kg')

    cube = cube2 - cube1
    cube.metadata = cube1.metadata
    cube = iris.util.squeeze(cube)
    #print(cube)
    return cube


def compute_diff_temp(input_data, group, dataset):
    """Compute relative change per temperture change."""

    dataset_name = dataset['dataset']
    var = dataset['short_name']

    input_file_1 = dataset['filename']

    var_data_2 = select_metadata(input_data,
                                 short_name=var,
                                 dataset=dataset_name,
                                 variable_group=group[1]) 
    if not var_data_2:
        raise ValueError(
            f"No '{var}' data for '{dataset_name}' in '{group[1]}' available")

    input_file_2 = var_data_2[0]['filename']

    tas_data_1 = select_metadata(input_data,
                              short_name='tas',
                              dataset=dataset_name,
                              variable_group='tas_'+group[0]) 
    tas_data_2 = select_metadata(input_data,
                              short_name='tas',
                              dataset=dataset_name,
                              variable_group='tas_'+group[1]) 
    if not tas_data_1:
        raise ValueError(
            f"No 'tas' data for '{dataset_name}' in '{group[0]}' available")
    if not tas_data_2:
        raise ValueError(
            f"No 'tas' data for '{dataset_name}' in '{group[1]}' available")
    input_file_tas_1 = tas_data_1[0]['filename']
    input_file_tas_2 = tas_data_2[0]['filename']

    cube = compute_diagnostic(input_file_1)
    if var in ['lwp', 'clivi']:
        cube.data[cube.data < 0.001] = 0.0

    cube_diff = compute_diff(input_file_1, input_file_2)
    cube_tas_diff = compute_diff(input_file_tas_1, input_file_tas_2)

    cube_tas_diff.data[cube_tas_diff.data < 0.1] = 0.0

    #cube_diff = cube
    #cube_diff = cube_tas_diff
    #cube_diff = 100. * (cube_diff / cube)
    cube_diff = 100. * (cube_diff / cube) / cube_tas_diff

    cube_diff.metadata = cube.metadata

    #cube_diff.units = 'K'
    #cube_diff.units = 'g/kg/K'
    cube_diff.units = '%/K'
    
    return cube_diff


def plot_model(cube, attributes, plot_type, cfg):
    """Plot each single model."""

    plt.figure(figsize=(12, 8))

    lat = cube.coord('latitude')
    qplt.plot(lat, cube)

    # Appearance
    dataset_name = attributes['dataset']
    title = f'{VAR_NAMES.get(cube.var_name, cube.var_name)} for {dataset_name}'
    filename = ('{}_{}'.format(VAR_NAMES.get(cube.var_name, cube.var_name),
                                  dataset_name))
    #filename = ('{}_{}_{}'.format(VAR_NAMES.get(cube.var_name, cube.var_name),
    #                              attributes['exp'], dataset_name))

    plt.title(title)
    plot_path = get_plot_filename(filename, cfg)
    plt.savefig(plot_path,
                bbox_inches='tight',
                orientation='landscape')
    logger.info("Wrote %s", plot_path)
    plt.close()


def plot_diagnostic(cube, legend, plot_type, cfg):
    """Create diagnostic data and plot it."""

    if cfg.get('quickplot'):
        # Create the plot
        quickplot(cube, **cfg['quickplot'])
    else:
        cube_label = legend
        line_color = LINE_COLOR.get(legend, legend)
        line_dash = LINE_DASH.get(legend, legend)

        plt.subplot(211)

        if plot_type == 'height':
          cube.coord('air_pressure').convert_units('hPa')
          y_axis = cube.coord('air_pressure')
          qplt.plot(cube, y_axis, label=cube_label, color=line_color, 
                    linestyle=line_dash)
        else:
          lat = cube.coord('latitude')
          qplt.plot(lat, cube, label=cube_label, color=line_color,
                    linestyle=line_dash)

        logger.info("Plotting %s", legend)


def plot_diagnostic_diff(cube, legend, plot_type, cfg):
    """Create diagnostic data and plot it."""

    if cfg.get('quickplot'):
        # Create the plot
        quickplot(cube, **cfg['quickplot'])
    else:
        cube_label = LINE_LEGEND.get(legend, legend)
        line_color = LINE_COLOR.get(legend, legend)
        line_dash = LINE_DASH.get(legend, legend)

        plt.subplot(212)

        if cube.var_name == 'pr':
          cube.units = cube.units / 'kg m-3'
          cube.data = cube.core_data() / 1000.
          cube.convert_units('mm day-1')
        elif cube.var_name == 'clivi':
            cube.convert_units('g/kg')
        elif cube.var_name == 'lwp':
            cube.convert_units('g/kg')

        if plot_type == 'height':
          cube.coord('air_pressure').convert_units('hPa')
          y_axis = cube.coord('air_pressure')
          qplt.plot(cube, y_axis, label=cube_label, color=line_color, 
                    linestyle=line_dash)
        else:
          lat = cube.coord('latitude')
          qplt.plot(lat, cube, label=cube_label, color=line_color,
                    linestyle=line_dash)

        logger.info("Plotting %s", legend)


def plot_errorband(cube1, cube2, legend, plot_type, cfg):
    """Create diagnostic data and plot it."""

    line_color = LINE_COLOR.get(legend, legend)
    line_dash = LINE_DASH.get(legend, legend)

    plt.subplot(211)

    if cube1.var_name == 'pr':
      cube1.units = cube1.units / 'kg m-3'
      cube1.data = cube1.core_data() / 1000.
      cube1.convert_units('mm day-1')
      cube2.units = cube2.units / 'kg m-3'
      cube2.data = cube2.core_data() / 1000.
      cube2.convert_units('mm day-1')
    elif cube1.var_name == 'clivi':
        cube1.convert_units('g/kg')
        cube2.convert_units('g/kg')
    elif cube1.var_name == 'lwp':
        cube1.convert_units('g/kg')
        cube2.convert_units('g/kg')

    if plot_type == 'height':
      cube1.coord('air_pressure').convert_units('hPa')
      cube2.coord('air_pressure').convert_units('hPa')
      y_axis = cube1.coord('air_pressure').points
      plt.fill_betweenx(y_axis, cube1.data, cube2.data, color=line_color,
                        linestyle=line_dash, alpha=.1)
    else:
      lat = cube1.coord('latitude').points
      plt.fill_between(lat, cube1.data, cube2.data, color=line_color,
                       linestyle=line_dash, alpha=.1)
    logger.info("Plotting %s", legend)


def main(cfg):
    """Run diagnostic."""
    cfg = deepcopy(cfg)
    cfg.setdefault('title_key', 'dataset')
    cfg.setdefault('filename_attach', 'base')
    logger.info("Using key '%s' to create titles for datasets",
                cfg['title_key'])

    plot_type = cfg['plot_type']

    input_data = list(cfg['input_data'].values())
    all_vars = list(group_metadata(input_data, 'short_name'))

    groups = group_metadata(input_data, 'variable_group', sort='dataset')

    #cubes = iris.cube.CubeList()

    plt.figure(figsize=(8, 12))

    for group_name in groups:
        if 'tas_' not in group_name:
            logger.info("Processing variable %s", group_name)

            dataset_names = []
            cubes = {}

            for dataset in groups[group_name]:

                dataset_name = dataset['dataset']
                var = dataset['short_name']

                if dataset_name not in ['MultiModelMean', 'MultiModelP5', 'MultiModelP95']:

                    logger.info("Loop dataset %s", dataset_name)

                    input_file = dataset['filename']
                    cube = compute_diagnostic(input_file)

                    cubes[dataset_name] = cube

                    #if cfg['plot_each_model']:
                    #    plot_model(cube, dataset, plot_type, cfg)


            cube_mmm = _get_multi_model_mean(cubes, var)

            plot_diagnostic(cube_mmm, group_name, plot_type, cfg)

            cube_p5  = _get_multi_model_quantile(cubes, var, 0.05)
            cube_p95 = _get_multi_model_quantile(cubes, var, 0.95)

            plot_errorband(cube_p5, cube_p95, group_name, plot_type, cfg)

    if plot_type == 'height':
      plt.ylim(1000.,100.)
      plt.yscale('log')
      plt.yticks([1000., 800., 600., 400., 300., 200., 100.], [1000, 800, 600, 400, 300, 200, 100])
      title = 'Vertical mean of ' + dataset['long_name']
    elif plot_type == 'zonal':
      title = 'Zonal mean of ' + dataset['long_name']
    else:
      title = dataset['long_name']

    plt.title(title)
    plt.legend(ncol=1)
    plt.grid(True)

    for group_name in cfg['group_by']:

        logger.info("Processing group %s", group_name[0])

        dataset_names = []
        cubes_diff = {}

        for dataset in groups[group_name[0]]:
            dataset_name = dataset['dataset']
            var = dataset['short_name']

            if dataset_name not in ['MultiModelMean', 'MultiModelP5', 'MultiModelP95']:
                logger.info("Loop dataset %s", dataset_name)
                dataset_names.append(dataset_name)

                cube_diff = compute_diff_temp(input_data, group_name, dataset)

                cubes_diff[dataset_name] = cube_diff

                if cfg['plot_each_model']:
                    plot_model(cube_diff, dataset, plot_type, cfg)

        cube_mmm = _get_multi_model_mean(cubes_diff, var)

        plot_diagnostic_diff(cube_mmm, group_name[0], plot_type, cfg)

    if plot_type == 'height':
      plt.ylim(1000.,100.)
      plt.yscale('log')
      plt.yticks([1000., 800., 600., 400., 300., 200., 100.], [1000, 800, 600, 400, 300, 200, 100])
      plt.axvline(x=0, ymin=0., ymax=1., color='black', linewidth=3)
      title = 'Difference of vertical mean of ' + dataset['long_name']
    elif plot_type == 'zonal':
      plt.axhline(y=0, xmin=-90., xmax=90., color='black', linewidth=3)
      title = 'Difference of zonal mean of ' + dataset['long_name']
    else:
      title = dataset['long_name']

    plt.title(title)
    plt.legend(ncol=1)
    plt.grid(True)

    provenance_record = get_provenance_record(
        dataset, ancestor_files=cfg['input_files'])

    if plot_type == 'height':
      basename = 'level_diff_' + dataset['short_name'] + '_' + cfg['filename_attach']
    else:
      basename = 'zonal_diff_' + dataset['short_name'] + '_' + cfg['filename_attach']

    # Save the data used for the plot
    save_data(basename, provenance_record, cfg, cube_mmm)

    # And save the plot
    save_figure(basename, provenance_record, cfg)



if __name__ == '__main__':

    with run_diagnostic() as config:
        main(config)