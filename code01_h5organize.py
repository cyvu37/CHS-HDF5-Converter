"""
StormSim: File 1
===
Converts specific HDF5 files from CHS databse.

About
---
code01_h5organize.py: Handles conversion for a file.

Author
---
Code by Jared Hidalgo. 
"""
import itertools, os, pickle, shutil, sys, time
from copy import deepcopy
from zipfile import ZipFile
from datetime import timedelta

import chime, h5py
import numpy as np
import pandas as pd
from PySide6.QtCore import (Qt, QAbstractTableModel, QDateTime, Signal)



DIR_RESULTS = f"{os.sep}".join( __file__.split( os.sep )[:-2] )
# For command line.
SPACES = "".join([" "]*20)
# Categories of units to add.
D_UNITS = {"Save Point Latitude": "Latitude Units",
           "Save Point Longitude": "Longitude Units",
           "Save Point Depth": "Save Point Depth Units"}
# Categories of data types to use.
D_COLTYPES = {"Save Point ID": int,
              "Save Point Latitude": float,
              "Save Point Longitude": float,
              "Save Point Depth": float,
              "Storm ID": int,
              "Storm Name": str,
              "Storm Type": str}



#
# Make a custom model for the QTableView window.
#
class TableModel(QAbstractTableModel):
    """
    Convert dataset to a displayable format for Data Viewer (right).
    """

    def __init__(self, data, parent=None, *args):
        QAbstractTableModel.__init__(self, parent, *args)
        self._data: pd.DataFrame = data
        """The original DataFrame"""
    
    def rowCount(self, index):
        return len(self._data.index)
    
    def columnCount(self, index):
        return len(self._data.columns)
    
    def data(self, index, role):
        """
        Set format for data object.
        """
        if role == Qt.ItemDataRole.DisplayRole and index.isValid():
            value = self._data.iloc[index.row(), index.column()]
            if isinstance(value, pd.Timestamp):
                return value.strftime("%m/%d/%Y, %I:%M %p")
            else:
                return str(value)
        return None
    
    def headerData(self, section, orientation, role):
        """
        Get headers.
        """
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return str(self._data.columns[section])
    
    def flags(self, index):
        """
        Set flags for each element.
        """
        return QAbstractTableModel.flags(self, index) | Qt.ItemFlag.ItemIsSelectable





