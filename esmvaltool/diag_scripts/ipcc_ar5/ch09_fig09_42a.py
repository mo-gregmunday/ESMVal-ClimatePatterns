#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnostic script to plot figure 9.42a of IPCC AR5 chapter 9.

Description
-----------
Calculate and plot the equilibrium climate sensitivity (ECS) vs. the global
mean surface temperature (GMSAT) for several CMIP5 models (see IPCC AR5 WG1 ch.
9, fig. 9.42a).

Author
------
Manuel Schlund (DLR, Germany)

Project
-------
CRESCENDO

Configuration options in recipe
-------------------------------
save : dict, optional
    Keyword arguments for the `fig.saveplot()` function.
axes_functions : dict, optional
    Keyword arguments for the plot appearance functions.

"""

import logging
import os

import iris
from iris import Constraint

from esmvaltool.diag_scripts.shared import (
    extract_variables, get_ancestor_file, get_plot_filename, plot,
    run_diagnostic, save_iris_cube, variables_available)

logger = logging.getLogger(os.path.basename(__file__))


def plot_data(cfg, hist_cubes, pi_cubes, ecs_cube):
    """Plot data."""
    if not cfg['write_plots']:
        return
    x_data = []
    y_data = []
    dataset_names = []
    plot_kwargs = []

    # Collect data
    for dataset in hist_cubes:

        # Historical data
        x_data.append(ecs_cube.extract(Constraint(dataset=dataset)).data)
        y_data.append(hist_cubes[dataset].data)
        dataset_names.append(dataset)
        plot_kwargs.append({
            'label': dataset,
            'linestyle': 'none',
            'markersize': 10,
        })

        # PiControl data
        x_data.append(ecs_cube.extract(Constraint(dataset=dataset)).data)
        y_data.append(pi_cubes[dataset].data)
        dataset_names.append(dataset)
        plot_kwargs.append({
            'label': '_' + dataset,
            'linestyle': 'none',
            'markersize': 6,
        })

    # Plot data
    path = get_plot_filename('ch09_fig09_42a', cfg)
    plot.multi_dataset_scatterplot(
        x_data,
        y_data,
        dataset_names,
        path,
        plot_kwargs=plot_kwargs,
        save_kwargs=cfg.get('save', {}),
        axes_functions=cfg.get('axes_functions', {}))
    return


def write_data(cfg, hist_cubes, pi_cubes, ecs_cube):
    """Write netcdf file."""
    if cfg['write_plots']:
        datasets = list(hist_cubes)

        # Collect data
        data_ecs = []
        data_hist = []
        data_pi = []
        for dataset in datasets:
            data_ecs.append(ecs_cube.extract(Constraint(dataset=dataset)).data)
            data_hist.append(hist_cubes[dataset].data)
            data_pi.append(pi_cubes[dataset].data)

        # Create cube
        dataset_coord = iris.coords.AuxCoord(datasets, long_name='dataset')
        tas_hist_coord = iris.coords.AuxCoord(
            data_hist,
            attributes={'exp': 'historical'},
            **extract_variables(cfg, as_iris=True)['tas'])
        tas_picontrol_coord = iris.coords.AuxCoord(
            data_pi,
            attributes={'exp': 'piControl'},
            **extract_variables(cfg, as_iris=True)['tas'])
        cube = iris.cube.Cube(
            data_ecs,
            var_name='ecs',
            long_name='equilibrium_climate_sensitivity',
            aux_coords_and_dims=[(dataset_coord, 0), (tas_hist_coord, 0),
                                 (tas_picontrol_coord, 0)])

        # Save file
        save_iris_cube(cube, cfg, basename='ch09_fig09_42a')


def main(cfg):
    """Run the diagnostic."""
    input_data = cfg['input_data'].values()

    # Check if tas is available
    if not variables_available(cfg, ['tas']):
        raise ValueError("This diagnostic needs 'tas' variable")

    # Get ECS data
    ecs_filepath = get_ancestor_file(cfg, 'ecs.nc')
    ecs_cube = iris.load_cube(ecs_filepath)

    # Create iris cubes for each dataset
    hist_cubes = {}
    pi_cubes = {}
    for data in input_data:
        name = data['dataset']
        logger.info("Processing %s", name)
        cube = iris.load_cube(data['filename'])

        # Preprocess cubes
        cube.convert_units(cfg.get('tas_units', 'celsius'))
        cube = cube.collapsed(['time'], iris.analysis.MEAN)

        # Save cubes
        if data.get('exp') == 'historical':
            hist_cubes[name] = cube
        elif data.get('exp') == 'piControl':
            pi_cubes[name] = cube
        else:
            pass

    # Plot data
    plot_data(cfg, hist_cubes, pi_cubes, ecs_cube)

    # Write netcdf file
    write_data(cfg, hist_cubes, pi_cubes, ecs_cube)


if __name__ == '__main__':
    with run_diagnostic() as config:
        main(config)
