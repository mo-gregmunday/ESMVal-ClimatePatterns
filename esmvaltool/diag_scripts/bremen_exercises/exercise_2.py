"""Example diagnostic script 2 for the lecture Climate Modelling Part 2."""

import os

import iris
import matplotlib.pyplot as plt

from esmvaltool.diag_scripts.shared import run_diagnostic


def main(cfg):
    """Execute the diagnostic."""
    ###########################################################################
    # Running your recipe by
    #
    # esmvaltool run ~/ESMValTool_2/esmvaltool/recipes/recipe_bremen_exercise_2.yml --config-file ~/config/bremen.yml
    #
    # should procuce a plot with the following features:
    # - Time series of annually and globally averaged surface air temperature
    #   from 1970 to 2005 of the datasets used in exercise 1.
    # - Units: celsius
    # - Legend with the datasets' names.
    #
    ###########################################################################

    # Add your code here

    # Extract data
    input_data = cfg['input_data'].values()

    # Iterate over all datasets and plot them
    for dataset in input_data:
        filename = dataset['filename']
        cube = iris.load_cube(filename)
        iris.quickplot.plot(cube.coord('year'), cube, label=dataset['dataset'])

    # Save plot
    plt.legend()
    plot_type = cfg['output_file_type']
    plot_path = os.path.join(cfg['plot_dir'], 'exercise_2.' + plot_type)
    plt.savefig(plot_path)
    plt.close()


# Call the main function when the script is called
# Do not modify
if __name__ == '__main__':

    with run_diagnostic() as config:
        main(config)
