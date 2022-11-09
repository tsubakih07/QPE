#%%
import pyart
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from datetime import datetime as dt
import os
import nclcmaps
#%%
"""
input radar object by pyart to proceed with data QC based on 
Loh et al. (2021)
Caution: This only processes lowest elevation angle (swp=0)
"""
### test
case = "Maria"
date = '2018_0710'
indir = '/mnt/d/Project/RAWdata/'+case+'/'+date+'/'
files = os.listdir(indir)
filename = files[170]
### read radar data
radar = pyart.io.read_nexrad_archive(indir+filename)
swp = 0
radar = radar.extract_sweeps([swp])

#%%

def rewrite(radar,key,data):
    dict = radar.fields[key]
    dict['data'] = data
    radar.add_field(key,dict,replace_existing=True)
    return radar

def add_data(radar,key,data):
    dict = pyart.config.get_metadata(key)
    dict['data'] = data
    radar.add_field(key,dict,replace_existing=True)
    return radar

def gatefilter_only_rain(radar,ml=4000.):
    ### data masking
    gatefilter = pyart.correct.GateFilter(radar)
    ### below melting level < 5.0-km (data from raindrop only)
    lon, lat, alt = radar.get_gate_lat_lon_alt(swp)
    alt_dict = pyart.config.get_metadata(radar)
    alt_dict['data'] = alt
    radar.add_field('altitude',alt_dict)
    gatefilter.exclude_above('altitude',ml)
    radar.fields.pop('altitude')    # delete field
    return gatefilter

def calc_sigma(radar):
    phidp = radar.get_field(swp,'differential_phase')
    df = pd.DataFrame(phidp)
    sigma = df.rolling(window=5,axis=1,center=True,min_periods=5).std() 
    return sigma.values   

def qc_A(radar,swp=0):
    """
    Removal of Nonmeteorological Signals
        Remove:
        1) PH < 0.85
        2) sigma_Φdp(5 gates)> 20°
    Args:
        radar (radar ofject): created/read by pyart
    Returns:
        radar, gatefilter
    """
    ### extract data below melting level
    ### also initiate gatefilter
    gatefilter = gatefilter_only_rain(radar)
    ### remove noise
    gatefilter.exclude_below('cross_correlation_ratio', 0.85)
    
    sigma = calc_sigma(radar)    
    radar = add_data(radar,'sigma_phidp',sigma)
    
    gatefilter.exclude_above('sigma_phidp',20.)
    
    return radar, gatefilter

#%%
def attenuation_correction(radar,band='S'):
    """
    Attenuation correction by pyart

    Args:
        radar (radar object): created/read by pyart
    """  
    
    ### finish qc_A first to get gatefilter
    radar,gatefilter = qc_A(radar)
    
    ### get coefficient
    # S band:
    param_att_dict = dict()
    param_att_dict.update({'S': (0.02, 0.64884, 0.15917, 1.0804)})
    # C band:
    param_att_dict.update({'C': (0.08, 0.64884, 0.3, 1.0804)})
    # X band:
    param_att_dict.update({'X': (0.31916, 0.64884, 0.15917, 1.0804)})
    
    a_coef, beta, c, d = param_att_dict[band]   
    out = pyart.correct.calculate_attenuation_zphi(radar, doc=None, fzl=4000., 
                                            a_coef=a_coef, beta=beta, c=c, d=d, 
                                            smooth_window_len=5, gatefilter=gatefilter)
    return out


def qc_B_C(radar):
    """
    Attenuation Correction Schemes using Φdp
    currently use pyart module "correct.calculate_attenuation_zphi()"

    Args:
        radar (radar object): created/read by pyart
    
    Returns:
        radar (radar object): radar field added (Ah, Adp, cor_Zh, cor_Zdr) 
    """
    Ah, _, cor_z, Adp, _, cor_zdr = attenuation_correction(radar)
    radar.add_field('Ah',Ah)
    radar.add_field('Adp',Adp)
    radar.add_field('cor_Zh',cor_z)
    radar.add_field('cor_Zdr',cor_zdr)
    return radar

#%%
def qc_D(radar,bias=0.):
    """
    Zdr systematic bias correction

    Args:
        radar (radar object): created/read by pyart
    
    Returns:
        radar (radar object):  
    """
    zdr_new = pyart.correct.correct_bias(radar, bias=bias, field_name='cor_Zdr')
    radar.add_field('cor_Zdr',zdr_new,replace_existing=True)
    return radar

# %%

def qc_all(radar):
    radar, gatefilter = qc_A(radar)
    radar = qc_B_C(radar)
    bias = input("Enter Zdr bias:")
    radar = qc_D(radar,bias=bias)
    return radar, gatefilter


# %% check data (PPI) ===================================================
# ### ~ plot begins ~
# fig = plt.figure(facecolor='white', figsize=(12, 10))
# display = pyart.graph.RadarDisplay(radar)

# # plot super resolution reflectivity
# c_index = [2,3,4,5,6,7,9,10,11,12,13,15,16]
# cmap = nclcmaps.cmap('prcp_1',c_index)   
# clv = [-5.,0.,5.,10.,15.,20.,25.,30.,35.,40.,45.,50.,55.,60.]
# norm = mpl.colors.BoundaryNorm(clv,cmap.N)

# plt.axis('off')
# # plt.title('{0}:{1} UTC'.format(time[0],time[1]),fontsize=14, pad=20)
# # plt.title("Lowest available PPI ("+str(ele)+"°) "+tstr,fontsize=15, pad=30)

# ax = fig.add_subplot(221)

# display.plot('reflectivity', swp, title='Reflectivity (raw)',gatefilter=gatefilter,
#             cmap=cmap, norm=norm,
#             axislabels=('', 'North South distance from radar (km)'),
#             vmin=0, vmax=60, colorbar_label='', ax=ax)
# display.set_limits(xlim=(-200, 200), ylim=(-200, 200), ax=ax)


# ax = fig.add_subplot(222)
# cmap2 = nclcmaps.cmap('NCV_bright') 
# display.plot('differential_reflectivity', swp, title='$Z_{DR}$ (raw)',gatefilter=gatefilter,
#             axislabels=('', ''), #cmap=cmap2,
#             vmin=-10, vmax=10, colorbar_label='', ax=ax)
# display.set_limits(xlim=(-200, 200), ylim=(-200, 200), ax=ax)


# ax = fig.add_subplot(223)
# display.plot('cor_Zh', swp, title='Reflectivity (corrected)',
#             cmap=cmap, norm=norm,
#             axislabels=('East West distance from radar (km)', 'North South distance from radar (km)'),
#             vmin=0, vmax=60, colorbar_label='', ax=ax)
# display.set_limits(xlim=(-200, 200), ylim=(-200, 200), ax=ax)


# ax = fig.add_subplot(224)
# # use default field color map by pyart
# cmp = pyart.config.get_field_colormap('differential_reflectivity')
# display.plot('cor_Zdr', swp, title='$Z_{DR}$ (corrected)',
#             axislabels=('East West distance from radar (km)', ''),
#             vmin=-10, vmax=10, colorbar_label='',cmap=cmp, ax=ax)
# display.set_limits(xlim=(-200, 200), ylim=(-200, 200), ax=ax)

# # %%
# fig.savefig('test_data_qc4qpe.png',dpi=350,bbox_inches='tight')

# %%
