"""Python diagnostic file to plot figures from Gillett (2023)."""
import logging
import os
import csv
import matplotlib.pyplot as plt
import numpy as np
import iris
from iris.analysis import MEAN
from iris.analysis.stats import pearsonr

from esmvaltool.diag_scripts.shared import group_metadata, run_diagnostic

logger = logging.getLogger(os.path.basename(__file__))

def compute_diagnostic(filename):
    """Compute an example diagnostic."""
    logger.debug("Loading %s", filename)
    cube = iris.load_cube(filename)

    logger.debug("Running example computation")
    cube = iris.util.squeeze(cube)
    return cube

def get_provenance_record(attributes, ancestor_files, plot_type):
    """Create a provenance record describing the diagnostic data and plot."""
    caption = ("Correlation of {long_name} between {dataset} and "
               "{reference_dataset}.".format(**attributes))

    record = {
        'caption': caption,
        'statistics': ['corr'],
        'domains': ['global'],
        'plot_type': plot_type,
        'authors': [
            'nathan_gillett',
        ],
        'references': [
            'acknow_project',
        ],
        'ancestors': ancestor_files,
    }
    return record


def main(cfg):
    input_data = group_metadata(
        cfg['input_data'].values(),
        'dataset',
        sort='short_name',
    )
    plot_dir=cfg['plot_dir']
    plt.ioff() #Turn off interactive plotting.
# Define variables to set up plot.
    models=['ACCESS-ESM1-5','CanESM5','CESM2','MPI-ESM1-2-LR','NorESM2-MM']
    F_4co2=[7.95,7.61,8.91,8.35,8.38] #Smith et al., 2020 Table 2. Had to assume same ERF for ACCESS and CESM families.
    ECS=[3.87,5.62,5.16,3.00,2.50] #Schlund et al., 2020, Table A2
    TCRE=[2.02,2.09,2.13,1.65,1.32] #Arora et al. 2020, Table 4. Assume same TCRE for all CESM2 models.
    nmodel=len(models)
    plt.figure(1,figsize=[7.1,6.7])
    plt.figure(2,figsize=[7.1,6.7])

#Read in data from pre-processed files.
#Loop over models. Read and plot everything for one model, then move on to the next.
    for dataset in input_data:
        logger.info("Processing model %s", dataset)
        grouped_input_data=group_metadata(input_data[dataset],'variable_group',sort='exp')
        for short_name in grouped_input_data:
            logger.info("Processing variable %s", short_name)
            grouped_input_data_var=group_metadata(grouped_input_data[short_name],'exp',sort='exp')
            
            for exp in grouped_input_data_var:
                logger.info("Processing experiment %s", exp)
                for attributes in grouped_input_data_var[exp]:
                    input_file = attributes['filename']
                    if exp == 'abrupt-4xCO2':
                        cube1 = compute_diagnostic(input_file)
                    if exp == 'piControl':
                        cube2 = compute_diagnostic(input_file)
            print ('short_name',short_name)
            if short_name == 'tas':
                tas=cube1.data-cube2.data
            if short_name == 'nbp':
                atmos_land_flux=(cube1.data-cube2.data)*31556952/1e12 #in PgC/yr
            if short_name == 'fgco2':
                atmos_ocean_flux=(cube1.data-cube2.data)*31556952/1e12 #in PgC/yr
            if short_name == 'hfds':
                q=(cube1.data-cube2.data)/5.101e14 #Convert to W/m^2.
        atmos_co2=np.full([150],1.8163314) #Increase in atmospheric CO2 in 4xCO2 simulation.
        ocean_cumflux=np.cumsum(atmos_ocean_flux[:])/1000.
        land_cumflux=np.cumsum(atmos_land_flux[:])/1000.
        emiss=atmos_co2[:]+ocean_cumflux[:]+land_cumflux[:]
        year=list(np.arange(150))
        mod_index=models.index(dataset)        

#Plot Figure 2 in Gillett (2023)
        plt.figure(1)
        plt.subplot(nmodel,3,mod_index*3+1)
        plt.plot(year[:],q[:],color='black')
        plt.ylabel('q (W/$m^2$)')
#Calculate values needed for analytical model to compare with ESMs.
        lambda_=F_4co2[mod_index]/(2*ECS[mod_index]) 
        delta_ca=atmos_co2[0] 
        q0=F_4co2[mod_index]
        alpha=(atmos_ocean_flux[0])*lambda_*TCRE[mod_index]/(q0*1000)
        f_est=(atmos_ocean_flux[0])*np.exp(-1.*np.arange(150)*alpha)
        emiss_est=((atmos_ocean_flux[0])/(alpha*1000.))*(1-np.exp(-1.*np.arange(150)*alpha))
        q_est=q0*np.exp(-1.*np.arange(150)*alpha)
#Begin plotting.
        plt.plot(year[:],q_est[:],color='gray')
        plt.axis([0,150,0,8])
        if mod_index==nmodel-1:
          plt.xlabel('Year')
        plt.text (20,7,dataset,fontsize =10,fontweight='bold', va='center')
        if mod_index ==0:
          plt.title('Heat flux')
        if mod_index < nmodel-1:
          plt.xticks([])
        plt.subplot(nmodel,3,mod_index*3+2)
        plt.ylabel('f (PgC/yr)')
        plt.plot(year[:],atmos_ocean_flux[:],color='black',label='ESM')
        plt.plot(year[:],f_est[:],color='gray',label='Analytical')
        plt.axis([0,150,0,95])
        if mod_index == 0:
          plt.title('Carbon flux')
        if mod_index == nmodel-1:
          plt.legend(loc="upper right",labelspacing=0.1,borderpad=0.1,fontsize=10)
          plt.xlabel('Year')
        if mod_index < nmodel-1:
          plt.xticks([])
        plt.subplot(nmodel,3,mod_index*3+3)
        plt.ylabel('(W/$m^2$)/(PgC/yr)')
        plt.plot(year[:],q[:]/(atmos_ocean_flux[:]),color='black')
        plt.plot([0,1000],[q0/atmos_ocean_flux[0],q0/atmos_ocean_flux[0]],color='gray')
        plt.axis([0,150,0,2])
        if mod_index == 0:
          plt.title('Ratio')
        if mod_index == nmodel-1:
          plt.xlabel('Year')
        if mod_index < nmodel-1:
          plt.xticks([])

