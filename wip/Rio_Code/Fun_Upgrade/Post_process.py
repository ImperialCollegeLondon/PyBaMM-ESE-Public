""" Functions for post-processing - extract output 
variables from pybamm object to customized dictionary and class"""
import csv, random, os
import numpy as np
import pandas as pd
import pybamm as pb
import matplotlib.pyplot as plt
from .Fun_Upgrade import *

# Update 231117 new method to get throughput capacity to avoid problems of empty solution
def Get_ThrCap(sol_PRT): 
    thr_tot = 0
    for cycle in sol_PRT.cycles:
        for step in cycle.steps:
            # print(type(step))
            if not isinstance(step,pb.solvers.solution.EmptySolution):
                thr_i = np.trapz(
                    abs(step["Current [A]"].entries), 
                    step["Time [h]"].entries)
                thr_tot += thr_i
    return thr_tot

def Get_Last_state(Model, Sol):
    dict_short = {}
    list_short = []
    # update 220808 to satisfy random model option:
    for var, equation in Model.initial_conditions.items():
        #print(var._name)
        list_short.append(var._name)
    # delete Porosity times concentration and Electrolyte potential then add back
    list_short.remove("Porosity times concentration [mol.m-3]");
    list_short.remove("Electrolyte potential [V]");
    list_short.extend(
        ("Negative electrode porosity times concentration [mol.m-3]",
        "Separator porosity times concentration [mol.m-3]",
        "Positive electrode porosity times concentration [mol.m-3]",   

        "Negative electrolyte potential [V]",
        "Separator electrolyte potential [V]",
        "Positive electrolyte potential [V]",))
    for list_short_i in list_short:
        dict_short.update( { list_short_i : Sol.last_state[list_short_i].data  } )
    return list_short,dict_short

