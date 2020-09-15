"""Example diagnostic script 1 for the lecture Climate Modelling Part 2."""

import os

import iris
import matplotlib.pyplot as plt

from esmvaltool.diag_scripts.shared import run_diagnostic, select_metadata


def main(cfg):
    """Execute the diagnostic."""
    ###########################################################################
    # Part 1
    #
    # Run the first exercise recipe by
    #
    # esmvaltool run ~/ESMValTool_2/esmvaltool/recipes/recipe_bremen_exercise_1.yml --config-file ~/config/bremen.yml
    #
    # Which data is selected, what happens to it in this diagnostic script and
    # what is plotted?
    ###########################################################################

    # Extract MultiModelMean dataset
    input_data = cfg['input_data'].values()
    mmm_data = select_metadata(input_data, dataset='MultiModelMean')[0]

    # Read MMM dataset into cube
    mmm_file = mmm_data['filename']
    mmm_cube = iris.load_cube(mmm_file)
    mmm_cube.rename('Multi-model mean temperature')

    # Set path of first plot
    plot_type = cfg['output_file_type']
    plot_path_1 = os.path.join(cfg['plot_dir'], 'exercise_1a.' + plot_type)

    # Plot the data
    iris.quickplot.pcolormesh(mmm_cube, cmap='plasma')
    plt.gca().coastlines()
    plt.savefig(plot_path_1)
    plt.close()

    ###########################################################################
    # Part 2
    #
    # Based on the code of part 1, extract the observational dataset and
    # calculate the multi-model mean bias = multi-model mean - observations.
    # Plot this data similarly to part 1.
    ###########################################################################

    # Add your code here

    # Extract observational dataset
    obs_data = select_metadata(input_data, dataset='NCEP')[0]

    # Read OBS dataset into cube
    obs_file = obs_data['filename']
    obs_cube = iris.load_cube(obs_file)

    # Calculate MMM bias
    bias_cube = mmm_cube - obs_cube
    bias_cube.rename('Multi-model mean temperature bias')

    # Set path of second plot
    plot_type = cfg['output_file_type']
    plot_path_2 = os.path.join(cfg['plot_dir'], 'exercise_1b.' + plot_type)

    # Plot the data
    iris.quickplot.pcolormesh(bias_cube, cmap='bwr')
    plt.gca().coastlines()
    plt.savefig(plot_path_2)
    plt.close()


# Call the main function when the script is called
# Do not modify
if __name__ == '__main__':

    with run_diagnostic() as config:
        main(config)