#Plot Figure 1 in Gillett (2023)
        plt.figure(2)
        plt.subplot(nmodel,3,mod_index*3+1)
        plt.plot(year[:],tas[:],color="black",label='ESM')#,label='\u0394T')
        plt.plot(year[:],(q_est[:]*-1.+F_4co2[mod_index])/lambda_,color="gray",label='Analytical')
        plt.ylabel('\u0394T (K)')
        if mod_index==nmodel-1:
          plt.xlabel('Year')
          plt.legend(loc="center left",labelspacing=0.1,borderpad=0.1,fontsize=10)
        plt.text (5,10,dataset,fontsize =10,fontweight='bold', va='center')
        if mod_index ==0:
          plt.title('Warming')
        plt.axis([0,150,0,11.5])
        if mod_index < nmodel-1:
            plt.xticks([])
        plt.subplot(nmodel,3,mod_index*3+2)
        plt.fill_between(year[:],np.zeros(150),atmos_co2[:],color="red")
        plt.fill_between(year[:],atmos_co2[:],atmos_co2[:]+ocean_cumflux,color="blue")
        plt.fill_between(year[:],atmos_co2[:]+ocean_cumflux,atmos_co2[:]+ocean_cumflux+land_cumflux,color="green")
        plt.plot(year[:],emiss[:],color="black",label='Cumulative CO2 emissions')
        plt.plot(year[:],emiss_est[:],color="gray",label='Cumulative CO2 emissions - analytical')
        plt.ylabel('Carbon (EgC)')
        print ('atmos,ocean,land fractions:',atmos_co2[149]/emiss[149],ocean_cumflux[149]/emiss[149],land_cumflux[149]/emiss[149])
        print ('emiss_est/ocean_cumflux',emiss_est/ocean_cumflux)
        if mod_index == 0:
          plt.title('Cumulative emissions')
        if mod_index == nmodel-1:
          plt.text (65,1.3,'Atmosphere',fontsize =10, va='center')
          plt.text (65,2.1,'Ocean',fontsize =10, va='center')
          plt.text (65,2.9,'Land',fontsize =10, va='center')
          plt.xlabel('Year')
        plt.axis([0,150,0,5.5])
        if mod_index < nmodel-1:
          plt.xticks([])
        plt.subplot(nmodel,3,mod_index*3+3)        
        plt.ylabel('Ratios (K/EgC)')
        plt.plot(year[:],0.1*tas[:]/ocean_cumflux[:],color='blue',label='0.1\u0394T/\u0394$C_O$')
        plt.plot(year[:],tas[:]/(ocean_cumflux[:]+atmos_co2[:]),color='red',label='\u0394T/(\u0394$C_O$+\u0394$C_A$)')
        plt.plot(year[:],tas[:]/emiss,color="black",label='\u0394T/E')
        plt.plot([0,1000],[TCRE[mod_index],TCRE[mod_index]],color="gray")#,label='TCRE')
        plt.axis([0,150,0,4])
        if mod_index == 0:
          plt.title('Ratios')
        if mod_index < nmodel-1:
          plt.xticks([])
        if mod_index == nmodel-1:        
          plt.xlabel('Year')
          plt.legend(loc="upper left",labelspacing=0.1,borderpad=0.1,fontsize=10)
#Write data out to a file, one per model.
        with open(plot_dir+'/gillett23_figs2and3_data_'+dataset+'.csv', mode='w') as file:
          data_writer=csv.writer(file,delimiter=',',quotechar='"', quoting=csv.QUOTE_MINIMAL)
          data_writer.writerow(['Year','Delta T','Delta T analytical','Delta C_A','Delta C_A + Delta C_O',\
                                'E','E analytical','0.1*Delta T / Delta C_O','Delta T/(Delta C_A+DeltaC_O)','Delta T/E','TCRE',\
                                'q','q analytical','f','f analytical','q/f','F_4CO2/f(0)'])
          for yy in range(150):
            data_writer.writerow([yy,tas[yy],(q_est[yy]*-1.+F_4co2[mod_index])/lambda_,atmos_co2[yy],atmos_co2[yy]+ocean_cumflux[yy],\
                                  emiss[yy],emiss_est[yy],0.1*tas[yy]/ocean_cumflux[yy],tas[yy]/(ocean_cumflux[yy]+atmos_co2[yy]),tas[yy]/emiss[yy],TCRE[mod_index],\
                                  q[yy],q_est[yy],atmos_ocean_flux[yy],f_est[yy],q[yy]/atmos_ocean_flux[yy],q0/atmos_ocean_flux[0]])


#Finalise plots and write them out and close them.
    plt.figure(1)
    plt.tight_layout(pad=0.1)
    plt.savefig(plot_dir+'/ocean_fluxes.png')
    plt.close()

    plt.figure(2)
    plt.tight_layout(pad=0.1)
    plt.savefig(plot_dir+'/tcre.png')
    plt.close()

                               

    
if __name__ == '__main__':

    with run_diagnostic() as config:
        main(config)