# Define a function to calculate concentration change, whether electrolyte being squeezed out or added in
def Cal_new_con_Update(Sol,Para):   # subscript r means the reservoir
    # Note: c_EC_r is the initial EC  concentraiton in the reservoir; 
    #       c_e_r  is the initial Li+ concentraiton in the reservoir;
    #############################################################################################################################  
    ###############################           Step-1 Prepare parameters:        #################################################
    #############################################################################################################################  
    L_p   =Para["Positive electrode thickness [m]"]
    L_n   =Para["Negative electrode thickness [m]"]
    L_s   =Para["Separator thickness [m]"]
    L_y   =Para["Electrode width [m]"]   # Also update to change A_cc and therefore Q
    L_z   =Para["Electrode height [m]"]
    c_EC_r_old=Para["Current solvent concentration in the reservoir [mol.m-3]"]   # add two new parameters for paper 2
    c_e_r_old =Para["Current electrolyte concentration in the reservoir [mol.m-3]"]
    # Initial EC concentration in JR
    c_EC_JR_old =Para["Bulk solvent concentration [mol.m-3]"]  # Be careful when multiplying with pore volume to get amount in mole. Because of electrolyte dry out, that will give more amount than real.   
    # LLI due to electrode,Ratio of EC and lithium is 1:1 -> EC amount consumed is LLINegSEI[-1]
    LLINegSEI = (
        Sol["Loss of lithium to SEI [mol]"].entries[-1] 
        - Sol["Loss of lithium to SEI [mol]"].entries[0] )
    LLINegSEIcr = (
        Sol["Loss of lithium to SEI on cracks [mol]"].entries[-1]
        - 
        Sol["Loss of lithium to SEI on cracks [mol]"].entries[0]
        )
    LLINegDeadLiP = (
        Sol["Loss of lithium to dead lithium plating [mol]"].entries[-1] 
        - Sol["Loss of lithium to dead lithium plating [mol]"].entries[0])
    LLINegLiP = (
        Sol["Loss of lithium to lithium plating [mol]"].entries[-1] 
        - Sol["Loss of lithium to lithium plating [mol]"].entries[0])
    cLi_Xavg  = Sol["X-averaged electrolyte concentration [mol.m-3]"].entries[-1] 
    # Pore volume change with time:
    PoreVolNeg_0 = Sol["X-averaged negative electrode porosity"].entries[0]*L_n*L_y*L_z;
    PoreVolSep_0 = Sol["X-averaged separator porosity"].entries[0]*L_s*L_y*L_z;
    PoreVolPos_0 = Sol["X-averaged positive electrode porosity"].entries[0]*L_p*L_y*L_z;
    PoreVolNeg_1 = Sol["X-averaged negative electrode porosity"].entries[-1]*L_n*L_y*L_z;
    PoreVolSep_1 = Sol["X-averaged separator porosity"].entries[-1]*L_s*L_y*L_z;
    PoreVolPos_1 = Sol["X-averaged positive electrode porosity"].entries[-1]*L_p*L_y*L_z;
    #############################################################################################################################  
    ##### Step-2 Determine How much electrolyte is added (from the reservoir to JR) or squeezed out (from JR to reservoir) ######
    #######################   and finish electrolyte mixing     #################################################################  
    Vol_Elely_Tot_old = Para["Current total electrolyte volume in whole cell [m3]"] 
    Vol_Elely_JR_old  = Para["Current total electrolyte volume in jelly roll [m3]"] 
    if Vol_Elely_Tot_old - Vol_Elely_JR_old < 0:
        print('Model error! Electrolyte in JR is larger than in the cell!')
    Vol_Pore_tot_old  = PoreVolNeg_0 + PoreVolSep_0 + PoreVolPos_0    # pore volume at start time of the run
    Vol_Pore_tot_new  = PoreVolNeg_1 + PoreVolSep_1 + PoreVolPos_1    # pore volume at end   time of the run, intrinsic variable 
    Vol_Pore_decrease = Vol_Elely_JR_old  - Vol_Pore_tot_new # WHY Vol_Elely_JR_old not Vol_Pore_tot_old here? Because even the last state of the last solution (n-1) and the first state of the next solution (n) can be slightly different! 
    # EC:lithium:SEI=2:2:1     for SEI=(CH2OCO2Li)2, but because of too many changes are required, change to 2:1:1 for now
    # update 230703: Simon insist we should do: EC:lithium:SEI  =  2:2:1 and change V_SEI accordingly 
    # Because inner and outer SEI partial molar volume is the same, just set one for whole SEI
    VmolSEI   = Para["Outer SEI partial molar volume [m3.mol-1]"] # 9.8e-5,
    VmolLiP   = Para["Lithium metal partial molar volume [m3.mol-1]"] # 1.3e-05
    VmolEC    = Para["EC partial molar volume [m3.mol-1]"]
    #################   KEY EQUATION FOR DRY-OUT MODEL                   #################
    # UPDATE 230525: assume the formation of dead lithium doesn’t consumed EC
    Vol_EC_consumed  =  ( LLINegSEI + LLINegSEIcr   ) * 1 * VmolEC    # Mark: either with 2 or not, will decide how fast electrolyte being consumed!
    Vol_Elely_need   = Vol_EC_consumed - Vol_Pore_decrease
    Vol_SEILiP_increase = 0.5*(
        (LLINegSEI+LLINegSEIcr) * VmolSEI 
        #+ LLINegLiP * VmolLiP
        )    #  volume increase due to SEI+total LiP 
    #################   KEY EQUATION FOR DRY-OUT MODEL                   #################

    Test_V = Vol_SEILiP_increase - Vol_Pore_decrease  #  This value should always be zero, but now not, which becomes the source of error!
    Test_V2= (Vol_Pore_tot_old - Vol_Elely_JR_old) / Vol_Elely_JR_old * 100; # Porosity errors due to first time step
    
    # Start from here, there are serveral variables to be determined:
    #   1) Vol_Elely_add, or Vol_Elely_squeezed; depends on conditions. easier for 'squeezed' condition
    #   2) Vol_Elely_Tot_new, should always equals to Vol_Elely_Tot_old -  Vol_EC_consumed;
    #   3) Vol_Elely_JR_new, for 'add' condition: see old code; for 'squeezed' condition, equals to pore volume in JR
    #   4) Ratio_Dryout, for 'add' condition: see old code; for 'squeezed' condition, equals to Vol_Elely_Tot_new/Vol_Pore_tot_new 
    #   5) Ratio_CeEC_JR and Ratio_CeLi_JR: for 'add' condition: see old code; for 'squeezed' condition, equals to 1 (unchanged)
    #   6) c_e_r_new and c_EC_r_new: for 'add' condition: equals to old ones (unchanged); for 'squeezed' condition, need to carefully calculate     
    #   7) Width_new: for 'add' condition: see old code; for 'squeezed' condition, equals to L_y (unchanged)
    Vol_Elely_Tot_new = Vol_Elely_Tot_old - Vol_EC_consumed;

    
    if Vol_Elely_need < 0:
        print('Electrolyte is being squeezed out, check plated lithium (active and dead)')
        Vol_Elely_squeezed = - Vol_Elely_need;   # Make Vol_Elely_squeezed>0 for simplicity 
        Vol_Elely_add = 0.0;
        Vol_Elely_JR_new = Vol_Pore_tot_new; 
        Ratio_Dryout = Vol_Elely_Tot_new / Vol_Elely_JR_new
        Ratio_CeEC_JR = 1.0;    # the concentrations in JR don't need to change
        Ratio_CeLi_JR = 1.0; 
        SqueezedLiMol   =  Vol_Elely_squeezed*cLi_Xavg;
        SqueezedECMol   =  Vol_Elely_squeezed*c_EC_JR_old;
        Vol_Elely_reservoir_old = Vol_Elely_Tot_old - Vol_Elely_JR_old; 
        LiMol_reservoir_new = Vol_Elely_reservoir_old*c_e_r_old  + SqueezedLiMol;
        ECMol_reservoir_new = Vol_Elely_reservoir_old*c_EC_r_old + SqueezedECMol;
        c_e_r_new= LiMol_reservoir_new / (Vol_Elely_reservoir_old+Vol_Elely_squeezed);
        c_EC_r_new= ECMol_reservoir_new / (Vol_Elely_reservoir_old+Vol_Elely_squeezed);
        Width_new = L_y; 
    else:   # this means Vol_Elely_need >= 0, therefore the folliwing script should works for Vol_Elely_need=0 as well!
        # Important: Calculate added electrolyte based on excessive electrolyte, can be: 1) added as required; 2) added some, but less than required; 3) added 0 
        Vol_Elely_squeezed = 0;  
        if Vol_Elely_Tot_old > Vol_Elely_JR_old:                             # This means Vol_Elely_JR_old = Vol_Pore_tot_old ()
            if Vol_Elely_Tot_old-Vol_Elely_JR_old >= Vol_Elely_need:         # 1) added as required
                Vol_Elely_add     = Vol_Elely_need;  
                Vol_Elely_JR_new  = Vol_Pore_tot_new;  # also equals to 'Vol_Pore_tot_new', or Vol_Pore_tot_old - Vol_Pore_decrease
                Ratio_Dryout = 1.0;
            else:                                                            # 2) added some, but less than required;                                                         
                Vol_Elely_add     = Vol_Elely_Tot_old - Vol_Elely_JR_old;   
                Vol_Elely_JR_new  = Vol_Elely_Tot_new;                       # This means Vol_Elely_JR_new <= Vol_Pore_tot_new
                Ratio_Dryout = Vol_Elely_JR_new/Vol_Pore_tot_new;
        else:                                                                # 3) added 0 
            Vol_Elely_add = 0;
            Vol_Elely_JR_new  = Vol_Elely_Tot_new; 
            Ratio_Dryout = Vol_Elely_JR_new/Vol_Pore_tot_new;

        # Next: start mix electrolyte based on previous defined equation
        # Lithium amount in liquid phase, at initial time point
        TotLi_Elely_JR_Old = Sol["Total lithium in electrolyte [mol]"].entries[-1]; # remember this is only in JR
        # Added lithium and EC amount in the added lithium electrolyte: - 
        AddLiMol   =  Vol_Elely_add*c_e_r_old
        AddECMol   =  Vol_Elely_add*c_EC_r_old
        # Total amount of Li and EC in current electrolyte:
        # Remember Li has two parts, initial and added; EC has three parts, initial, consumed and added
        TotLi_Elely_JR_New   = TotLi_Elely_JR_Old + AddLiMol
        TotECMol_JR   = Vol_Elely_JR_old*c_EC_JR_old - LLINegSEI + AddECMol  # EC:lithium:SEI=2:2:1     for SEI=(CH2OCO2Li)2
        Ratio_CeEC_JR  = TotECMol_JR    /   Vol_Elely_JR_new   / c_EC_JR_old
        Ratio_CeLi_JR  = TotLi_Elely_JR_New    /   TotLi_Elely_JR_Old   /  Ratio_Dryout # Mark, change on 21-11-19
        c_e_r_new  = c_e_r_old;
        c_EC_r_new = c_EC_r_old;
        Width_new   = Ratio_Dryout * L_y;
        
    # Collect the above parameter in DryOut_List to shorten the code  
    DryOut_List   = [
        Vol_EC_consumed, 
        Vol_Elely_need, 
        Test_V, 
        Test_V2, 
        Vol_Elely_add, 
        Vol_Elely_Tot_new, 
        Vol_Elely_JR_new, 
        Vol_Pore_tot_new, 
        Vol_Pore_decrease, 
        c_e_r_new, c_EC_r_new,
        Ratio_Dryout, Ratio_CeEC_JR, 
        Ratio_CeLi_JR,
        Width_new, 
        ]  # 16 in total
    #print('Loss of lithium to negative SEI', LLINegSEI, 'mol') 
    #print('Loss of lithium to dead lithium plating', LLINegDeadLiP, 'mol') 
    #############################################################################################################################  
    ###################       Step-4 Update parameters here        ##############################################################
    #############################################################################################################################
    Para.update(   
        {'Bulk solvent concentration [mol.m-3]':  
         c_EC_JR_old * Ratio_CeEC_JR  })
    Para.update(
        {'EC initial concentration in electrolyte [mol.m-3]':
         c_EC_JR_old * Ratio_CeEC_JR },) 
    Para.update(   
        {'Ratio of Li-ion concentration change in electrolyte consider solvent consumption':  
        Ratio_CeLi_JR }, check_already_exists=False) 
    Para.update(   
        {'Current total electrolyte volume in whole cell [m3]':  Vol_Elely_Tot_new  }, 
        check_already_exists=False)
    Para.update(   
        {'Current total electrolyte volume in jelly roll [m3]':  Vol_Elely_JR_new  }, 
        check_already_exists=False)
    Para.update(   
        {'Ratio of electrolyte dry out in jelly roll':Ratio_Dryout}, 
        check_already_exists=False)
    Para.update(   {'Electrode width [m]':Width_new})    
    Para.update(   
        {'Current solvent concentration in the reservoir [mol.m-3]':c_EC_r_new}, 
        check_already_exists=False)     
    Para.update(   
        {'Current electrolyte concentration in the reservoir [mol.m-3]':c_e_r_new}, 
        check_already_exists=False)             
    return DryOut_List,Para



