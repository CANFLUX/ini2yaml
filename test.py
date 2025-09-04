import os
import ini2yaml
import importlib
importlib.reload(ini2yaml)

# root = r'C:\Users\jskeeter\OneDrive - NRCan RNCan\Documents\DataTansfers'
root = r'C:\Users\jskeeter\gsc-permafrost'
root = 'C:\\'
old_ini_path = os.path.join(root,r'Database\Calculation_Procedures\TraceAnalysis_ini')
SiteID = 'DSM'
stage = 'firststage'
i2y = ini2yaml.parser(root=old_ini_path,SiteID=SiteID,stage=stage)
# print([l.strip() for l in i2y.text.split('\n')])
# print(i2y.config.globalVars)

# import yaml
# with open(os.path.join(old_ini_path,SiteID,f"{SiteID}_{stage}.yml")) as f:
#     print(yaml.safe_load(f))


# print(i2y.config['comments'])
# print(i2y.config.Include['RAD_FirstStage_include'])
# print(i2y.config.Trace['TA_1_1_1'])
# print(i2y.revised_text)
