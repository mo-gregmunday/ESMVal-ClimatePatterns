"""Example diagnostic script 3 for the lecture Climate Modelling Part 2."""

import os

import iris
import matplotlib.pyplot as plt

from esmvaltool.diag_scripts.shared import run_diagnostic, select_metadata


def main(cfg):
    """Execute the diagnostic."""
    ###########################################################################
    # Running your recipe by
    #
    # esmvaltool run ~/ESMValTool_2/esmvaltool/recipes/recipe_bremen_exercise_3.yml --config-file ~/config/bremen.yml
    #
    # should procuce a plot of the times series of the globally and annually
    # averaged surface air temperature from 2006 to 2100 of the RCP 2.6 and
    # RCP 8.5 scenarios for the climate models (not observations) used in
    # exercise 1 and 2.
    ###########################################################################

    # Add your code here

    # Extract data
    input_data = cfg['input_data'].values()

    # Plot RCP 2.6 data
    rcp26_data = select_metadata(input_data, exp='rcp26')
    for dataset in rcp26_data:
        filename = dataset['filename']
        cube = iris.load_cube(filename)
        label = dataset['dataset'] + ' (RCP 2.6)'
        iris.quickplot.plot(cube.coord('year'), cube, label=label)

    # Plot RCP 8.5 data
    rcp85_data = select_metadata(input_data, exp='rcp85')
    for dataset in rcp85_data:
        filename = dataset['filename']
        cube = iris.load_cube(filename)
        label = dataset['dataset'] + ' (RCP 8.5)'
        iris.quickplot.plot(cube.coord('year'), cube, label=label)

    # Save plot
    plt.legend()
    plot_type = cfg['output_file_type']
    plot_path = os.path.join(cfg['plot_dir'], 'exercise_3.' + plot_type)
    plt.savefig(plot_path)
    plt.close()


# Call the main function when the script is called
# Do not modify
if __name__ == '__main__':

    with run_diagnostic() as config:
        main(config)