# update 230312: add a function to get the discharge capacity and resistance
def Get_0p1s_R0(sol_RPT,cap_full):
    Index = np.arange(1,25,1)  # TODO add this into config
    Res_0p1s = []; SOC = [100,];
    for i,index in enumerate(Index):
        cycle = sol_RPT.cycles[index]
        Res_0p1s.append(   (
            np.mean(cycle.steps[1]["Terminal voltage [V]"].entries[-10:-1])
            - cycle.steps[2]["Terminal voltage [V]"].entries[0]
        ) / cycle.steps[2]["Current [A]"].entries[0] * 1000)
        if i > 0:
            Dis_Cap = abs(
                cycle.steps[2]["Discharge capacity [A.h]"].entries[0] 
                - cycle.steps[2]["Discharge capacity [A.h]"].entries[-1] )
            SOC.append(SOC[-1]-Dis_Cap/cap_full*100)
    return Res_0p1s[12],Res_0p1s,SOC

# update 230517 add a function to get R_50%SOC from C/2 discharge
def Get_R_from_0P5C_CD(step_0P5C_CD,cap_full):
    # print("Total data points: ",len(step_0P5C_CD["Time [h]"].entries))
    Dis_Cap = abs(
        step_0P5C_CD["Discharge capacity [A.h]"].entries[0] 
        - step_0P5C_CD["Discharge capacity [A.h]"].entries )
    SOC_0p5C = (1-Dis_Cap/cap_full)*100
    #print(SOC_0p5C)
    V_ohmic = (
    step_0P5C_CD['Battery open-circuit voltage [V]'].entries 
    - step_0P5C_CD["Terminal voltage [V]"].entries
    + step_0P5C_CD["Battery particle concentration overpotential [V]"].entries 
    + step_0P5C_CD["X-averaged battery concentration overpotential [V]" ].entries
    )
    # print("Applied current [A]:",step_0P5C_CD["Current [A]"].entries[0])
    Res_0p5C = V_ohmic/step_0P5C_CD["Current [A]"].entries[0] * 1e3
    Res_0p5C_50SOC = np.interp(50,np.flip(SOC_0p5C),np.flip(Res_0p5C),)
    SOC_0p5C = SOC_0p5C.tolist()
    Res_0p5C = Res_0p5C.tolist()
    Res_0p5C_50SOC = Res_0p5C_50SOC.tolist()
    return Res_0p5C_50SOC,Res_0p5C,SOC_0p5C  #,Rohmic_CD_2


# Update 23-05-18 Compare MPE - code created by ChatGPT
def mean_percentage_error(A, B):
    if 0 in A:
        indices = np.where(A == 0)[0]
        A = np.delete(A, indices)
        B = np.delete(B, indices)
        print(A,B)
    errors = np.abs(A - B) / np.abs(A)
    mpe = np.mean(errors) * 100
    return mpe

