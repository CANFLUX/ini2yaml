import os
import ini2yaml
import importlib
importlib.reload(ini2yaml)

# root = r'C:\Users\jskeeter\OneDrive - NRCan RNCan\Documents\DataTansfers'
root = r'C:\Users\jskeeter\gsc-permafrost'
# root = 'C:\\'
root = 'E:\\'
old_ini_path = os.path.join(root,r'Database\Calculation_Procedures\TraceAnalysis_ini')
siteList = ['BB','BB2','BBS','DSM','RBM','HOGG','OHM','YOUNG']
for SiteID in siteList:
    for stage in ['firststage','secondstage']:
        print(f'Site: {SiteID}, stage: {stage}')
        i2y = ini2yaml.parser(root=old_ini_path,SiteID=SiteID,stage=stage,fields_on_the_fly=True,verbose=False)