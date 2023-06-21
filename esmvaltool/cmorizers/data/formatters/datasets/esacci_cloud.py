"""ESMValTool CMORizer for ESACCI-CLOUD data.

Tier
    Tier 2: other freely-available dataset.

Source
    https://public.satproj.klima.dwd.de/data/ESA_Cloud_CCI/CLD_PRODUCTS/v3.0/L3U/AVHRR-PM/

Last access
    20230619

Download and processing instructions
    see downloading script
"""

import copy
import glob
import logging
import os

import iris
from cf_units import Unit
from iris import NameConstraint

from esmvaltool.cmorizers.data import utilities as utils
from esmvalcore.preprocessor import regrid

logger = logging.getLogger(__name__)


def _extract_variable(short_name, var, year, month, cfg, in_dir,
                      out_dir):
    """Extract variable."""
    cube = iris.cube.CubeList()
    #filename = f'{year}{month:02}0*' + var['file']
    filename = f'{year}{month:02}01' + var['file']
    filelist = glob.glob(os.path.join(in_dir, filename))
    for filename in sorted(filelist):
        logger.info("CMORizing file %s", filename)

        # load data
        raw_var = var.get('raw', short_name)
        daily_cube = iris.load_cube(filename, NameConstraint(var_name=raw_var))
        daily_cube.data = 100. * daily_cube.data
        daily_cube.attributes.clear()

        # Fix coordinates
        daily_cube = utils.fix_coords(daily_cube)

        cube.append(daily_cube)

    cube = cube.concatenate_cube()

    # regridding from 0.05x0.05 to 0.5x0.5
    cube = regrid(cube, target_grid='0.5x0.5', scheme='area_weighted')

    # fix time units
    cube.coord('time').convert_units(
        Unit('days since 1950-1-1 00:00:00', calendar='gregorian'))

    print(cfg['cmor_table'])
    #for i in cfg['cmor_table']:
    #    print(i)
    print(var['mip'])
    cmor_info = cfg['cmor_table'].get_variable(var['mip'], short_name)
    print(*cmor_info)

    # Fix coordinates
    utils.fix_dim_coordnames(cube)
    ## fix flipped latitude
    #utils.flip_dim_coord(cube, 'latitude')
    #utils.fix_dim_coordnames(cube)
    cube_coord = cube.coord('latitude')
    utils.fix_bounds(cube, cube_coord)
    cube_coord = cube.coord('longitude')
    utils.fix_bounds(cube, cube_coord)

    # Fix metadata and  update version information
    attrs = copy.deepcopy(cfg['attributes'])
    attrs['mip'] = var['mip']
    utils.fix_var_metadata(cube, cmor_info)
    utils.set_global_atts(cube, attrs)

    # Save variable
    utils.save_variable(cube,
                        short_name,
                        out_dir,
                        attrs,
                        unlimited_dimensions=['time'])


def cmorization(in_dir, out_dir, cfg, cfg_user, start_date, end_date):
    """Cmorization func call."""
    glob_attrs = cfg['attributes']
    # Run the cmorization
    for (short_name, var) in cfg['variables'].items():
        logger.info("CMORizing variable '%s'", short_name)
        for year in range(glob_attrs['start_year'],
                          glob_attrs['end_year'] + 1):
            for month in range(1,2):
                print(month)
                _extract_variable(short_name, var, year, month, cfg, in_dir,
                                     out_dir)
