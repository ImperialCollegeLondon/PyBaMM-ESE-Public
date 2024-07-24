""" 
This script is the baseline for main file to run functions from
GEM-2_Ruihe 
"""
# Load modules
import pybamm as pb;import pandas as pd;import numpy as np;
import os, json,openpyxl,traceback,multiprocessing,scipy.optimize,sys
import matplotlib.pyplot as plt;
import pickle,imageio,timeit,random,time, signal
from scipy.io import savemat,loadmat;
from pybamm import constants,exp;import matplotlib as mpl

########################     Global settings!!!
rows_per_file = 1;  Scan_end_end = 270  
purpose_i = "Full_Exp2_NC_SA" 


# define options:
On_HPC =  False;        Runshort=True;    Add_Rest = False
Plot_Exp=True;          Timeout=True;     Return_Sol=True;   
Check_Small_Time=True;  R_from_GITT = False
fs = 13; dpi = 100; Re_No =0
Options = [ 
    On_HPC,Runshort,Add_Rest,
    Plot_Exp,Timeout,Return_Sol,
    Check_Small_Time,R_from_GITT,
    dpi,fs]
Timelimit = int(3600*48) # give 48 hours!


if On_HPC:
    i_bundle = int(os.environ["PBS_ARRAY_INDEX"])
else:
    i_bundle = 9; 
Scan_start = (i_bundle-1)*rows_per_file+1;    
Scan_end   = min(Scan_start + rows_per_file-1, Scan_end_end)    
purpose = f"{purpose_i}_Case_{Scan_start}_{Scan_end}"
Target  = f'/{purpose}/'
# interpetation: Simnon suggested, with cracking activation, heat transfer
para_csv = f"Bundle_{i_bundle}.csv"  # name of the random file to get parameters

# Path setting:
if On_HPC:                          # Run on HPC
    Path_csv = f"InputData/{purpose_i}/" 
    Path_Input = "InputData/" 
    BasicPath=os.getcwd() 
    Para_file = Path_csv +  para_csv
else:
    # Add path to system to ensure Fun_P2 can be used
    import sys  
    str_path_0 = os.path.abspath(os.path.join(pb.__path__[0],'..'))
    str_path_1 = os.path.abspath(
        os.path.join(str_path_0,"wip/Rio_Code/Fun_P2"))
    sys.path.append(str_path_1) 
    Path_Input = os.path.expanduser(
        "~/EnvPBGEM_NC/SimSave/InputData/") # for Linux
    BasicPath =  os.path.expanduser(
        "~/EnvPBGEM_NC/SimSave/P2_R9_Dim")
    Para_file = Path_Input+f'{purpose_i}/'+para_csv
# import all functions 
from Fun_NC import * 


# Load input file
Para_dict_list = load_combinations_from_csv(Para_file)
pool_no = len(Para_dict_list) # do parallel computing if needed

midc_merge_all = [];  Sol_RPT_all = [];  Sol_AGE_all = []
Path_List = [BasicPath, Path_Input,Target,purpose] 
# Run the model
if Re_No == 0:
    midc_merge,Sol_RPT,Sol_AGE,DeBug_Lists = Run_P2_Excel (
        Para_dict_list[0], Path_List, 
        Re_No, Timelimit, Options) 
elif Re_No > 0:
    pass