class H5_Organized_New:
    """
    Ultimate class to store data from a CHS HDF5 file into a table format (aka a dataset).
    """
    setCurrentProgress = Signal(int)
    success = Signal(int)
    dec = 6

    has_datetime = False
    is_timeseries = False
    is_plottable = False
    is_aef_special = False
    is_locations = False
    more_steps = 0
    h5s = None
    
    df_current: pd.DataFrame
    df_full: pd.DataFrame
    is_cmd: bool



    def __init__(self):
        """Initialize class without conversion."""
        pass



    def run(self, fpath: str, will_export: bool, is_cmd: bool):
        """
        First function to process the HDF5 file. 
        
        If in ZIP file, a temporary HDF5 file will be extracted to the "Extracted" subdirectory.

        Parameters
        ---
        fpath: The complete filepath of the HDF5 file.
        will_export: Boolean for exporting the dataset right after conversion.
        is_cmd: Boolean for running this file from the command line (`True`) or the GUI (`False`).
        """
        self.df_normal = {}
        self.fpath = fpath
        x = fpath.split(";")[1] if ";" in fpath else fpath
        self.name = os.path.basename(x).split(".")[-2]
        self.export = will_export
        self.is_cmd = is_cmd
        self.end_print = "\r" if is_cmd else "\n" # NOTE: Test if we only need "\r".

        if will_export and not is_cmd: self.more_steps = 2  #    Exporting from GUI.
        elif will_export or not is_cmd: self.more_steps = 1 # 1) Exporting from CMD. 2) Only importing to GUI.

        # Extract info from filename.
        f_split = self.name.split("_")
        self.fileType = f_split[-1]
        self.is_timeseries = self.fileType == "Timeseries"
        self.is_plottable = self.fileType in ["Peaks", "Timeseries"]

        if ";" in fpath:
            fs = fpath.split(";")
            with ZipFile(fs[0]) as z:
                z.extract(fs[1], path="Extracted")
            f = "Extracted" + os.sep + fs[1]
        else:
            f = fpath
        h5 = h5py.File( f, 'r' )

        # Extract info.
        fileKeys = list(h5.keys())
        sZ = len(fileKeys)
        fileVals = h5.values()
        fileAttrs = dict(h5.attrs)
        first_val = h5[fileKeys[0]]
        has_groups = isinstance(first_val, h5py.Group)
        try: fileVersion = fileAttrs['CHS File Format'].decode('utf-8')
        except: fileVersion = "V1"
        
        # Version 3 -- ID1 = CHS-LA, CHS-NA, CHS-TX
        if fileVersion == "V3":
            # CASE 1 | ID7 = AEF(cond)
            if "AEF" in self.fileType:
                self._v3_AEF(h5, fileKeys)
        # Version 2 -- ID1 = SACSNCSEFL
        elif fileVersion == "V2":
            # CASE 2 | SACSNCSEFL_X_X_X_X_X_Peaks
            if self.fileType == "Peaks" and f_split[0] == "SACSNCSEFL":
                self._v2_SACSNCSEFL_Peaks(h5, fileKeys, fileAttrs, first_val)
            # CASE 3 | SACSNCSEFL_X_X_X_X_X_AEF(cond) with multiple groups --> Each group is an H5_Organized object.
            elif "AEF" in self.fileType:
                self._v2_SACSNCSEFL_AEF(list(fileVals), fileAttrs, sZ)
        # Version 1
        else:
            # CASE 4 | ID1 = [CHS-LA, CHS-NA, CHS-TX]; ID7 = Locations --> Split in 2.
            if self.fileType == "Locations":
                self._v1_Locations(h5)
            # CASE 5 | ID1 = [NACCS, SACSNCSEFL]; ID7 = Timeseries
            elif self.fileType == "Timeseries":
                self._v1_Timeseries(h5, fileKeys, list(fileVals), fileAttrs, sZ)
            # CASE 6 | NACCS_X_X_X_X_X_NLR
            elif self.fileType == "NLR":
                self._v1_NLR(h5, fileKeys)
            # CASE 7 | NACCS_X_X_X_X_X_SRR
            elif self.fileType == "SRR":
                self._v1_SRR(list(fileVals), list(first_val))
            # CASE 8 | UNIVERSAL SETTINGS: ID7 = [STcond, Params, Peaks, AEP]
            else:
                self._v1_Universal(list(fileVals), fileAttrs, has_groups, first_val, sZ)
        
        # Finish.
        h5.close()
        if ";" in self.fpath:
            os.remove(f) # Remove extracted HDF5 file.
            if is_cmd:
                shutil.rmtree("Extracted") # Remove temporary folder.
            


    
    def _v3_AEF(self, h5: h5py.File, fileKeys: list[str]):
        """
        Converts CHS v3 files where...
        * ID 1: `CHS-LA`, `CHS-NA`, `CHS-TX`
        * ID 7: `AEF`, `AEFcond`
        """
        sizeH = h5["Best Estimate AEF"].shape
        headers = ["ADCIRC Node ID", "AEF Value", *fileKeys[2:]]
        print(f"LENGTH: {len(headers) + self.more_steps}")
        self.df_normal["ADCIRC Node ID"] = np.repeat( np.array( h5["ADCIRC Node IDs"], dtype=int ), sizeH[1] )
        print("STATUS: 1", end=self.end_print)
        self.df_normal["AEF Value"] = np.tile( h5["AEF Values"][0], sizeH[0] )
        print("STATUS: 2", end=self.end_print)
        for i, col in enumerate(fileKeys[2:]):
            self.df_normal[col] = np.array( h5[col] ).flatten()
            print(f"STATUS: {i+3}", end=self.end_print)
        
        # Manage global mins and maxes.
        if not self.is_cmd:
            self.var_min_max = {}
            for dataset in headers[1:]:
                self._minmax_val(self.df_normal, dataset)
            print(f"STATUS: {len(headers) + 1}", end=self.end_print)
        
        # Laminate!
        self.df_normal = pd.DataFrame(self.df_normal)
        self._laminate(f"STATUS: {len(headers) + (1 if self.is_cmd else 2)}")
    


    def _v2_SACSNCSEFL_Peaks(self, h5: h5py.File, fileKeys: list[str], fileAttrs, first_val: h5py.Group):
        """
        Converts CHS v2 files where...
        * ID 1: `SACSNCSEFL`
        * ID 7: `Peaks`
        """
        file_cols = ["Save Point ID", "Save Point Latitude", "Save Point Longitude", "Save Point Depth"]
        grup_cols = ["Storm ID", "Storm Name", "Storm Type"] # Sorting attributes.
        vars_time = ["Landfall Time", "Peak Time"]
        vars_other = [x for x in fileKeys if x not in [*file_cols, *grup_cols, *vars_time]]
        print(f"LENGTH: {4 + self.more_steps}")

        # Extract and scale desired file attributes.
        n = len(list(first_val))
        print(self.df_normal.keys())
        self.df_normal.update({ key:np.repeat( fileAttrs[key].astype(D_COLTYPES[key]), n ) for key in file_cols })
        print(self.df_normal.keys())
        print(f"STATUS: 1", end=self.end_print)
        # Extract desired group attributes.
        self.df_normal["Storm ID"] = h5["Storm ID"].astype(int)[:]
        self.df_normal["Storm Name"] = [ x.decode('utf-8') for x in h5["Storm Name"] ]
        try: self.df_normal["Storm Type"] = [ x.decode('utf-8') for x in h5["Storm Type"] ]
        except: pass
        # Extract other variables.
        self.df_normal.update({ key:h5[key].astype(float)[:] for key in vars_other })
        print("STATUS: 2", end=self.end_print)

        # Extract variable data.
        no_land = np.isnan(h5["Landfall Time"]).all()
        no_peak = np.isnan(h5["Peak Time"]).all()
        no_date = no_land or no_peak
        if not no_date:
            # Manage Landfall Time and Peak Time columns, assuming "Units" attribute == b'hrs since 1970-01-01 00:00:00Z'
            tme = h5["Landfall Time"].attrs["Units"].decode('utf-8').split(" since ")[1][:-1] + " UTC"
            tme = np.array( pd.to_datetime( tme, format='%Y-%m-%d %H:%M:%S %Z', utc=True ) )
            t = np.repeat(tme, n)
            l = [pd.Timedelta(hours=x) for x in h5["Landfall Time"]]
            p = [pd.Timedelta(hours=x) for x in h5["Peak Time"]]
            self.df_normal["Landfall Time"] = t + l
            self.df_normal["Peak Time"]     = p
            self.df_normal["yyyymmddHHMM"]  = self.df_normal["Landfall Time"] - p
        print("STATUS: 3", end=self.end_print)

        # Get global mins and maxes.
        if not self.is_cmd:
            self.var_min_max = {}
            for var in vars_other:
                self._minmax_val(self.df_normal, var)
            if not no_date: 
                self._minmax_date(self.df_normal["yyyymmddHHMM"])
            print("STATUS: 4", end=self.end_print)

        # Laminate!
        """for x in self.df_normal.keys():
            print(x)"""
        self.df_normal = pd.DataFrame(self.df_normal)
        self._laminate(f"STATUS: {4 if self.is_cmd else 5}")
    


    def _v2_SACSNCSEFL_AEF(self, fileVals: list[h5py.Group], fileAttrs:dict, sZ: int):
        """
        Converts CHS v2 files where...
        * ID 1: `SACSNCSEFL`
        * ID 7: `AEF`, `AEFcond`

        Splits file by groups. Dataset filenames will be `[original filename]^[group title].csv`.
        """
        if not self.is_cmd: print(f"LENGTH: {sZ+1}")
        file_cols = ["Save Point ID", "Save Point Latitude", "Save Point Longitude", "Save Point Depth"]
        dict_file_cols = {key:fileAttrs[key].astype(D_COLTYPES[key]) for key in file_cols}
        self.h5s: list[H5_Organized_New] = []
        for i, group in enumerate(fileVals):
            # Extract group name
            name = self.name + "^" + str(group).split("\"")[1][1:]
            # Save AEF groups as separate databases
            h5_obj = H5_Organized_New()
            h5_obj.run_AEF_special(group, self, name, dict_file_cols)
            self.h5s.append( h5_obj )
            if not self.is_cmd: print(f"STATUS: {i+1}", end=self.end_print)
    


    def run_AEF_special(self, g: h5py.Group, h5_org, name_mod: str, dict_file_cols: dict):
        """
        Special H5_Organized object for CHS v2 files where...
        * ID 1: `SACSNCSEFL`
        * ID 7: `AEF`, `AEFcond`

        Parameters
        ---
        h5_org: The parent H5_Organized object.
        """
        self.df_normal = {}
        group = g
        self.is_aef_special = True
        self.name = name_mod
        self.export = h5_org.export
        self.is_cmd = h5_org.is_cmd
        self.end_print = h5_org.end_print
        n = len(list(group.values())[0])
        
        # Scale file attribute data
        for attr_key, obj in dict_file_cols.items():
            self.df_normal[attr_key] = np.repeat(obj, n)

        # Process data
        for d in group.keys():
            ls = group[d].astype(float)[:]
            self.df_normal[d] = ls
        
        # Catch mins + maxes
        if not self.is_cmd:
            self.var_min_max = {}
            for d in group.keys():
                self._minmax_val(self.df_normal, d)
        
        # Laminate!
        self.df_normal = pd.DataFrame(self.df_normal)
        self._laminate("")
    


    def _v1_Locations(self, h5: h5py.File):
        """
        Converts CHS v1 files where...
        * ID 1: `CHS-LA`, `CHS-NA`, `CHS-TX`
        * ID 7: `Locations`

        Splits file into groups "Nodes" and "Elements". Dataset filenames will be `[original filename]^[group title].csv`.
        """
        self.is_locations = True
        print(f"LENGTH: {4 if self.export else 2}")
        self.h5s: list[H5_Organized_New] = []
        # Manage Nodes.
        h5_nodes = H5_Organized_New()
        h5_nodes.name = self.name + "^Nodes"
        h5_nodes.fpath = self.fpath
        h5_nodes.export = self.export
        h5_nodes.fileType = self.fileType
        h5_nodes.is_locations = True
        h5_nodes.is_cmd = self.is_cmd   # Necessary for `h5_nodes._laminate()`
        h5_nodes.end_print = self.end_print
        headers = ["ADCIRC Node ID", "Latitude", "Longitude", "Datum Depth"]
        h5_nodes.df_normal = pd.DataFrame( h5["Nodes"], columns=headers ).astype( {"ADCIRC Node ID":int} )
        print("STATUS: 1", end=self.end_print)
        if not self.is_cmd:
            h5_nodes.var_min_max = {}
            for c in headers:
                h5_nodes._minmax_val(h5_nodes.df_normal, c)
        h5_nodes._laminate("STATUS: 2")
        self.h5s.append(h5_nodes)
        
        # Manage Elements.
        h5_elems = H5_Organized_New()
        h5_elems.name = self.name + "^Elements"
        h5_elems.fpath = self.fpath
        h5_elems.export = self.export
        h5_elems.fileType = self.fileType
        h5_elems.is_locations = True
        h5_elems.is_cmd = self.is_cmd   # Necessary for `h5_elems._laminate()`
        h5_elems.end_print = self.end_print
        nodes = [f"Node ID {i}" for i in range(1, h5["Elements"].shape[1]-1)]
        h5_elems.df_normal = pd.DataFrame( h5["Elements"], columns=["Triangular element ID", "Number of nodes", *nodes] ).astype(int)
        h5_elems.df_normal.drop( columns=["Number of nodes"], inplace=True )
        print(f"STATUS: {3 if self.export else 2}", end=self.end_print)
        # Get mins and maxes.
        if not self.is_cmd: 
            h5_elems.var_min_max = {}
            for c in ["Triangular element ID", *nodes]:
                h5_elems._minmax_val(h5_elems.df_normal, c)
        h5_elems._laminate(f"STATUS: 4")
        self.h5s.append(h5_elems)
    


    def _v1_Timeseries(self, h5: h5py.File, fileKeys: list[str], fileVals: list, fileAttrs: dict, sZ: int):
        """
        Converts CHS v1 files where...
        * ID 1: `NACCS`, `SACSNCSEFL`
        * ID 7: `Timeseries`
        """
        if not self.is_cmd: print(f"LENGTH: {sZ+2 if self.export else sZ+1}")
        file_cols = ["Save Point ID", "Save Point Latitude", "Save Point Longitude"]
        grup_cols = ["Save Point Depth", "Storm ID", "Storm Name", "Storm Type"]
        data_cols = list(h5[fileKeys[0]].keys())
        #headers = [*file_cols, *grup_cols, *data_cols]
        data_but_time = deepcopy(data_cols)
        data_but_time.remove("yyyymmddHHMM")

        self.var_min_max_byID = {}
        fAll = []; fNorm = []
        iRange = [1]

        # BEGIN!
        for i, group in enumerate(fileVals):
            group: h5py.Group
            i1 = i+1
            n = list(group.values())[0].shape[0] # list(group.values()) = list of datasets
            iRange.append(iRange[i] + n)

            # Manage normal dataset
            df1 = {key:val if isinstance(val, str) else val.astype(D_COLTYPES[key]) for key, val in fileAttrs.items() if key in file_cols}
            df2 = {key:val if isinstance(val, str) else val.astype(D_COLTYPES[key]) for key, val in group.attrs.items() if key in grup_cols}
            sID = str(df2["Storm ID"])
            dfL = {dataset:str(n)+" x 1" for dataset in group.keys()}
            df = pd.DataFrame( df1|df2|dfL, index=[i1] )
            fNorm.append(df)
            
            # Manage full dataset
            df1 = {key:np.repeat(val, n) for key, val in df1.items()}
            df2 = {key:np.repeat(val, n) for key, val in df2.items()}
            dfL = {dataset:col.astype(float)[:] for dataset, col in group.items() if dataset != "yyyymmddHHMM"}
            dfT = {"yyyymmddHHMM":np.array( pd.to_datetime( list(group["yyyymmddHHMM"]), format="%Y%m%d%H%M.0", utc=True, errors='coerce' ) )}
            df = pd.DataFrame( df1|df2|dfL|dfT, index = range(iRange[i], iRange[i1]) ).sort_values(by=["yyyymmddHHMM"])
            fAll.append(df)

            # Manage mins and maxes by Storm IDs.
            if not self.is_cmd:
                x = {}
                for dataset, col in dfL.items():
                    if not np.isnan( col ).all():
                        var_min = np.around( np.nanmin(col), decimals=self.dec )
                        var_max = np.around( np.nanmax(col), decimals=self.dec )
                        if var_max > var_min:
                            x[dataset] = [var_min, var_max]
                
                arr = [y for y in dfT["yyyymmddHHMM"] if isinstance(y, pd.Timestamp)]
                if len(arr) > 0:
                    var_min = np.nanmin(arr)
                    var_max = np.nanmax(arr)
                    if var_max > var_min:
                        x["yyyymmddHHMM"] = [var_min, var_max]
                self.var_min_max_byID[sID] = x # "var_min_max_byID" is a dictionary for each Storm ID. The value "x" is a dictionary for each variable.
                
            print(f"STATUS: {i1}", end=self.end_print)
        
        # ORGNAIZE
        self.df_full   = pd.concat(fAll).sort_values(by=["Storm ID"])
        self.df_normal = pd.concat(fNorm).sort_values(by=["Storm ID"])
        
        if not self.is_cmd:
            self.var_min_max = {}
            for dataset in data_but_time:
                self._minmax_val(self.df_full, dataset)
            self._minmax_date(self.df_full["yyyymmddHHMM"])
        self._laminate(f"STATUS: {sZ+1}")
    


    def _v1_NLR(self, h5: h5py.File, fileKeys: list[str]):
        """
        Converts CHS v1 files where...
        * ID 1: `NACCS`
        * ID 7: `NLR`

        Designed to export to CSV only.
        """
        file_cols = ["Save Point ID", "Save Point Latitude", "Save Point Longitude"]
        grup_cols = [x for x in fileKeys if x not in file_cols]
        print(f"LENGTH: {3 if self.export else 2}")
        d1 = {key:h5[key].astype(D_COLTYPES[key])[:] for key in file_cols}
        d2 = {key:h5[key].astype(float)[:] for key in grup_cols}
        dict_merged =  pd.DataFrame( d1|d2 )
        print("STATUS: 1", end=self.end_print)
        
        # Laminate!
        self.df_normal = pd.DataFrame(dict_merged)
        self._laminate("STATUS: 2")
    

    
    def _v1_SRR(self, fileVals: list, first_val: list[np.ndarray]):
        """
        Converts CHS v1 files where...
        * ID 1: `NACCS`
        * ID 7: `SRR`

        Designed to export to CSV only.
        """
        headers = ["Save Point ID", "Save Point Latitude", "Save Point Longitude"]
        dict_merged = dict.fromkeys(headers, [])
        len_task = len(headers) + len([x for g in fileVals[1:] for x in g.keys()]) + (2 if self.export else 1)
        print(f"LENGTH: {len_task}")
        for i, h in enumerate(headers):
            dict_merged[h] = [row[i].astype(D_COLTYPES[h]) for row in first_val]
            print(f"STATUS: {i+1}", end=self.end_print)
        i = len(headers)+1
        for group in fileVals[1:]:
            for gname, dataset in group.items():
                dict_merged[gname] = dataset.astype(float)[:]
                print(f"STATUS: {i}", end=self.end_print)
                i += 1

        # Laminate!
        self.df_normal = pd.DataFrame(dict_merged)
        self._laminate(f"STATUS: {i}")
    


    def _v1_Universal(self, fileVals: list[h5py.Group]|list[h5py.Dataset], fileAttrs:dict, has_groups: bool, first_val: h5py.Group|h5py.Dataset, sZ: int):
        """
        Converts CHS v1 files where...
        * ID 7: `STcond`, `Params`, `Peaks`, `AEP`
        """
        file_cols = ["Save Point ID", "Save Point Latitude", "Save Point Longitude"]
        if self.fileType in ["STcond", "Param"]: file_cols = []
        grup_cols = ["Save Point Depth", "Storm Name", "Storm ID", "Storm Type"]
        if self.fileType in ["STcond", "Param"]: grup_cols = ["Storm Name", "Storm Type"]
        elif self.fileType in ["AEP"]: grup_cols = []
        # Check if selected attributes exist.
        file_cols = [x for x in file_cols if x in fileAttrs.keys()]
        grup_cols = [x for x in grup_cols if x in first_val.attrs.keys()]

        data_cols = list(first_val.keys())
        # Check for time column
        data_but_time = deepcopy(data_cols)
        has_time = True
        try: data_but_time.remove("yyyymmddHHMM")
        except: has_time = False
        
        fAll = []
        iRange = [1]

        if has_groups:
            if not self.is_cmd: print(f"LENGTH: {sZ + self.more_steps}")

            for i, group in enumerate(fileVals):
                i1 = i+1
                if self.is_cmd: print(f"Processing group #{i1} {SPACES}", end="\r")
                
                n = list(group.values())[0].shape[0] # list(group.values()) = list of datasets
                iRange.append(iRange[i] + n)

                df1 = {} if file_cols == [] else { key:np.repeat(val if isinstance(val, str) else val.astype(D_COLTYPES[key]), n) 
                                                    for key, val in fileAttrs.items() if key in file_cols }
                df2 = {} if grup_cols == [] else { key:np.repeat(val if isinstance(val, str) else val.astype(D_COLTYPES[key]), n) 
                                                    for key, val in group.items() if key in grup_cols }
                dfL = {dataset:col.astype(float)[:] for dataset, col in group.items() if dataset != "yyyymmddHHMM"}
                dfT = {} if not has_time else {"yyyymmddHHMM":np.array( pd.to_datetime( list(group["yyyymmddHHMM"]), format="%Y%m%d%H%M.0", utc=True, errors='coerce' ) )}
                df = pd.DataFrame( df1|df2|dfL|dfT, index = range(iRange[i], iRange[i1]) )
                if has_time: df.sort_values(by=["yyyymmddHHMM"], inplace=True)
                fAll.append(df)

                print(f"STATUS: {i1}", end=self.end_print)
            
            # ORGANIZE
            self.var_min_max = {}
            self.df_normal = pd.concat(fAll)
            if "Storm ID" in list(self.df_normal.columns): 
                self.df_normal.sort_values(by=["Storm ID"], inplace=True)

            # Get global mins and maxes.
            if not self.is_cmd:
                self.var_min_max = {}
                if has_time:
                    for dataset in data_but_time:
                        self._minmax_val(self.df_normal, dataset)
                    self._minmax_date(self.df_normal["yyyymmddHHMM"])
                else:
                    for dataset in data_cols:
                        self._minmax_val(self.df_normal, dataset)
                print(f"STATUS: {sZ + 1}", end=self.end_print)
        
        else:
            # NOTE: INSERT UNIVERSAL CODE FOR H5s WITHOUT GROUPS!!!
            pass
        
        # FINISH
        self._laminate(f"STATUS: {sZ + (1 if self.is_cmd else 2)}")

    

    def _update_steps(self):
        """
        Update the number of steps in `LENGTH: ` print. For internal functions that count exporting and min/max finding as extra steps.
        """
        if self.export: self.more_steps += 1
        if not self.is_cmd: self.more_steps += 1

    

    def _func_d_to_Q(self, dt: pd.Timestamp):
        """
        Convert a Pandas `Timestamp` object to a PySide6 `QDateTime` object. For dateTimeEdit boxes in GUI.
        """
        x = QDateTime.fromString(dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "yyyy-MM-ddTHH:mm:ss.zzzZ")
        x.toUTC()
        return x


    
    def _minmax_val(self, dataset: pd.DataFrame, name: str):
        """
        Determines if the numerical array has a minimum and a maximum worth filtering.

        Parameters
        ---
        dataset: `self.df_normal`, `self.df_full`
        name: The name of the column.
        """
        all_nan = True
        try: all_nan = np.isnan(dataset[name]).all()
        except:
            try: all_nan = all(np.isnan( np.array(dataset[name], float) ))
            except: all_nan = all([x == np.nan for x in dataset[name]])

        if not all_nan:
            var_min = np.around( np.nanmin(dataset[name]), decimals=self.dec )
            var_max = np.around( np.nanmax(dataset[name]), decimals=self.dec )
            if var_max > var_min:
                self.var_min_max[name] = [var_min, var_max]


    
    def _minmax_date(self, arr: np.ndarray):
        """
        Determines if the date-time array has a minimum and a maximum worth filtering.

        Parameters
        ---
        arr: The array of date-time values.
        """
        all_nan = True
        try: all_nan = np.isnan(arr).all() # DEV NOTE: Is this all that's needed??
        except:
            try: all_nan = all(np.isnan( np.array(arr, float) ))
            except: all_nan = all([x == np.nan for x in arr])
        
        if not all_nan:
            arr = [x for x in arr if isinstance(x, pd.Timestamp)]
            if len(arr) > 0:
                var_min = np.nanmin(arr)
                var_max = np.nanmax(arr)
                if var_max > var_min:
                    self.var_min_max["yyyymmddHHMM"] = [self._func_d_to_Q(var_min), self._func_d_to_Q(var_max)]


    
    def _laminate(self, status):
        """
        Sets the normal dataset to the current dataset. If necessary, exports dataset to CSV and reports status.
        """
        self.df_current = self.df_normal
        if self.export: 
            self.export_csv()
            print(status, end=self.end_print)
    


    def export_csv(self):
        """
        Exports complete dataset to CSV.
        """
        fpath = os.path.join( DIR_RESULTS, f"{self.name}.csv" )
        if self.is_timeseries: self.df_full.to_csv( fpath, index=False )
        else:                self.df_normal.to_csv( fpath, index=False )
    


    def get_data_current(self):
        """Get the current dataset."""
        return self.df_current
    def get_data_normal(self):
        """Get the default dataset."""
        return self.df_normal
    def get_data_timeseries(self):
        """Timeseries only: Get the full dataset of the Timeseries file."""
        return self.df_full
    def get_fileType(self):
        """Get the type of file/model used in the dataset."""
        return self.fileType
    def get_var_min_max(self):
        """Get the set of minimum and maximum values for each variable."""
        return self.var_min_max
    def get_stormIDs(self):
        """Timeseries only: Get the unique storm IDs."""
        return np.unique( self.df_normal["Storm ID"] ).astype(str)
    def get_dataset(self):
        """Get the noraml dataset as TableModel when switching databases."""
        self.df_current = self.df_normal
        return TableModel(self.df_current)
    def get_stormID_subset(self, stormID):
        """Timeseries only: Get sub-dataset of storm ID as TableModel."""
        self.df_current = self.df_full[ self.df_full["Storm ID"] == stormID ].sort_values(by=["yyyymmddHHMM"])
        return TableModel(self.df_current)
    


    def set_filter(self, var, min, max, is_not_id):
        """
        Manage a filtered dataset.

        Option 1 if first time, but showing an abridged time series dataset. Option 2 for current state of dataset.
        """
        df = self.df_full if (self.is_timeseries and is_not_id) else self.df_current
        if var == "yyyymmddHHMM":
            df = df[df[var] != pd.NaT]
        self.df_current = df[(df[var] >= min) & (df[var] <= max)]
        return TableModel(self.df_current)
    


    def get_plot_data(self, var, min_dt, max_dt, stormIDs = None, only_one_dt = False):
        """Get data to plot peaks or timeseries data."""
        if self.is_timeseries and len(stormIDs) > 1:
            # Get truncated dataset of Storm IDs and necessary data.
            ids_chosen = [int(x) for x in stormIDs]
            ids_full_dataset = self.df_full["Storm ID"]
            indxs = [i for i, z in enumerate(ids_full_dataset) if z in ids_chosen]
            df = self.df_full.iloc[indxs]
            df = df[["Storm ID", var, "yyyymmddHHMM"]].sort_values(by=["Storm ID", "yyyymmddHHMM"])
            # Get time stamps of every Storm ID
            _, cnts = np.unique(df["Storm ID"], return_counts=True)
            timesteps = [np.arange(1, x+1) for x in cnts]
            timesteps = np.array( list(itertools.chain(*timesteps)) )
            timesteps = timesteps[:, np.newaxis]
            df = np.concatenate( (timesteps, df.to_numpy()), axis=1 ) # Add time steps
            return pd.DataFrame(df, columns=['Time Step', 'Storm ID', var, 'Date-Time'])
        
        else:
            if self.is_timeseries:
                df = self.df_full.loc[ self.df_full["Storm ID"] == int(stormIDs[0]) ]
                df.sort_values( by=["Storm ID", "yyyymmddHHMM"], inplace=True )
            else:
                df = self.df_normal.sort_values( by=["yyyymmddHHMM"] )
            df = df[df["yyyymmddHHMM"] != pd.NaT]
            if min_dt != None: # If there is a time filter.
                df = df[ (df["yyyymmddHHMM"] >= min_dt) & (df["yyyymmddHHMM"] <= max_dt) ]
            if only_one_dt:
                return pd.DataFrame({ "Storm ID":df["Storm ID"], var:df[var] })
            else:
                return pd.DataFrame({ "Date-Time":df["yyyymmddHHMM"], var:df[var] })