# Update 23-05-18
# compare modelling result with modelling:
# idea: do interpolation following TODO this is where weighting works
# initial:: X_1_st,X_5_st,Y_1_st_avg,Y_2_st_avg,Y_3_st_avg,Y_4_st_avg,Y_5_st_avg
# to compare: my_dict_RPT
def Compare_Exp_Model(task_result, config):
    
    # Unpack:
    my_dict_RPT = task_result.my_dict_RPT
    Scan_No = config.Scan_No
    Re_No = config.global_config.Re_No
    fs = config.global_config.fs
    dpi = config.global_config.dpi
    Exp_No = config.exp_config.Exp_No
    Age_T_in_K = config.exp_config.Exp_No
    BasicPath_Save = config.path_config.BasicPath_Save
    Target = config.path_config.Target
    XY_pack = config.expData_config.XY_pack



    [X_1_st,X_5_st,Y_1_st_avg,Y_2_st_avg,
        Y_3_st_avg,Y_4_st_avg,Y_5_st_avg,Y_6_st_avg] = XY_pack
    mX_1 = my_dict_RPT['Throughput capacity [kA.h]']
    if mX_1[-1] > X_1_st[-1]:
        punish = 1; 
        mX_1_st = X_1_st   # do interpolation on modelling result
        mY_1_st = np.interp(mX_1_st,my_dict_RPT['Throughput capacity [kA.h]'], 
            my_dict_RPT['CDend SOH [%]'])
        mY_2_st = np.interp(mX_1_st,my_dict_RPT['Throughput capacity [kA.h]'], 
            my_dict_RPT["CDend LLI [%]"])
        mY_3_st = np.interp(mX_1_st,my_dict_RPT['Throughput capacity [kA.h]'], 
            my_dict_RPT["CDend LAM_ne [%]"])
        mY_4_st = np.interp(mX_1_st,my_dict_RPT['Throughput capacity [kA.h]'], 
            my_dict_RPT["CDend LAM_pe [%]"])
        mY_6_st = np.interp(mX_1_st,my_dict_RPT['Throughput capacity [kA.h]'], 
            my_dict_RPT["avg_Age_T"])
        # experiment result remain unchanged
        Y_1_st_avgm = Y_1_st_avg
        Y_2_st_avgm = Y_2_st_avg
        Y_3_st_avgm = Y_3_st_avg
        Y_4_st_avgm = Y_4_st_avg
        Y_6_st_avgm = Y_6_st_avg
    else:                # do interpolation on expeirment results
        punish = X_1_st[-1] / mX_1[-1]  # punishment error, add when simulation end early
        mX_1_st = mX_1 #  standard for experiment following modelling
        Y_1_st_avgm = np.interp(mX_1_st,X_1_st,Y_1_st_avg)
        Y_2_st_avgm = np.interp(mX_1_st,X_1_st,Y_2_st_avg)
        Y_3_st_avgm = np.interp(mX_1_st,X_1_st,Y_3_st_avg)
        Y_4_st_avgm = np.interp(mX_1_st,X_1_st,Y_4_st_avg)
        Y_6_st_avgm = np.interp(mX_1_st,X_1_st,Y_6_st_avg)
        mY_1_st = my_dict_RPT['CDend SOH [%]']
        mY_2_st = my_dict_RPT["CDend LLI [%]"]
        mY_3_st = my_dict_RPT["CDend LAM_ne [%]"]
        mY_4_st = my_dict_RPT["CDend LAM_pe [%]"]
        mY_6_st = my_dict_RPT["avg_Age_T"]
    if mX_1[-1] > X_5_st[-1]:
        mX_5_st = X_5_st   
        mY_5_st = np.interp(mX_5_st,my_dict_RPT['Throughput capacity [kA.h]'], 
            my_dict_RPT["Res_midSOC"])
        Y_5_st_avgm = Y_5_st_avg
    else:
        mX_5_st = mX_1 #  standard for experiment following modelling
        mY_5_st = my_dict_RPT["Res_midSOC"]
        Y_5_st_avgm = np.interp(mX_5_st,X_5_st,Y_5_st_avg)
    # Now we can calculate MPE! mean_percentage_error
    mpe_1 = np.sum(abs(np.array(Y_1_st_avgm)-np.array(mY_1_st)))/len(Y_1_st_avgm) # SOH [%]
    mpe_2 = np.sum(abs(np.array(Y_2_st_avgm)-np.array(mY_2_st)))/len(Y_2_st_avgm) # LLI [%]
    mpe_3 = np.sum(abs(np.array(Y_3_st_avgm)-np.array(mY_3_st)))/len(Y_3_st_avgm) # LAM_ne [%]
    mpe_4 = np.sum(abs(np.array(Y_4_st_avgm)-np.array(mY_4_st)))/len(Y_4_st_avgm) # LAM_pe [%]
    mpe_5 = mean_percentage_error(Y_5_st_avgm, mY_5_st) # Res_midSOC
    mpe_6 = mean_percentage_error(Y_6_st_avgm, mY_6_st) # Age set average temperature (degC)
    # total MPE: TODO this is where weighting works
    # SOH and Resistance are directly measured so give more weight; 
    # DMA result is derived from pOCV and come with certain errors
    mpe_tot = (
        0.55*mpe_1 + 0.1*(mpe_2+mpe_3+mpe_4) 
        + 0.15*mpe_5 + 0.15* mpe_6 +
        (punish>1.0)* punish * 2 )
    
    # plot and check:
    fig, axs = plt.subplots(5,1, figsize=(6,13),tight_layout=True)
    axs[0].plot(mX_1_st, mY_1_st,'-o', label="Model" )
    axs[0].plot(mX_1_st, Y_1_st_avgm,'-o', label="Exp"  )
    axs[1].plot(mX_1_st, mY_2_st,'-o', label="Model" )
    axs[1].plot(mX_1_st, Y_2_st_avgm,'-o', label="Exp"  )
    axs[2].plot(mX_1_st, mY_3_st,'-o', label="Model" )
    axs[2].plot(mX_1_st, Y_3_st_avgm,'-o', label="Exp"  )
    axs[3].plot(mX_1_st, mY_4_st,'-o', label="Model" )
    axs[3].plot(mX_1_st, Y_4_st_avgm,'-o', label="Exp"  )
    axs[4].plot(mX_5_st, mY_5_st,'-o', label="Model" )
    axs[4].plot(mX_5_st, Y_5_st_avgm,'-o', label="Exp"  )
    axs[0].legend()
    axs[0].set_ylabel("SOH %")
    axs[1].set_ylabel("LLI %")
    axs[2].set_ylabel("LAM NE %")
    axs[3].set_ylabel("LAM PE %")
    axs[4].set_ylabel(r"Lump resistance [m$\Omega$]")
    axs[4].set_xlabel("Charge Throughput (kA.h)")
    fig.suptitle(
        f"Scan {str(Scan_No)}-Exp-{Exp_No}-{str(int(Age_T_in_K-273.15))}"
        +r"$^\circ$C - Calculate Error", fontsize=fs+2)
    plt.savefig(BasicPath_Save + Target
        +"Plots/"+ f"Scan {str(Scan_No)}_Re_{Re_No}-Exp-{Exp_No}-{str(int(Age_T_in_K-273.15))}degC"
        +r"- Calculate Error.png", dpi=dpi)
    plt.close()  # close the figure to save RAM


    mpe_all = np.around(
        [
            mpe_tot,mpe_1,mpe_2,
            mpe_3,mpe_4,mpe_5,mpe_6,
            punish],2)
    return mpe_all


# Evaluate errors systematically:
def Evaluate_MPE_with_ExpData(task_result,config):
    Exp_No = config.exp_config.Exp_No
    Age_T_in_K = config.exp_config.Age_T_in_K
    Keys_error = task_result.Keys_error

    if Exp_No in np.arange(1, 6) and \
        int(Age_T_in_K - 273.15) in [10, 25, 40]:

        config.Get_Cell_Mean_1T_1Exp()  # XY_pack
        mpe_all = Compare_Exp_Model(task_result, config)
    else:

        config.XY_pack         = "nan"
        mpe_all         = [np.nan]*8

    for mpe_i,key in zip(mpe_all,Keys_error):
        task_result.my_dict_RPT[key] =  mpe_i
    # [mpe_tot,mpe_1,mpe_2,mpe_3,mpe_4,mpe_5,mpe_6,punish] = mpe_all
    # set pass or fail TODO figure out how much should be appropriate:
    if isinstance(mpe_all[0],float): # is mpe_tot
        if mpe_all[0] < 3:
            Pass_Fail = "Pass"
        else:
            Pass_Fail = "Fail"
    else:
        Pass_Fail = f"Not Exp"
    task_result.Pass_Fail = Pass_Fail
    task_result.mpe_all = mpe_all
    return task_result