def func_processFile(fpath: str, msg: str):
    print(f"\n{msg}: Converting {fpath}")
    t1 = time.time()
    h5 = H5_Organized_New()
    h5.run( fpath, True, True )
    print(f"\nTime elapsed: {str(timedelta(seconds = time.time() - t1))}")




if len(sys.argv) > 1:

    # Running from program.
    if sys.argv[1] == "1":
        will_export = eval(sys.argv[2])
        fpath = str(sys.argv[3])
        h5 = H5_Organized_New()
        h5.run( fpath, will_export, False )
        sys.stdout.buffer.write( pickle.dumps( [h5] ) )
        sys.stdout.buffer.flush()

    # Running from command line.
    else:
        # Process all files.
        print("\nRunning the CHS HDF5 Converter...\n")
        for fpath in sys.argv[1:]:
            ftype = fpath.split(".")[-1]
            if ftype == "h5":
                func_processFile( fpath, "1 HDF5 file" )
            elif ftype == "zip":
                with ZipFile(fpath) as czip:
                    for subf in czip.namelist():
                        if subf.split(".")[-1] == "h5":
                            func_processFile( f"{fpath};{subf}", "1 ZIP file" )
            elif os.path.isdir(fpath):  # Folder.
                lst = []
                for (root, dirs, files) in os.walk(fpath):
                    if len(files) > 0:
                        lst.extend( [os.path.join(root, f) for f in files if f.split(".")[-1] == "h5"] )
                print(f"CONVERTING {str(len(lst))} FILES")
                for f in lst:
                    func_processFile( f, "All dir + subdirs (HDF5 only)" )
            else:
                print(f"\nIncompatible file or folder: {fpath}")