# Add 220808 - to simplify the post-processing
def GetSol_dict (my_dict, keys_all, Sol, 
    cycle_no,step_CD, step_CC , step_RE, step_CV ):

    [keys_loc,keys_tim,keys_cyc]  = keys_all;
    # get time_based variables:
    if len(keys_tim): 
        for key in keys_tim:
            step_no = eval("step_{}".format(key[0:2]))
            if key[3:] == "Time [h]":
                my_dict[key].append  (  (
                    Sol.cycles[cycle_no].steps[step_no][key[3:]].entries
                    -
                    Sol.cycles[cycle_no].steps[step_no][key[3:]].entries[0]).tolist()  )
            elif key[3:] == "Anode potential [V]":
                sol_step = Sol.cycles[cycle_no].steps[step_no]
                mesh_sep = len(sol_step["Separator electrolyte potential [V]"].entries[:,0])
                if mesh_sep % 2 ==0:
                    phi_ref = (
                        sol_step["Separator electrolyte potential [V]"].entries[mesh_sep//2-1,:]
                        +
                        sol_step["Separator electrolyte potential [V]"].entries[mesh_sep//2+1,:]
                        ) / 2
                    #print(mesh_sep/2+0.5)
                else:
                    phi_ref = sol_step["Separator electrolyte potential [V]"].entries[mesh_sep//2,:]
                V_n = -phi_ref 
                my_dict[key].append(  V_n.tolist()  )
            elif key[3:] == "Cathode potential [V]":
                sol_step = Sol.cycles[cycle_no].steps[step_no]
                mesh_sep = len(sol_step["Separator electrolyte potential [V]"].entries[:,0])
                if mesh_sep % 2 ==0:
                    phi_ref = (
                        sol_step["Separator electrolyte potential [V]"].entries[mesh_sep//2-1,:]
                        +
                        sol_step["Separator electrolyte potential [V]"].entries[mesh_sep//2+1,:]
                        ) / 2
                    #print(mesh_sep/2+0.5)
                else:
                    phi_ref = sol_step["Separator electrolyte potential [V]"].entries[mesh_sep//2,:]
                V =  sol_step["Terminal voltage [V]"].entries
                V_p = V - phi_ref   
                my_dict[key].append(  V_p.tolist()  )
            else:
                my_dict[key].append(  (
                    Sol.cycles[cycle_no].steps[step_no][key[3:]].entries).tolist()  )
    # get cycle_step_based variables: # isn't an array
    if len(keys_cyc): 
        for key in keys_cyc:
            if key in ["Discharge capacity [A.h]"]:
                step_no = step_CD;
                my_dict[key].append  (
                    Sol.cycles[cycle_no].steps[step_no][key].entries[-1]
                    - 
                    Sol.cycles[cycle_no].steps[step_no][key].entries[0])
            elif key in ["Throughput capacity [A.h]"]: # 
                i_try = 0
                while i_try<3:
                    try:
                        getSth = Sol[key].entries[-1]
                    except:
                        i_try += 1
                        print(f"Fail to read Throughput capacity for the {i_try}th time")
                    else:
                        break
                my_dict[key].append(abs(getSth))
            elif key[0:5] in ["CDend","CCend","CVend","REend",
                "CDsta","CCsta","CVsta","REsta",]:
                step_no = eval("step_{}".format(key[0:2]))
                if key[2:5] == "sta":
                    my_dict[key].append  (
                        Sol.cycles[cycle_no].steps[step_no][key[6:]].entries[0])
                elif key[2:5] == "end":
                    my_dict[key].append  (
                        Sol.cycles[cycle_no].steps[step_no][key[6:]].entries[-1])
                
    # get location_based variables:
    if len(keys_loc): 
        for key in keys_loc:
            if key in ["x_n [m]","x [m]","x_s [m]","x_p [m]"]:
                #print("These variables only add once")
                if not len(my_dict[key]):   # special: add only once
                    my_dict[key] = (Sol[key].entries[:,-1]).tolist()
            elif key[0:5] in ["CDend","CCend","CVend","REend",
                            "CDsta","CCsta","CVsta","REsta",]:      
                #print("These variables add multiple times")
                step_no = eval("step_{}".format(key[0:2]))
                if key[2:5] == "sta":
                    my_dict[key].append  ((
                        Sol.cycles[cycle_no].steps[step_no][key[6:]].entries[:,0]).tolist() )
                elif key[2:5] == "end":
                    my_dict[key].append ( (
                        Sol.cycles[cycle_no].steps[step_no][key[6:]].entries[:,-1]).tolist()  )
    return my_dict                              

def Get_SOH_LLI_LAM(task_result,config):

    my_dict_RPT = task_result.my_dict_RPT
    model_options = config.model_config.model_options
    DryOut = config.model_config.DryOut
    mdic_dry = task_result.mdic_dry
    cap_0 = config.expData_config.cap_0

    my_dict_RPT['Throughput capacity [kA.h]'] = (
        np.array(my_dict_RPT['Throughput capacity [A.h]'])/1e3).tolist()
    my_dict_RPT['CDend SOH [%]'] = ((
        np.array(my_dict_RPT["Discharge capacity [A.h]"])
        /
        cap_0       # my_dict_RPT["Discharge capacity [A.h]"][0] # Mark: change to this so that every case has same standard for reservior paper
        )*100).tolist()
    my_dict_RPT["CDend LAM_ne [%]"] = ((1-
        np.array(my_dict_RPT['CDend Negative electrode capacity [A.h]'])
        /my_dict_RPT['CDend Negative electrode capacity [A.h]'][0])*100).tolist()
    my_dict_RPT["CDend LAM_pe [%]"] = ((1-
        np.array(my_dict_RPT['CDend Positive electrode capacity [A.h]'])
        /my_dict_RPT['CDend Positive electrode capacity [A.h]'][0])*100).tolist()
    my_dict_RPT["CDend LLI [%]"] = ((1-
        np.array(my_dict_RPT["CDend Total lithium capacity in particles [A.h]"])
        /my_dict_RPT["CDend Total lithium capacity in particles [A.h]"][0])*100).tolist()
    if model_options.__contains__("SEI"):
        my_dict_RPT["CDend LLI SEI [%]"] = ((
            np.array(
                my_dict_RPT["CDend Loss of capacity to SEI [A.h]"]-
                my_dict_RPT["CDend Loss of capacity to SEI [A.h]"][0]
                )
            /my_dict_RPT["CDend Total lithium capacity in particles [A.h]"][0])*100).tolist()
    else:
        my_dict_RPT["CDend LLI SEI [%]"] = (
            np.zeros(
                np.size(
                    my_dict_RPT["CDend LLI [%]"]))).tolist()
    if model_options.__contains__("SEI on cracks"):
        my_dict_RPT["CDend LLI SEI on cracks [%]"] = ((
            np.array(
                my_dict_RPT["CDend Loss of capacity to SEI on cracks [A.h]"]-
                my_dict_RPT["CDend Loss of capacity to SEI on cracks [A.h]"][0]
                )
            /my_dict_RPT["CDend Total lithium capacity in particles [A.h]"][0])*100).tolist()
    else:
        my_dict_RPT["CDend LLI SEI on cracks [%]"] = (
            np.zeros(
                np.size(
                    my_dict_RPT["CDend LLI [%]"]))).tolist()
    if model_options.__contains__("lithium plating"):
        my_dict_RPT["CDend LLI lithium plating [%]"] = ((
            np.array(
                my_dict_RPT["CDend Loss of capacity to lithium plating [A.h]"]-
                my_dict_RPT["CDend Loss of capacity to lithium plating [A.h]"][0]
                )
            /my_dict_RPT["CDend Total lithium capacity in particles [A.h]"][0])*100).tolist()
    else:
        my_dict_RPT["CDend LLI lithium plating [%]"] =  (
            np.zeros(
                np.size(
                    my_dict_RPT["CDend LLI [%]"]))).tolist()    
    my_dict_RPT["CDend LLI due to LAM [%]"] = (
        np.array(my_dict_RPT['CDend LLI [%]'])
        -my_dict_RPT["CDend LLI SEI [%]"]
        -my_dict_RPT["CDend LLI lithium plating [%]"]
        -my_dict_RPT["CDend LLI SEI on cracks [%]"] )
    if DryOut == "On":
        LAM_to_Dry   = 100-np.array(
            mdic_dry['Width_all']) /mdic_dry['Width_all'][0]*100
        LAM_to_Dry_end=LAM_to_Dry[-1]
    else:
        LAM_to_Dry_end = 0
    LAM_to_Crack_NE_end=my_dict_RPT['CDend LAM_ne [%]'][-1]-LAM_to_Dry_end
    LAM_to_Crack_PE_end=my_dict_RPT['CDend LAM_pe [%]'][-1]-LAM_to_Dry_end
    my_dict_RPT["LAM_to_Dry [%] end"] = LAM_to_Dry_end
    my_dict_RPT["LAM_to_Crack_NE [%] end"] = LAM_to_Crack_NE_end
    my_dict_RPT["LAM_to_Crack_PE [%] end"] = LAM_to_Crack_PE_end
    task_result.my_dict_RPT = my_dict_RPT
    return task_result

# Update 240429: Define a new dictionary to write summary result into Excel file
def Write_Dict_to_Excel(
        task_result, config, log_messages):
    # unpack: 
    mpe_all = task_result.mpe_all
    Pass_Fail = task_result.Pass_Fail
    my_dict_RPT = task_result.my_dict_RPT
    mdic_dry = task_result.mdic_dry
    Flag_Breakin = task_result.Flag_Breakin

    Para_dict_i = config.para_config.Para_dict_i
    cap_0 = config.expData_config.cap_0
    BasicPath_Save = config.path_config.BasicPath_Save
    Target = config.path_config.Target
    Exp_No = config.exp_config.Exp_No
    model_options = config.model_config.model_options 
    DryOut = config.model_config.DryOut
    Scan_No = config.Scan_No

    str_exp_AGE_text = str(config.exp_config.exp_AGE_text)
    str_exp_RPT_text = str(config.exp_config.exp_RPT_text)
    str_error_AGE = task_result.str_error_AGE
    str_error_RPT = task_result.str_error_RPT


    book_name_xlsx = f'Re_{config.global_config.Re_No}_{config.path_config.purpose}.xlsx'
    # *mpe_all = [mpe_tot,mpe_1,mpe_2,mpe_3,mpe_4,mpe_5,mpe_6,punish]
    Dict_Excel = {}
    # 1 - start from basic summary information: pre
    keys_pre = [
        "Scan No","Exp No.","Y or N",
        "Error tot %","Error SOH %","Error LLI %",
        "Error LAM NE %","Error LAM PE %",
        "Error Res %","Error ageT %","Punish",
        "Dry out",]
    value_Pre = [
        Scan_No,Exp_No,Pass_Fail,
        *mpe_all,DryOut]
    for key, value in zip(keys_pre,value_Pre):
        Dict_Excel[key] = value
    # 2 - middle is input parameters
    Dict_Excel.update(Para_dict_i)  # include "Total ageing cycles", "Ageing cycles between RPT", 
    # 3 - Finally post-processing data, may be "nan"
    Dict_Excel["exp_AGE_text"] =  str_exp_AGE_text
    Dict_Excel["exp_RPT_text"] =  str_exp_RPT_text
    if Flag_Breakin: # break in cycle succeed:
        tot_char_throughput = my_dict_RPT['Throughput capacity [kA.h]'][-1]
        Dict_Excel["Throughput capacity [kA.h]"] =  tot_char_throughput
        Dict_Excel["CDend SOH [%]"] =  my_dict_RPT['CDend SOH [%]'][-1]
        Porosity = my_dict_RPT["CDend Porosity"][-1]
        x_n = my_dict_RPT["x_n [m]"]
        Dict_Excel["CDend Neg Porosity Sep side"] =  Porosity[len(x_n)-1]
        Dict_Excel["CDend LLI [%]"] =  my_dict_RPT["CDend LLI [%]"][-1]

        if model_options.__contains__("SEI on cracks"):
            Dict_Excel["LLI to sei-on-cracks [%]"] = my_dict_RPT["CDend LLI SEI on cracks [%]"][-1]
        else:
            Dict_Excel["LLI to sei-on-cracks [%]"] = 0.0
        if model_options.__contains__("lithium plating"):
            Dict_Excel["LLI to LiP [%]"] = my_dict_RPT["CDend LLI lithium plating [%]"][-1]
        else:
            Dict_Excel["LLI to LiP [%]"] = 0.0
        if model_options.__contains__("SEI"):
            Dict_Excel["LLI to SEI [%]"] = my_dict_RPT["CDend LLI SEI [%]"][-1]
        else:
            Dict_Excel["LLI to SEI [%]"] = 0.0
        Dict_Excel["CDend LLI due to LAM [%]"] = my_dict_RPT["CDend LLI due to LAM [%]"][-1]
        Dict_Excel["LAM_to_Crack_NE [%]"] = my_dict_RPT["LAM_to_Crack_NE [%] end"]
        Dict_Excel["LAM_to_Crack_PE [%]"] = my_dict_RPT["LAM_to_Crack_PE [%] end"]
        Dict_Excel["LAM_to_Dry [%]"] = my_dict_RPT["LAM_to_Dry [%] end"]
        Dict_Excel["CDend LAM_ne_tot [%]"] = my_dict_RPT["CDend LAM_ne [%]"][-1]
        Dict_Excel["CDend LAM_pe_tot [%]"] = my_dict_RPT["CDend LAM_pe [%]"][-1]
        
        # per kAh:
        Dict_Excel["Cap per kAh"]=(1-Dict_Excel["CDend SOH [%]"])*cap_0/tot_char_throughput
        Dict_Excel["LLI% per kAh"]=Dict_Excel["CDend LLI [%]"]/tot_char_throughput
        Dict_Excel["LAM_ne% per kAh"]=Dict_Excel["CDend LAM_ne_tot [%]"]/tot_char_throughput
        Dict_Excel["LAM_pe% per kAh"]=Dict_Excel["CDend LAM_pe_tot [%]"]/tot_char_throughput
        if DryOut == "On":
            Dict_Excel["Vol_Elely_Tot_All_final"] = mdic_dry["Vol_Elely_Tot_All"][-1]
            Dict_Excel["Vol_Elely_JR_All_final"]  = mdic_dry["Vol_Elely_JR_All"][-1]
            Dict_Excel["Width_all_final"]         = mdic_dry["Width_all"][-1]
        else:
            Dict_Excel["Vol_Elely_Tot_All_final"] = np.nan
            Dict_Excel["Vol_Elely_JR_All_final"]  = np.nan
            Dict_Excel["Width_all_final"]         = np.nan
    else: # break in cycle fail:
        Keys_pos = [
            "Throughput capacity [kA.h]","CDend SOH [%]",
            "CDend Neg Porosity Sep side",
            "CDend LLI [%]","LLI to sei-on-cracks [%]",
            "LLI to LiP [%]","LLI to SEI [%]",
            "CDend LLI due to LAM [%]","LAM_to_Crack_NE [%]",
            "LAM_to_Crack_PE [%]","LAM_to_Dry [%]",
            "CDend LAM_ne_tot [%]","CDend LAM_pe_tot [%]",
            "Cap per kAh","LLI% per kAh","LAM_ne% per kAh",
            "LAM_pe% per kAh","Vol_Elely_Tot_All_final",
            "Vol_Elely_JR_All_final","Width_all_final",
        ]
        for key in Keys_pos:
            Dict_Excel[key] = np.nan

    Dict_Excel["Error_AGE"] = str_error_AGE
    Dict_Excel["Error_RPT"] = str_error_RPT
    Dict_Excel["Log"] = log_messages
    # df_excel = pd.DataFrame(Dict_Excel)
    df_excel = pd.DataFrame([Dict_Excel])
    book_name_xlsx_seperate =   str(Scan_No)+ '_' + book_name_xlsx
    df_excel.to_excel(
        BasicPath_Save + Target + "Excel/" 
        +book_name_xlsx_seperate,
        index=False, engine='openpyxl')
    return 

import pickle
def Fun_Save_for_Reload(task_result,Model_Dry_old,Para_0_Dry_old,config):
    # unpack: 
    DryOut = config.model_config.DryOut
    Scan_No = config.Scan_No
    Re_No = config.global_config.Re_No

    midc_merge = [ 
        task_result.my_dict_RPT, task_result.my_dict_AGE, 
        task_result.mdic_dry]
    
    if isinstance(task_result.Sol_RPT[-1],pb.solvers.solution.Solution):
        _,dict_short = Get_Last_state(Model_Dry_old, task_result.Sol_RPT[-1])
        sol_last = task_result.Sol_RPT[-1]
    else:
        _,dict_short = Get_Last_state(Model_Dry_old, task_result.Sol_AGE[-1])
        sol_last = task_result.Sol_AGE[-1]
        print("!!!!!!!Big problem! The last RPT fails, "
            "need to restart from RPT next time")
    # calculate dry-out parameter first
    if DryOut == "On":
        DryOut_List,Paraupdate = Cal_new_con_Update(sol_last, Para_0_Dry_old)
    else: 
        Paraupdate = Para_0_Dry_old; DryOut_List = "nan"
    i_try = 0
    while i_try<3:
        try:
            getSth = sol_last['Throughput capacity [A.h]'].entries[-1] 
        except:
            i_try += 1
            print(f"Fail to read Throughput capacity for the {i_try}th time")
        else:
            break
    Save_for_Reload = [ midc_merge, dict_short, Paraupdate, DryOut_List, getSth]
    with open(
        config.path_config.BasicPath_Save + config.path_config.Target + 
        "Mats/" + str(Scan_No)+ f'_Re_{Re_No}-Save_for_Reload.pkl', 
        'wb') as file:
        pickle.dump(Save_for_Reload, file)
    return    


def Fun_Save_for_debug(task_result, config):
    Scan_No = config.Scan_No
    Re_No = config.global_config.Re_No

    DeBug_Lists = [
        task_result.DeBug_List_Breakin, 
        task_result.DeBug_List_AGE, 
        task_result.DeBug_List_RPT]
    with open(
        config.path_config.BasicPath_Save + config.path_config.Target 
        +"Mats/" + str(Scan_No) + f'_Re_{Re_No}-DeBug_Lists.pkl', 
        'wb') as file:
        pickle.dump(DeBug_Lists, file)
    return 



def Fun_Save_Partial_Age(task_result, config):
    # unpack: 
    Scan_No = config.Scan_No
    Re_No = config.global_config.Re_No
    Sol_AGE = task_result.Sol_AGE
    BasicPath_Save = config.path_config.BasicPath_Save
    Target = config.path_config.Target

    if task_result.Flag_partial_AGE == True:
        try:
            Sol_partial_AGE_list = [
                Sol_AGE[-1].cycles[0],    Sol_AGE[-1].cycles[-1],
                len(Sol_AGE[-1].cycles)]
        except IndexError:
            try:
                Sol_partial_AGE_list = [
                    Sol_AGE[-1].cycles[0],    Sol_AGE[-1].cycles[-2],
                    len(Sol_AGE[-1].cycles)]
            except IndexError:
                print("Problems in saving last two cycles in Sol_AGE[-1],"
                        " now saving the whole Sol_AGE[-1]")
                Sol_partial_AGE_list = [
                    Sol_AGE[-1],    "nan",
                    len(Sol_AGE[-1].cycles)]
        with open(
            BasicPath_Save + Target+"Mats/" + str(Scan_No)+ 
            f'_Re_{Re_No}-Sol_partial_AGE_list.pkl', 
            'wb') as file:
            pickle.dump(Sol_partial_AGE_list, file)
        print(f"Last AGE succeed partially, save Sol_partial_AGE_list.pkl for Scan {Scan_No} Re {Re_No}")
    else:
        pass
    return 


import shutil,os; import pandas as pd
def Copy_png(Path_Results, purpose_i, Path_Plot_Collect,
            rows_per_file, Scan_end_end):

    source_folders = []
    for i_bundle in range(int(Scan_end_end/rows_per_file)):
        Scan_start = (i_bundle)*rows_per_file+1;    
        Scan_end   = min(Scan_start + rows_per_file-1, Scan_end_end)    
        purpose = f"{purpose_i}_Case_{Scan_start}_{Scan_end}"
        source_folders.append(purpose)
        #print(purpose)

    # Initialize a list to store the results
    List_check_succeed = []

    # Move the .png files to the Plot_Collect folder
    for k,folder in enumerate(source_folders):
        plots_directory = os.path.join(
            Path_Results, folder, "Plots")
        if os.path.exists(plots_directory):
            if not os.listdir(plots_directory):
                print(f"The directory {folder} is empty, case {k+1} fail")
                List_check_succeed.append([k+1, False])
            else:
                for filename in os.listdir(plots_directory):
                    if filename.startswith("0_") and filename.endswith("Summary.png"):
                        source_file = os.path.join(plots_directory, filename)
                        destination_file = os.path.join(Path_Plot_Collect, filename)
                        shutil.copy(source_file, destination_file)
                List_check_succeed.append([k+1, True])
    df_succeed = pd.DataFrame(List_check_succeed, columns=["Case", "Succeed"])

    return df_succeed
























