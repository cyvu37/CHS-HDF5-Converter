"""
StormSim: File 1
===
Converts specific HDF5 files from CHS databse.

About
---
begin_stormsim.py: Generates GUI, binds commands.

Author
---
Code by Jared Hidalgo. 
"""
title = "StormSim: CHS HDF5 Converter"
print("\nChecking requirements.............................\n")

# Import internal packages
import os, pickle, sys, time
from subprocess import call, Popen
from importlib.metadata import distributions
from platform import system
from copy import deepcopy
from datetime import timedelta
from functools import partial
from shutil import rmtree
from zipfile import ZipFile

# Get directories.
spl = __file__.split( os.sep )
DIR_PROGRAM = f"{os.sep}".join( spl[:-1] )
DIR_RESOURCES = os.path.join( DIR_PROGRAM, "resources" )
DIR_RESUTLS = f"{os.sep}".join( spl[:-2] )

# Set command to open a directory.
od_dict = {
    "Windows": "explorer", 
    "Darwin": "open"
}
open_directory = od_dict[system()] if system() in od_dict else "xdg-open"

# File check.
req_files = ["code01_h5organize.py", "gui01_ui_stormsim.py", "requirements.txt"]
lis_files = [f for f in os.listdir(DIR_PROGRAM) if f in req_files]
if len(lis_files) != len(req_files):
    sys.exit( "\n\nERROR: Missing Python files. --> Can't run program." )

# Package check: Online attempt.
try:
    call( f"{sys.executable} -m pip install -U pip", shell=True )
    call( f"{sys.executable} -m pip install -r \"{DIR_PROGRAM}{os.sep}requirements.txt\"", shell=True )
except:
    print( "WARNING: Either no internet or not using independent Python compiler." )

# Package check: Offline check.
with open(f"{DIR_PROGRAM}{os.sep}requirements.txt", "r") as r:
    req_pkgs = [i.split("==" if "==" in i else "\n")[0] for i in r.readlines()]
curr_pkgs    = [dist.metadata['Name'] for dist in distributions()]
missing_pkgs = [x for x in req_pkgs if x not in curr_pkgs]
if len(missing_pkgs) > 0:
    sys.exit( "\n\nERROR: Can't install missing Python packages. --> Can't run program." )

print("\nChecking requirements............................. Done!\nBooting CHS HDF5 Converter........................ ", end="")


# Import external packages.
from PySide6.QtCore import (Qt, QDateTime, QProcess, QThread, Signal)
from PySide6.QtGui import (QFont, QIcon, QImage, QPixmap)
from PySide6.QtWidgets import (QApplication, QCompleter, QDateTimeEdit, QFileDialog, 
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplashScreen, QTableWidgetItem)

STATES = { QProcess.ProcessState.NotRunning: 'Not running',
           QProcess.ProcessState.Starting: 'Initializing',
           QProcess.ProcessState.Running: 'Running' }
"""For printing the state of the QProcess."""

# Temporarily import program directory to PATH for importing program files from any directory.
sys.path.append( DIR_PROGRAM )

# Start splash screen.
app = QApplication( sys.argv )
main_pixmap = QPixmap(QImage(os.path.join( DIR_RESOURCES, "CHS HDF5 Converter logo 2.ico" )))
splash = QSplashScreen( main_pixmap )
splash.show()
splash.setWindowIcon( main_pixmap )

# Continue importing external packages.
import plotly.express as px
import plotly.offline as po
import plotly.io as pio
pio.renderers.default = "png"
import chime
chime.theme('material')
import numpy as np
import pandas as pd

# Import Python files
from code01_h5organize import H5_Organized_New
from gui01_ui_stormsim import Ui_MainWindow





class SecondThread(QThread):
    """
    New processing thread that loops over files to convert. 
    
    Without this, the ZipFile function would bottleneck the main Python thread.
	"""
    dictP = {}
    dict3_name_to_h5 = {}
    setCurrentProgress = Signal(int)
    success = Signal(dict)
    flim = 0

    
    def __init__(self, gui):
        """
        Store GUI objects. Determine number of HDF5 files to convert.
        """
        super().__init__()
        self.gui: StormSim_Converter = gui
    

    def run(self):
        """
        Perform loop over HDF5 files + references to HDF5 files in ZIP.
        """
        self.len = len(list(self.gui.dict2_name_to_task.keys()))
        has_zip = False
        for i, (fname, task) in enumerate(self.gui.dict2_name_to_task.items()):
            self.gui.statusBar.showMessage(f"<< Processing file {i+1}/{self.len}: {fname} >>")
            fpath = self.gui.dict1_name_to_URI[fname]
            if isinstance(fpath, list):
                fpath = ";".join(fpath)
                has_zip = True
            self.filename = fname.split(".")[0].split("/")[-1]

            self.h5 = None
            self.process = QProcess()
            self.process.readyReadStandardOutput.connect( partial(self.process_stdout, i) )
            self.process.readyReadStandardError.connect( self.process_stderr )
            self.process.stateChanged.connect( partial(self.process_state, i+1) )
            self.process.finished.connect( partial(self.process_finished, i+1) )
            self.process.setProgram( str(sys.executable) )
            self.process.setArguments( ['-u', f'{DIR_PROGRAM}{os.sep}code01_h5organize.py', "1", str(int(not task == 0)), str(fpath)] )
            self.timestamp = time.time()
            self.process.start()
            self.process.waitForFinished(-1)
        
        if has_zip: rmtree( "Extracted" )
        self.gui.statusBar.showMessage("<< Done >>")
        self.success.emit( self.dict3_name_to_h5 )
    

    def process_stdout(self, ii: int):
        """
        Decode output.

        If string, then apply status update to progress bar.

        If pickle, then aggregate individual H5_Organized objects.
        """
        x = self.process.readAllStandardOutput().data()
        try:
            x: str = x.decode("utf8")
            if x.startswith("LENGTH:"): # 
                self.flim = int(x.split(": ")[1].split(" ")[0])
            elif x.startswith("STATUS:"):
                r = ii + int(x.split(": ")[1]) / self.flim
                self.setCurrentProgress.emit( int(100*r) )
            #else: print(x)   # For errors on QProcess.
        except:
            try:
                self.h5: H5_Organized_New = pickle.loads( x )[0]
                if self.h5.h5s:
                    for h5_obj in self.h5.h5s:
                        self.dict3_name_to_h5[ h5_obj.name ] = h5_obj
                else:
                    self.dict3_name_to_h5[ self.h5.name ] = self.h5
            except: pass
    
    
    def process_stderr(self):
        """Print error in CMD that terminated conversion."""
        print( bytes( self.process.readAllStandardError() ).decode("utf8") )
    
    def process_state(self, ii: int, state: QProcess.ProcessState):
        """Print state of converting file in CMD."""
        print(f"Converting file {ii}/{self.len}: {self.filename} | {STATES[state]}")
    
    def process_finished(self, ii: int, exit_code, exit_status):
        """Print conversion time."""
        self.setCurrentProgress.emit( 100*ii )
        te = str(timedelta(seconds = time.time() - self.timestamp))
        res = "Finished!" if self.h5 else "Not imported."
        print(f"{res} Time elapsed: {te}\n")
    
    def exit(self):
        """Kill thread from "Abort" button."""
        try: self.process.kill()
        except: pass
        self.quit()






class StormSim_Converter(Ui_MainWindow):
    """
    Sub-class of a pre-made GUI (`Ui_MainWindow`) from the file `gui01_ui_stormsim.ui`.
	"""
    dec = 6
    """Number of decimals in doubleSpinBoxes."""
    
    state_1x1_browse = True
    """STATE before conversion: Initial state of app."""
    ACTIVE_DIR = deepcopy(DIR_RESUTLS)
    """When user selects H5 or ZIP file(s), directory is saved here."""
    default_button = QMessageBox.StandardButton.Yes
    full_filelist = []
    """Full list of filenames."""

    state_1x2A_imported = False
    """STATE before conversion: Files imported."""
    dict1_name_to_URI = {}
    """Dictionary of filenames (w/ extension) to absolute filepath (.h5) or ZIP filepath."""
    list_to_not_import = []
    """Filenames (w/o extension) to avoid importing."""
    is_adding_rows = False
    """State of adding rows to tableWidget."""
    track_import = []
    """Row numbers of selected files to import."""
    track_export = []
    """Row numbers of selected files to export."""
    has_timeseries = False
    """If there is no time series data, there's no need for a "Graph" tab."""

    task_checklist = [False] * 2
    """Keep track of what will happen at Run. i=0: Importing a file. i=1: Exporting a file."""

    state_1x2B_search = False
    """STATE of searching dataset. Can be True with 1x2A and 1x2B."""
    search_res = ""
    """The results of a search."""
    
    state_1x3_running = False
    """STATE during conversion."""
    dict2_name_to_task = {}
    """Dictionary of filenames (w/ extension) to task type: 0 = import, 1 = export, 2 = both"""
    dict3_name_to_h5 = {}
    """Dictionary of filenames (w/o extension) to modified H5 object."""
    mainThread: QThread = None
    """Reference to SecondThread object. For closing app."""
    restart_msgbox = None
    """Confirmation window to abort Run button."""
    is_changing_databases = False
    """State of adding databases to comboBox_62. Prevents self.func_DVtable_change_var() from running."""

    state_2x1_converted = False
    """STATE after conversion."""
    curr_database = ""
    """Current database in self.listWidget."""
    stormIDs = None
    """List of storm IDs for current database in Data Viewer."""
    is_resetting_vars = False
    """State of "Filter" groups changing variables. Prevents self.func_DVtable_check_datetime() and self.func_DVtable_check_magnitude() from running."""
    is_stormid_applied = False
    """State of Storm ID applied to dataset via comboBox_62 (Timeseries only)."""
    will_apply_mag = False
    """State of applying magnitude filter to "Table"."""
    will_apply_date = False
    """State of applying date filter to "Table"."""
    only_one_dt = False
    """Is Storm ID range only within one date?"""
    dataset_filters = []
    """State of filter applied to dataset via "Date Range" or "Magnitude Range"."""
    plot_stormIDs = []
    """List of Storm IDs chosen for "Plot"."""
    str_filters = ""
    """Filter status for plainTextEdit."""
    str_stormIDs = ""
    """Storm ID status for plainTextEdit."""

    state_2x2A_justplot = False
    """STATE after graph made. Graph was just made in Data Viewer. Can be True with 2x1A and 2x1B."""
    state_2x2B_aplot = False
    """STATE after plot made. There is a plot made. Can be true with 2x1A and 2x1B."""


    def __init__(self, window: QMainWindow):
        """
        Modifies the pre-made GUI, binds commands.
		"""
        self.setupUi(window)
        self.window = window
        self.window.closeEvent = self.closeEvent
        self.window.setWindowTitle(title)

        # Add pictures from the same directory manually
        img_right = os.path.join( DIR_RESOURCES, "CHL_banner3.png" )
        img_left = os.path.join( DIR_RESOURCES, "thumbnail_SSLogo (transparent).png" )
        self.label_2_chl_logo.setPixmap( QPixmap(img_right) )
        self.label_10_stormsim_logo.setPixmap( QPixmap(img_left) )
        # Set logo on window
        self.logo = QIcon(main_pixmap)
        self.window.setWindowIcon( self.logo )

        # Set button stylesheets
        self.style_btn_normal = str(self.pushButton_1.styleSheet)
        self.style_btn_bold = str(self.pushButton_2.styleSheet)
        self.style_btn_reset_on = ("QPushButton { background-color: red;" +
                                                 "color: white;" + 
                                                 "font-weight: bold;" +
                                                 "border: 1px solid black;" +
                                                 "border-style: outset;" +
                                                 "border-radius: 6px;}" +
                                   "QPushButton:hover { border: 2px solid rgb(0, 120, 212);" +
                                                       "background-color: rgb(245, 0, 100) }" +
                                   "QPushButton:pressed { background-color: rgb(224, 0, 0);" +
                                                         "border-style: inset;}")
        self.style_btn_run = ("QPushButton { background-color: lime;" +
                                            "color: black;" + 
                                            "font-weight: bold;" +
                                            "border: 1px solid black;" +
                                            "border-style: outset;" +
                                            "border-radius: 6px;}" +
                              "QPushButton:hover { border: 2px solid rgb(0, 120, 212);" +
                                                  "background-color: rgb(80, 245, 100);}" +
                              "QPushButton:pressed { border-style: inset;" +
                                                    "background-color: rgb(0, 224, 0);}")
        
        # Set button styles to change font
        self.style_font_btn_norm = QFont()
        self.style_font_btn_norm.setPointSize(11)
        self.style_font_btn_norm.setBold(False)
        self.style_font_btn_norm.setUnderline(False)
        self.style_font_btn_bold = QFont()
        self.style_font_btn_bold.setPointSize(11)
        self.style_font_btn_bold.setBold(True)
        self.style_font_btn_bold.setUnderline(False)

        # Reset widgets
        # > Convert tab
        self.pushButton_1.setEnabled(False)
        self.lineEdit.setEnabled(False)
        self.func_disable_reset_button( self.pushButton_3 )
        while self.tableWidget.columnCount() > 0:
            self.tableWidget.removeColumn(0)
        while self.tableWidget.rowCount() > 0:
            self.tableWidget.removeRow(0)
        self.tableWidget.setEnabled(False)
        # > Data Viewer (left)
        self.comboBox_62.setPlaceholderText("")
        self.doubleSpinBox_12.setDecimals(self.dec)
        self.doubleSpinBox_11.setDecimals(self.dec)

        # Initial state for primary tabs
        self.tabWidget.setTabEnabled(1, False)
        self.tabWidget.setTabEnabled(2, False)
        self.tabWidget.setTabEnabled(3, False)
        self.tabWidget_2.setEnabled(False)
        self.statusBar.showMessage( "Import > Ready to import HDF5/ZIP files with \"Browse.\"" )

        # Convert tab > Bind commands
        self.pushButton_2.clicked.connect( self.func_CONVERT_browse_files )
        self.tableWidget.cellChanged.connect( self.func_CONVERT_table_cellChanged )
        self.tableWidget.clicked.connect( self.func_CONVERT_click_table )
        self.lineEdit.textChanged.connect( self.func_CONVERT_search_file )
        self.pushButton_3.clicked.connect( self.func_CONVERT_clear_imported_files )
        self.pushButton_1.clicked.connect( self.func_RUN )

        # Data Viewer (left) > Bind commands
        self.listWidget.itemClicked.connect( self.func_DV_change_dataset )
        # "Table" tab
        self.pushButton_81.clicked.connect( self.func_DVtable_export_current )
        self.pushButton_79.clicked.connect( self.func_DVtable_export_full )
        self.pushButton_39.clicked.connect( self.func_DVtable_add_filter )
        self.pushButton_57.clicked.connect( self.func_DVtable_clear_all_filters )
        self.pushButton_102.clicked.connect( self.func_DVtable_tooltip_for_pushButton_102 )
        self.comboBox_27.currentIndexChanged.connect( self.func_DVtable_change_var )
        self.comboBox_62.currentTextChanged.connect( self.func_DVtable_change_stormID )
        self.dateTimeEdit_19.dateTimeChanged.connect( self.func_DVtable_check_datetime )
        self.dateTimeEdit_20.dateTimeChanged.connect( self.func_DVtable_check_datetime )
        self.doubleSpinBox_12.valueChanged.connect( self.func_DVtable_check_magnitude )
        self.doubleSpinBox_11.valueChanged.connect( self.func_DVtable_check_magnitude )
        # "Graph" tab
        self.pushButton_82.clicked.connect( self.func_DVplot_plot )
        self.pushButton_104.clicked.connect( self.func_DVplot_tooltip_for_pushButton_104 )
        self.comboBox_28.currentIndexChanged.connect( self.func_DVplot_change_var )
        self.comboBox_63.currentTextChanged.connect( self.func_DVplot_change_stormID )
        self.pushButton_85.clicked.connect( self.func_DVplot_add_stormID )
        self.pushButton_83.clicked.connect( self.func_DVplot_clear_stormIDs )
        self.dateTimeEdit_21.dateTimeChanged.connect( self.func_DVplot_check_daterange )
        self.dateTimeEdit_22.dateTimeChanged.connect( self.func_DVplot_check_daterange )
        self.pushButton_84.clicked.connect( self.func_DVplot_reset_daterange )

        print("Done!\n\n\n")

    
    def closeEvent(self, event):
        """
        GUI Action: Popup window before closing app.
        """
        chime.warning()
        txt = "Are you sure you want to quit? Exported files will not be deleted, but any progress in the GUI will not be saved."
        msgBox = QMessageBox( QMessageBox.Icon.Question,
                              "Exiting the Program",
                              txt,
                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                              self.window,
                              Qt.WindowType.WindowStaysOnTopHint )
        reply = msgBox.exec()
        if reply == QMessageBox.StandardButton.Yes:
            if self.state_1x3_running:
                try: self.mainThread.exit()
                except: pass
            sys.exit()
        else:
            event.ignore()

    
    def func_enable_reset_button(self, btn: QPushButton):
        """
        GUI Design: Setup to enable and decorate a Reset button.
        """
        btn.setStyleSheet( self.style_btn_reset_on )
        btn.setEnabled( True )

    
    def func_disable_reset_button(self, btn: QPushButton):
        """
        GUI Design: Setup to disable and decorate a Reset button.
        """
        btn.setStyleSheet( self.style_btn_normal )
        btn.setFont( self.style_font_btn_norm )
        btn.setEnabled( False )

    
    def func_Q_to_d(self, dt: QDateTimeEdit) -> np.ndarray[pd.Timestamp]:
        """
        Convert a PySide6 `QDateTime` object to a Pandas `Timestamp` object. For datetime processing.
        """
        return np.array( pd.Timestamp( dt.dateTime().toString("yyyy-MM-ddTHH:mm:ss.zzzZ") ) )


    def _func_d_to_Q(self, dt: pd.Timestamp):
        """
        Convert a `Timestamp` object to a `QDateTime` object. For dateTimeEdit boxes in GUI.
        """
        x = QDateTime.fromString( dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "yyyy-MM-ddTHH:mm:ss.zzzZ" )
        x.toUTC()
        return x

    

    def func_CONVERT_browse_files(self):
        """
        Import HDF5 and/or ZIP files and ignore everything else.
        
        GUI Location: Convert tab > Qualifying Files group > "Browse"/"Add" button
        """
        no_files = True
        duplicate_files = False
        # While no files are recorded in the app
        while no_files:
            filedialog_selected = QFileDialog.getOpenFileNames( self.window, "Select one or more files", self.ACTIVE_DIR, "HDF5 files (*.h5 *.zip)" )
            new_filenames = []
            # If any file is selected
            if filedialog_selected[0] != []:
                
                # Filter tuple
                filedialog_selected = [a for a in filedialog_selected[:-1]][0]
                # Save the path of the active directory. DEV NOTE: If user searches for file and chooses a search result, the search path will be saved to ACTIVE_DIR.
                self.ACTIVE_DIR = os.path.dirname( str(filedialog_selected[0].split(os.sep)[:-1]) )#.replace(os.sep, '/')
                # Check each file
                for f in filedialog_selected:
                    if f.split(os.sep)[-1].split(".")[-1] == "h5": # If an HDF5 file
                        [new_filenames, duplicate_files] = self.func_validate_file( new_filenames, duplicate_files, f1 = f )
                    else:
                        with ZipFile(f) as czip: # Peek into ZIP file
                            for subf in czip.namelist():
                                [new_filenames, duplicate_files] = self.func_validate_file( new_filenames, duplicate_files, f1 = subf, f2 = f )
                
                # If current files are empty, but you already have other files imported, notify.
                if len(new_filenames) == 0 and len(self.dict1_name_to_URI) != 0:
                    chime.warning()
                    txt = "Files with the same name are assumed to have the same data." if duplicate_files else "None of the files selected qualify for this app.\nYou still have acceptable files."
                    txt += " Try again?"
                    msgBox = QMessageBox.warning( self.window, "No Qualifying Files Found", txt, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.default_button )
                    if msgBox == QMessageBox.StandardButton.No:
                        no_files = False
                else:
                    # Sort and merge new files below old ones
                    new_filenames.sort()
                    self.full_filelist = list(dict.fromkeys([*new_filenames, *self.full_filelist]))
                    cnt_files = len(self.full_filelist)
                    
                    if cnt_files != 0: # THEN SUCCESS!!!
                        # Convert tab > Qualifying Files group > Add rows to table
                        # - If table is new...
                        if self.state_1x1_browse:
                            self.tableWidget.setEnabled(True)
                            self.tableWidget.setColumnCount(3)
                            self.tableWidget.setHorizontalHeaderLabels(["Filename", "Export", "Import"])
                            for row, name in enumerate(self.full_filelist):
                                self.func_add_row(name, row)
                            # Convert tab > Qualifying Files group > Enable text box
                            self.lineEdit.setEnabled(True)
                            # Convert tab > Qualifying Files group > "Browse" button: Change "Browse" to "Add" and un-bold
                            self.pushButton_2.setFont( self.style_font_btn_norm )
                            self.pushButton_2.setText( "Add" )
                            # Convert tab > Qualifying Files group > "Clear" button
                            self.func_enable_reset_button( self.pushButton_3 )
                            # Convert tab > Task Checklist group > "Run" button
                            self.pushButton_1.setFont( self.style_font_btn_bold )
                            self.pushButton_1.setToolTip( "Select at least one HDF5 file to export to CSV and/or import to the app!" )
                            # Adjust the current state
                            self.state_1x1_browse = False
                            self.state_1x2A_imported = True
                        # - If items are already on the table, start from bottom
                        else:
                            row = self.tableWidget.rowCount()
                            for name in new_filenames:
                                self.func_add_row(name, row)
                                row += 1
                            # Reset text box.
                            self.lineEdit.setText("")

                        # Convert tab > Qualifying Files group > Set # of files
                        self.lineEdit.setPlaceholderText( "Search " + str(cnt_files) + (" filename" if cnt_files == 1 else " filenames") )
                        
                        no_files = False
                        self.tableWidget.resizeColumnsToContents()
                        self.statusBar.showMessage( "Import > Files imported. Select which files to import/export." )
                        chime.info()
                    else: 
                        # Prompt dialog window when no qualifying files were found
                        chime.warning()
                        msgBox = QMessageBox.warning( self.window, "No Qualifying Files Found", 
                                                      "None of the selected files qualify for this app. Try again?", 
                                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.default_button )
                        if msgBox == QMessageBox.StandardButton.No:
                            no_files = False
            else:
                # Prompt dialog window when no files were selected
                chime.warning()
                msgBox = QMessageBox.warning( self.window, "No Files Selected", "You didn't select any files. Try again?", 
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.default_button )
                if msgBox == QMessageBox.StandardButton.No:
                    no_files = False
    
    

    def func_validate_file(self, new_filenames: list[str], duplicate_files: bool, f1: str, f2: str = None):
        """
        Checks if the current HDF5 file has 6 underscores and is already accounted for. Returns updated lists.
        """
        file = os.path.basename(f1)
        file_divide = file.split(".") # File name without extension
        file_split = file_divide[0].split("_")
        # HDF5 compatibility check
        b1 = len(file_split) == 7 # If it has 7 categories
        b2 = file not in self.dict1_name_to_URI.keys() # If filename isn't already imported
        if b1 and b2:
            if f2 == None:
                self.dict1_name_to_URI[file] = f1 # HDF5 filepath
            elif file_divide[1] == "h5":
                self.dict1_name_to_URI[file] = [f2, f1] # ZIP filepath, HDF5 filepath in ZIP
            else:
                return [new_filenames, duplicate_files]
            new_filenames.append(file)
            # Time series file check for entire app
            if file_split[6] == "Timeseries":
                self.has_timeseries = True

        elif not b2: # If filename is already in dictionary.
            duplicate_files = True
        return [new_filenames, duplicate_files]
    


    def func_add_row(self, name: str, row: int):
        """
        Adds row to Qualifying Files table.
		"""
        self.is_adding_rows = True
        self.tableWidget.insertRow(row)
        
        # Column 1: Add filename.
        l = QTableWidgetItem(name)
        l.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.tableWidget.setItem(row, 0, l)
        
        # Column 2: Add option to export.
        chkBoxExport = QTableWidgetItem()
        chkBoxExport.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        chkBoxExport.setCheckState(Qt.CheckState.Unchecked)
        self.tableWidget.setItem(row, 1, chkBoxExport)
        
        # Column 3: Determine if available to import!
        name = name.split(".")[0]
        name_split = name.split("_")
        # Import filter #2. RULES TO LIMIT FILES ARE HERE!!!
        b1 = name_split[0] not in ["CHS-TX"] and name_split[-1] not in ["AEF"]
        b2 = name_split[1] != "TH"
        b3 = name_split[3] != "Post96RT"
        b4 = name_split[-1] not in ["NLR", "Param", "SRR"]
        chkBoxImport = QTableWidgetItem()
        if np.all([b1, b2, b3, b4]):
            chkBoxImport.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chkBoxImport.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.list_to_not_import.append(name)
            chkBoxImport.setFlags(Qt.ItemFlag.NoItemFlags)
            chkBoxImport.checkState()
        self.tableWidget.setItem(row, 2, chkBoxImport)
        
        # Change state.
        self.is_adding_rows = False
    


    def func_CONVERT_table_cellChanged(self, row: int, column: int):
        """
        Activate "Run" button if exporting and/or importing datasets after conversion.

            Export = Save dataset as CSV file.
        
            Import = Display dataset on Data Viewer.

        GUI Location: Convert tab > Qualifying Files group > Table > Any checkbox
		"""
        if not self.is_adding_rows: # Only check if the table isn't adding rows.
            export_is_checked = self.tableWidget.item(row, 1).checkState() == Qt.CheckState.Checked
            import_has_checkState = hasattr(self.tableWidget.item(row, 2), "checkState")
            import_is_checked = self.tableWidget.item(row, 2).checkState() == Qt.CheckState.Checked if import_has_checkState else False
            
            if column == 2 and import_has_checkState:
                if import_is_checked: self.track_import.append(row)
                else:                 self.track_import.remove(row)
                num_import = len(self.track_import)
                self.task_checklist[0] = num_import > 0
                if num_import > 8:
                    deselected = self.tableWidget.item( self.track_import[num_import-2], column )
                    deselected.setCheckState(Qt.CheckState.Unchecked) # Uncheck previous selection. Auto-runs self.func_CONVERT_table_cellChanged() for that item.
                    chime.warning()
                    msgBox = QMessageBox.warning( self.window, "Import Limit!", 
                                                  "For memory limitations, this app only imports up to 8 HDF5 files.\nChoose wisely. Your previous file was deselected.",
                                                  QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok )
                else:
                    self.tableWidget.setHorizontalHeaderItem( column, QTableWidgetItem(f"Import ({num_import})") )
            
            else: # column == 1
                if export_is_checked: self.track_export.append(row)
                else:                 self.track_export.remove(row)
                num_export = len(self.track_export)
                self.task_checklist[1] = num_export > 0
                if num_export == 8:
                    chime.warning()
                    txt = "Exporting 8 or more HDF5 files will take a long time.\nChoose wisely."
                    if len(self.track_import) > 0: txt += " You can import other files later."
                    msgBox = QMessageBox.warning( self.window, "Conversion Warning!", txt, QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok )
                self.tableWidget.setHorizontalHeaderItem( column, QTableWidgetItem(f"Export ({num_export})") )
            
            # Manage "Run" button + status
            if len(self.track_import) > 0 or len(self.track_export) > 0:
                self.pushButton_1.setEnabled(True)
                self.pushButton_1.setStyleSheet( self.style_btn_run )
                self.pushButton_1.setToolTip( "" )
                self.statusBar.showMessage( "Import > Ready to run! Other optoins available." + self.search_res )
            else:
                self.pushButton_1.setEnabled(False)
                self.pushButton_1.setStyleSheet( self.style_btn_normal )
                self.pushButton_1.setToolTip( "Select at least one HDF5 file to import and/or export!" )
                self.statusBar.showMessage( "Import > Select which files to import/export." + self.search_res )
    

    
    def func_CONVERT_search_file(self, s):
        """
        On text change, highlight all files with matching substring.
        
        GUI Location: Convert tab > Qualifying Files group > "Search files" text box
		"""
        curr_status = self.statusBar.currentMessage()
        already_searched = " | " in curr_status
        first = curr_status.split(" | ")[0] if already_searched else curr_status

        self.tableWidget.setCurrentItem( None )
        if s:
            # Get items
            matching_items = self.tableWidget.findItems(s, Qt.MatchFlag.MatchContains)
            if matching_items:
                size = len(matching_items)
                # Highlight items
                self.tableWidget.clearSelection()
                for item in matching_items:
                    item.setSelected(True)
                tmp = " file matched" if size == 1 else " files matched"
                self.search_res = " | " + str(size) + tmp
            else:
                self.search_res = " | No files matched"
                self.tableWidget.clearSelection()
        else:
            self.search_res = ""
        
        # Status
        self.statusBar.showMessage( first + self.search_res )



    def func_CONVERT_click_table(self):
        """
        Any click on the table clears the highlights made by the "Search files" text box.
        
        GUI Location: Convert tab > Qualifying Files group > Table
		"""
        curr_status = self.statusBar.currentMessage()
        if " | " in curr_status:
            self.lineEdit.setText("")
            self.statusBar.showMessage( curr_status.split(" | ")[0] )
            self.search_res = ""



    def func_CONVERT_clear_imported_files(self):
        """
        Removes all files from the table.
        
        GUI Location: Convert tab > Qualifying Files group > "Clear" button
		"""
        chime.warning()
        msgBox = QMessageBox.warning( self.window, "Clearing Imported Files", "Are you sure you want to remove all imported HDF5 files?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.default_button )
        if msgBox == QMessageBox.StandardButton.Yes:
            # Convert tab > Clear table and tab
            for i in reversed(range(self.tableWidget.columnCount())):
                self.tableWidget.removeColumn(i)
            for i in reversed(range(self.tableWidget.rowCount())):
                self.tableWidget.removeRow(i)
            self.tableWidget.setEnabled(False)
            self.pushButton_1.setEnabled(False) # "Run" button
            self.pushButton_1.setFont( self.style_font_btn_norm )
            self.pushButton_2.setText( "Browse" ) # "Add" -> "Browse" button
            self.pushButton_2.setFont( self.style_font_btn_bold )
            self.func_disable_reset_button( self.pushButton_3 ) # "Clear" button
            self.lineEdit.setPlaceholderText("Search files") # Reset text box
            self.func_disable_reset_button( self.pushButton_1 )
            # Clear data
            self.full_filelist = []
            self.dict1_name_to_URI = {}
            self.dict2_name_to_task = {}
            self.dict3_name_to_h5 = {}
            self.list_to_not_import = []
            self.search_res = ""
            self.is_adding_rows = False
            self.task_checklist = [False] * 2
            self.track_import = []
            self.track_export = []
            self.has_timeseries = False
            self.state_1x2A_imported = False
            self.state_1x1_browse = True
            self.statusBar.showMessage( "Import > Ready to import HDF5/ZIP files with \"Browse\"." )
    

    #
    # Convert tab > Task Checklist group > "Run" button
    #
    def func_RUN(self):
        """
        Converts all selected files to datasets, then exports and/or imports the datasets.
        
        GUI Location: Convert tab > Task Checklist group > "Run"/"Abort" button
		"""
        # Reiterate the checklist
        txt = "Are you sure you want to perform the following tasks?"
        if self.task_checklist[1]:
            txt += " You won't be able to export/import any more files!"
        txt += "\n\n"
        if self.task_checklist[1]:
            txt += "- Export a file to CSV\n" if len(self.track_export) == 1 else "- Export files to CSV\n"
        if self.task_checklist[0]:
            txt += "- Import a file\n" if len(self.track_import) == 1 else "- Import files\n"
        msgBox = QMessageBox.information( self.window, "Confirm Run", txt, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.default_button )
        
        # Start the work.
        if msgBox == QMessageBox.StandardButton.Yes:
            # Set current state
            self.state_1x3_running = True
            # Convert tab > Disable "Import Files" group except for question box
            self.lineEdit.setEnabled(False)
            self.pushButton_2.setEnabled(False)
            self.pushButton_3.setEnabled(False)
            self.tableWidget.setEnabled(False)
            self.func_disable_reset_button( self.pushButton_3 )
            # Convert tab > "Run" to "Abort" button
            self.pushButton_1.setText( "Abort" )
            self.func_enable_reset_button( self.pushButton_1 )
            self.pushButton_1.clicked.disconnect( self.func_RUN )
            self.pushButton_1.clicked.connect( self.func_abort_run )
            # Task management on each file: 0 = import, 1 = export, 2 = both
            track_both = set(self.track_import).intersection(self.track_export)
            list_import = [self.tableWidget.item(i, 0).text() for i in self.track_import]
            list_export = [self.tableWidget.item(i, 0).text() for i in self.track_export]
            list_both = [self.tableWidget.item(i, 0).text() for i in track_both]
            self.dict2_name_to_task = dict.fromkeys(list_import, 0)
            self.dict2_name_to_task.update( dict.fromkeys(list_export, 1) )
            self.dict2_name_to_task.update( dict.fromkeys(list_both, 2) )
            # Setup progress bar
            self.progress_bar = QProgressBar()
            #self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.progress_bar.setValue(0)
            self.progress_bar.setMaximum(len(self.dict2_name_to_task.keys())*100)
            self.progress_bar.setToolTip("For all processing files.")
            self.statusBar.addPermanentWidget( self.progress_bar )
            self.progress_bar.show()

            # Start conversion
            self.mainThread = SecondThread(self)
            self.mainThread.setCurrentProgress.connect( self.progress_bar.setValue )
            self.mainThread.success.connect(self.func_convert_success)
            self.mainThread.setTerminationEnabled(True)
            self.mainThread.finished.connect(self.mainThread.deleteLater)
            self.mainThread.start()
        

    
    def func_convert_success(self, res):
        """
        Handle data after QThread finishes converting all files.
		"""
        self.state_1x3_running = False # Change state
        self.dict3_name_to_h5: dict[str, H5_Organized_New] = res # Copy dictionary from QThread.
        # Remove "Abort" confirmation window if open.
        if self.restart_msgbox != None:
            self.restart_msgbox = None
        self.progress_bar.hide() # Hide progress bar
        # Convert tab > "Abort" to "Run" button
        self.pushButton_1.setText( "Run" )
        self.pushButton_1.setStyleSheet( self.style_btn_normal )
        self.pushButton_1.clicked.disconnect( self.func_abort_run )
        self.pushButton_1.clicked.connect( self.func_RUN )
        
        # Check if convert only (aka no imported files).
        had_no_conversion = not self.task_checklist[0] and self.task_checklist[1]
        self.tabWidget.setTabEnabled(0, had_no_conversion) # If no conversion, keep "Import" tab enabled.
        if had_no_conversion: # Revert to imported state
            # Convert tab > Re-enable "Import Files" group and "Clear" button
            self.lineEdit.setEnabled(True)
            self.pushButton_2.setEnabled(True)
            self.pushButton_3.setEnabled(True)
            self.tableWidget.setEnabled(True)
            self.func_enable_reset_button( self.pushButton_3 )
            # Set status
            self.statusBar.showMessage( "Import > Success! You can import and/or export more files along with other options." )
        else:
            self.statusBar.showMessage( "<< Loading Data Viewer >>" )
            print("\nLoading Data Viewer... ", end="")
            # Disable other states
            self.state_1x2A_imported = False
            self.state_1x2B_search = False
            # Enable other tabs
            self.tabWidget_2.setEnabled(True)
            self.tabWidget.setTabEnabled(1, True) # Data Viewer (left) > Enable tabs
            self.tabWidget.setCurrentIndex(1)
            self.tabWidget_2.setTabEnabled(0, True)
            # Disable Table + Graph tabs
            self.tabWidget_4.setEnabled(False)
            self.pushButton_81.setEnabled(False)
            self.dateTimeEdit_19.setEnabled(False)
            self.dateTimeEdit_20.setEnabled(False)
            self.doubleSpinBox_12.setEnabled(False)
            self.doubleSpinBox_11.setEnabled(False)
            self.dateTimeEdit_21.setEnabled(False)
            self.dateTimeEdit_22.setEnabled(False)
            # Filter out unused datasets.
            for f in self.list_to_not_import:
                if "AEF" in f:
                    remove = []
                    for ff in self.dict3_name_to_h5.keys():
                        if f == ff.split("^")[0]:
                            remove.append(ff)
                    for ff in remove:
                        del self.dict3_name_to_h5[ff]
                else:
                    try: del self.dict3_name_to_h5[f]
                    except: pass
            # Data Viewer (left) > Fill "Dataset"
            self.is_changing_databases = True
            s_list = sorted( list(self.dict3_name_to_h5.keys()) )
            self.listWidget.addItems(s_list)
            self.groupBox_32.setTitle(f"Dataset ({len(s_list)})")
            self.is_changing_databases = False
            # Data Viewer (left) > If time series data is not available, then don't enable option to plot for time series data
            # Set state
            self.state_2x1_converted = True
            self.statusBar.showMessage( "Data Viewer > Table > Success! Observe + export data with Data Viewer." )
            print("Done!")
        
        chime.success()
        self.mainThread = None # Delete SecondThread
    


    def func_abort_run(self):
        """
        Abort converting files. Terminates the `self.func_RUN` function.
        
        GUI Location: GUI Location: Convert tab > Qualifying Files group > "Run"/"Abort" button
		"""
        chime.warning()
        txt = "Are you sure you want to abort?\n"
        if self.task_checklist[0]: txt += "- Any imported files will need to be exported again.\n"
        if self.task_checklist[1]: txt += "- Exported CSV files will not be deleted.\n"
        self.restart_msgbox = QMessageBox.warning( self.window, "Confirm Abort", txt, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.default_button )
        
        # Start the work.
        if self.restart_msgbox == QMessageBox.StandardButton.Yes:
            # Delete QThread
            if self.state_1x3_running:
                try: self.mainThread.exit()
                except: pass
                self.mainThread = None
            # Hide progress bar
            self.progress_bar.hide()
            self.progress_bar.setValue(0)
            self.restart_msgbox = None # Close message box
            self.dict2_name_to_task.clear() # Clear task dictionary
            self.dict3_name_to_h5.clear() # Clear H5_Organized dictionary
            # Convert tab > Re-enable "Import Files" group and "Clear" button
            self.lineEdit.setEnabled(True)
            self.pushButton_2.setEnabled(True)
            self.pushButton_3.setEnabled(True)
            self.tableWidget.setEnabled(True)
            self.func_enable_reset_button( self.pushButton_3 )
            # Convert tab > "Abort" to "Run" button
            self.pushButton_1.setText( "Run" )
            self.pushButton_1.setStyleSheet( self.style_btn_run )
            self.pushButton_1.clicked.disconnect( self.func_abort_run )
            self.pushButton_1.clicked.connect( self.func_RUN )
            # Set state
            self.state_1x3_running = False
            self.state_1x2A_imported = True
            self.statusBar.showMessage( "Import > Aborted. Ready to run! Other optoins available." )
    

    
    def func_DV_change_dataset(self, item):
        """
        Change displayed database. Adjust Data Viewer tabs to the database.
        
        GUI Location: Data Viewer (left) > Dataset table
        """
        self.tabWidget_4.setEnabled(True)
        if not self.is_changing_databases and len(self.dict3_name_to_h5.keys()) > 0:
            self.clear_data_viewer()
            self.pushButton_79.setEnabled(True)
            # Data Viewer (left) > "Table" tab > "Filter" group > Disable "Clear All" button
            self.func_disable_reset_button( self.pushButton_57 )
            # Data Viewer (left) > "Table" tab > Re-enable "Full" button
            self.pushButton_79.setEnabled(True)
            # Data Viewer (left) > Set text
            self.curr_database = item.text()
            #curr_database = self.comboBox_62.currentText()
            if "^" in self.curr_database:
                res = self.curr_database.split("^")
                res = res[0] + "^\n" + res[1]
            else:
                res = self.curr_database
            # Data Viewer (right) > Fill Table
            self.h5: H5_Organized_New = self.dict3_name_to_h5[self.curr_database]
            self.tableView_3.setModel( self.h5.get_dataset() )
            self.tableView_3.resizeColumnsToContents()
            # Data Viewer (left) > "Table" tab > "Filter" group > Fill "Variable" combobox, if applicable
            self.var_min_max = deepcopy(self.h5.get_var_min_max())
            if self.var_min_max:
                if_anyvars = len(self.var_min_max) > 0
                self.comboBox_27.setEnabled(if_anyvars)
                if if_anyvars:
                    first_txt = "Choose a Storm ID" if self.h5.is_timeseries else self.comboBox_27.placeholderText()
                    self.comboBox_27.addItems([ first_txt, *list(self.var_min_max.keys()) ])
                    self.comboBox_27.setCurrentIndex(0)
                # Data Viewer (left) > Disable "Graph" tabs if current dataset is not Timeseries or Peaks
                self.tabWidget_4.setTabEnabled(1, self.h5.is_plottable)
                # Reset view of "Date Range for Variable" and "Date Range for Plot"
                self.groupBox_9.show()
                self.groupBox_11.show()

                # "Graph" tab > Reset list of chosen Storm IDs to plot.
                self.plot_stormIDs = []
                # Data Viewer (left) > If plottable...
                if self.h5.is_plottable:
                    # "Graph" tab > "Filter" group > Fill "Variable" combobox, if applicable
                    self.comboBox_28.setEnabled(if_anyvars)
                    if if_anyvars:
                        tmp = list(self.var_min_max.keys())
                        try:
                            tmp.remove("yyyymmddHHMM")
                            tmp.remove("Landfall Time")
                            tmp.remove("Peak Time")
                        except: pass
                        self.is_resetting_vars = True
                        self.comboBox_28.addItems([self.comboBox_28.placeholderText(), *tmp])
                        self.comboBox_28.setCurrentIndex(0)
                        self.is_resetting_vars = False
                    # Not all Peaks files have more than two date-times.
                    try:
                        # "Graph" tab > "Filter" group > Fill "Date Range for Time"
                        min, max = self.var_min_max["yyyymmddHHMM"]
                        # If only one date-time, then Date Ranges should not be activated.
                        self.only_one_dt = min == max
                        self.dateTimeEdit_21.setEnabled(not self.only_one_dt)
                        self.dateTimeEdit_22.setEnabled(not self.only_one_dt)
                        if self.only_one_dt:
                            # Disable "Reset" buton
                            self.func_disable_reset_button(self.pushButton_84)
                            # Hide Date Ranges
                            self.groupBox_9.hide()
                            self.groupBox_11.hide()
                            # Remove "yyyymmddHHMM" from Variable list in "Table" tab.
                            self.comboBox_27.removeItem( list(self.var_min_max).index("yyyymmddHHMM")+1 )
                        else:
                            # Enable "Reset" button
                            self.func_enable_reset_button(self.pushButton_84)
                            # Set the DateTime ranges.
                            self.dateTimeEdit_21.setDateTimeRange(min, max)
                            self.dateTimeEdit_21.setDateTime(min)
                            self.dateTimeEdit_22.setDateTimeRange(min, max)
                            self.dateTimeEdit_22.setDateTime(max)
                            # Disable "Date Range for Graph" comboboxes.
                            if self.h5.is_timeseries and not self.only_one_dt:
                                self.dateTimeEdit_21.setEnabled(False)
                                self.dateTimeEdit_22.setEnabled(False)
                    except: pass
                    self.func_judge_plotting()

                elif "yyyymmddHHMM" in self.var_min_max.keys():
                    min, max = self.var_min_max["yyyymmddHHMM"]
                    self.only_one_dt = min == max
                    self.pushButton_84.setEnabled(not self.only_one_dt)
                    if self.only_one_dt:
                        # Hide Date Ranges
                        self.groupBox_9.hide()
                        self.groupBox_11.hide()
                        # Remove "yyyymmddHHMM" from Variable list in "Table" tab.
                        self.comboBox_27.removeItem( list(self.var_min_max).index("yyyymmddHHMM")+1 )
            
            else: self.comboBox_27.setEnabled(False)

            # Data Viewer (left) > Table + "Graph" tabs > Manage "Storm ID"
            if self.h5.is_timeseries:
                # "Table" tab > "Storm ID"
                self.label_138.show()
                self.comboBox_62.show()
                # "Graph" tab > "Storm ID"
                self.label_143.show()
                self.comboBox_63.show()
                self.pushButton_85.show()
                self.pushButton_83.show()
                # "Table" tab > Disable "Current" button.
                self.pushButton_81.setEnabled(False)
                
                # BUG: Graph button is activated when time series is selected sometimes.
                
                self.label_3.show()
                self.label_3.setText("[No selected Storm IDs]")
                # Fill "Storm ID" dropdowns (Table)
                self.stormIDs = self.h5.get_stormIDs()
                if len(self.stormIDs) > 19:
                    self.comboBox_62.addItems( ["Current table", *self.stormIDs[:18], "-- Type for more --"] )
                else:
                    self.comboBox_62.addItems( ["Current table", *self.stormIDs] )
                self.comboBox_62.setCompleter( QCompleter(self.stormIDs, self.window) )
                self.comboBox_62.setCurrentIndex(0)
                # Fill "Storm ID" dropdowns (Plot)
                if len(self.stormIDs) > 20:
                    self.comboBox_63.addItems( [*self.stormIDs[:19], "-- Type for more --"] )
                else:
                    self.comboBox_63.addItems( self.stormIDs )
                self.comboBox_63.setCompleter( QCompleter(self.stormIDs, self.window) )
                self.comboBox_63.setCurrentIndex(0)

            else:
                # "Table" tab > "Filter" group > "Storm ID"
                self.label_138.hide()
                self.comboBox_62.hide()
                # "Graph" tab > "Filter" group > "Storm ID"
                self.label_143.hide()
                self.comboBox_63.hide()
                self.pushButton_85.hide()
                self.pushButton_83.hide()
                self.label_3.hide()

            # Set status.
            self.statusBar.showMessage( "Data Viewer" )
    

    
    def clear_data_viewer(self):
        """
        Common function to reset elements in Table, "Graph" tabs.
        """
        # Data Viewer (left) > "Table" tab > "Filter" group > Fill "Variable" combobox, if applicable
        self.comboBox_27.clear()
        self.pushButton_39.setEnabled(False) # "Add" button should not be enabled at this point under any circumstances.
        # Data Viewer (left) > "Table" tab > "Filter" group > Reset "Date Range"
        self.dateTimeEdit_19.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
        self.dateTimeEdit_19.setDateTime(QDateTime(2000,1,1,0,0,0))
        self.dateTimeEdit_20.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
        self.dateTimeEdit_20.setDateTime(QDateTime(2000,1,1,0,0,0))
        # Data Viewer (left) > "Table" tab > "Filter" group > Reset "Magnitude Range"
        self.doubleSpinBox_12.setRange(-1, 1)
        self.doubleSpinBox_12.setValue( 0 )
        self.doubleSpinBox_11.setRange(-1, 1)
        self.doubleSpinBox_11.setValue( 0 )
        # Data Viewer (left) > "Graph" tab > Disable "Plot" and "Clear" buttons
        self.func_disable_reset_button( self.pushButton_82 )
        self.func_disable_reset_button( self.pushButton_83 )
        # Data Viewer (left) > "Graph" tab > "Filter" group > Reset "Variable" combobox
        self.is_resetting_vars = True
        self.comboBox_28.clear()
        self.is_resetting_vars = False
        # Data Viewer (left) > "Graph" tab > Disable "Add" buttons
        self.pushButton_85.setEnabled(False)
        # Data Viewer (left) > Table + "Graph" tabs > Reset "Storm ID" dropdowns
        self.is_resetting_vars = True
        self.comboBox_62.clear()
        self.comboBox_63.clear()
        # Status
        self.str_filters = ""
        self.str_stormIDs = ""
        self.plainTextEdit.setPlainText("")

        self.is_resetting_vars = False
    

    
    def func_DVtable_export_current(self):
        """
        Exports the current state of Data Viewer (right). Only applies if any filters are added.
        
        GUI Location: Data Viewer (left) > "Table" tab > "Current" button
        """
        dataset_name = self.curr_database #self.comboBox_62.currentText()
        # Export storm ID dataset, if applicable.
        if self.h5.is_timeseries and self.is_stormid_applied: # If a storm ID is applied, not simply chosen.
            dataset_name += "_StormID_" + self.comboBox_62.currentText()
        self.h5.get_data_current().to_csv(dataset_name + ".csv", index=False)
    

    
    def func_DVtable_export_full(self):
        """
        Exports the full dataset, ignoring any filters.
        
        GUI Location: Data Viewer (left) > "Table" tab > "Full" button
        """
        self.h5.export_csv()
        self.pushButton_79.setEnabled(False) # Disable "Full" button
    

    #
    # Data Viewer (left) > "Table" tab > "Filter" group > "Add" button
    #
    def func_DVtable_add_filter(self):
        """
        Adds a filter to the current dataset.
        
        GUI Location: Data Viewer (left) > "Table" tab > "Filter" group > "Add" button
        """
        #curr_database = self.comboBox_62.currentText()
        self.func_enable_reset_button( self.pushButton_57 ) # Activate "Clear All" button
        self.pushButton_39.setEnabled(False) # Disable "Add" button
        # If "Storm ID" is chosen.
        if self.h5.is_timeseries and self.comboBox_62.isEnabled():
            stormID = self.comboBox_62.currentText()
            self.tableView_3.setModel( self.h5.get_stormID_subset( int(stormID) ) )
            self.tableView_3.resizeColumnsToContents() # Resize tableView
            self.comboBox_62.setEnabled(False) # Don't use "Storm ID" again until "Clear All"
            self.is_stormid_applied = True
            for var, min_and_max in self.h5.var_min_max_byID[stormID].items():
                self.var_min_max[var] = min_and_max
            # Update filter status.
            self.str_stormIDs = "Storm ID: " + stormID + "\n"
        
        # If "Variable" is chosen.
        else:
            var = self.comboBox_27.currentText()
            is_date = var in ["yyyymmddHHMM", "Landfall Time", "Peak Time"]
            # Get selected min/max
            new_min = self.func_Q_to_d(self.dateTimeEdit_19) if is_date else self.doubleSpinBox_12.value()
            new_max = self.func_Q_to_d(self.dateTimeEdit_20) if is_date else self.doubleSpinBox_11.value()
            # Update filter status.
            if self.str_filters == "": self.str_filters = "Filters: "
            else:                      self.str_filters += "; "
            self.str_filters += f"{var}: [{new_min}, {new_max}]"
            # Implement filter
            self.tableView_3.setModel( self.h5.set_filter( var, new_min, new_max, not self.is_stormid_applied ) )
            self.tableView_3.resizeColumnsToContents()
            self.dataset_filters.append(var)
            # Adjust app to new min/max
            if is_date:
                new_min_qdt = self.dateTimeEdit_19.dateTime()
                new_max_qdt = self.dateTimeEdit_20.dateTime()
                # Data Viewer > "Table" tab > Filter > Adjust "Date Range"
                self.dateTimeEdit_19.setDateTimeRange(new_min_qdt, new_max_qdt)
                self.dateTimeEdit_20.setDateTimeRange(new_min_qdt, new_max_qdt)
                # Data Viewer > "Graph" tab > Filter > Sync "Date Range"
                if var == "yyyymmddHHMM":
                    self.dateTimeEdit_21.setDateTimeRange(new_min_qdt, new_max_qdt)
                    self.dateTimeEdit_22.setDateTimeRange(new_min_qdt, new_max_qdt)
            else:
                # Data Viewer > "Table" tab > Filter > Adjust "Magnitude Range"
                self.doubleSpinBox_12.setRange(new_min, new_max)
                self.doubleSpinBox_11.setRange(new_min, new_max)
            # Adjust var's min and max
            self.var_min_max[var] = [new_min, new_max]
            keys = list(self.var_min_max.keys())
            keys.remove(var)
        
            # Adjust variables' mins and maxs (minus current variable "var")
            for v in keys:
                x = self.h5.df_current[v]
                # Check if entire column is "NaN"
                try: all_nan = all(np.isnan( np.array(x, float) ))
                except: all_nan = all([y == np.nan for y in x])
                if all_nan:
                    del self.var_min_max[v]
                else:
                    new_min = np.nanmin(x)
                    new_max = np.nanmax(x)
                    if v not in ["yyyymmddHHMM", "Landfall Time", "Peak Time"]:
                        new_min = np.around( new_min, decimals=self.dec )
                        new_max = np.around( new_max, decimals=self.dec )
                    self.var_min_max[v] = [new_min, new_max]

        self.plainTextEdit.setPlainText( self.str_stormIDs + self.str_filters )
        self.pushButton_81.setEnabled(True) # Enable "Current" button
        #self.statusBar.showMessage( "Data Viewer > Table > Active filters: " + ", ".join(self.dataset_filters) )
    

    
    def func_DVtable_clear_all_filters(self):
        """
        Removes all filters, resets the dataset to its original state.
        
        GUI Location: Data Viewer (left) > "Table" tab > "Filter" group > "Clear All" button
        """
        self.is_changing_databases = True # Prevent self.func_DVtable_change_var() from running
        self.is_resetting_vars = True # Prevent self.func_DVtable_check_datetime() and self.func_DVtable_check_magnitude() from running
        # Reset variables
        self.var_min_max = deepcopy(self.h5.get_var_min_max())
        self.will_apply_mag = False
        self.will_apply_date = False
        # Data Viewer (right) > Reset Table
        self.tableView_3.setModel( self.h5.get_dataset() )
        self.tableView_3.resizeColumnsToContents()
        # Data Viewer (left) > "Table" tab > "Filter" group > Reset "Variable" combobox
        self.comboBox_27.setCurrentIndex(0)
        # Data Viewer (left) > "Table" tab > "Filter" group > Reset "Date Range"
        self.dateTimeEdit_19.setEnabled(False)
        self.dateTimeEdit_19.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
        self.dateTimeEdit_19.setDateTime(QDateTime(2000,1,1,0,0,0))
        self.dateTimeEdit_20.setEnabled(False)
        self.dateTimeEdit_20.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
        self.dateTimeEdit_20.setDateTime(QDateTime(2000,1,1,0,0,0))
        # Data Viewer (left) > "Table" tab > "Filter" group > Reset "Magnitude Range"
        self.doubleSpinBox_12.setEnabled(False)
        self.doubleSpinBox_12.setRange(-1, 1)
        self.doubleSpinBox_12.setValue( 0 )
        #self.doubleSpinBox_12.setDecimals(self.dec)
        self.doubleSpinBox_11.setEnabled(False)
        self.doubleSpinBox_11.setRange(-1, 1)
        self.doubleSpinBox_11.setValue( 0 )
        #self.doubleSpinBox_11.setDecimals(self.dec)
        self.dataset_filters = []
        # Data Viewer (left) > "Table" tab > "Filter" group > Reset "Storm ID"
        if self.h5.is_timeseries:
            self.is_stormid_applied = False
            # Reset Storm ID dropdown.
            self.comboBox_62.setEnabled(True)
            self.comboBox_62.setCurrentIndex(0)
        # Data Viewer (left) > "Table" tab > "Filter" group > Disable "Clear All" button
        self.func_disable_reset_button( self.pushButton_57 )
        self.is_changing_databases = False
        self.is_resetting_vars = False
        self.pushButton_81.setEnabled(False) # Disable "Current" button
        # Set status
        self.str_filters = ""
        self.str_stormIDs = ""
        self.plainTextEdit.setPlainText("")
        #self.statusBar.showMessage( "Data Viewer > Table > Filters cleared." )
    

    
    def func_DVtable_tooltip_for_pushButton_102(self):
        """
        Generates tooltip for "Table" tab.
        
        GUI Location: Data Viewer (left) > "Table" tab > "?" button
		"""
        txt = ("*Export Table > Full*: Exports the whole dataset. Available at all times.\n\n"
               + "*Export Table > Current*: Exports the filtered or abridged state of the dataset.\n\n"
               + "*Filter section*: Filter by magnitude range, date range, or Storm ID (only for Timeseries data). Press Tab or click on another range to process your input.\n\n"
               + "*Add*: Disabled when range is already at min/max or no Storm ID is selected.\n\n"
               + "*Clear All*: Reverts dataset & variable ranges back to initial state.")
        msgBox = QMessageBox.information( self.window, 
                                          "Selecting a Dataset",
                                          txt, 
                                          QMessageBox.StandardButton.Ok, 
                                          QMessageBox.StandardButton.Ok )
    

    
    def func_DVtable_change_var(self):
        """
        Sets the minimum and maximum values for the selected variable.
        
        GUI Location: Data Viewer (left) > "Table" tab > "Filter" group > "Variable" dropdown
		"""
        if not self.is_changing_databases:
            var = self.comboBox_27.currentText()
            # Booleans
            is_var = var not in ["", self.comboBox_27.itemText(0)]
            is_date = var in ["yyyymmddHHMM", "Landfall Time", "Peak Time"]
            # Manage "Date Range for Variable"
            self.dateTimeEdit_19.setEnabled(is_var and is_date)
            self.dateTimeEdit_20.setEnabled(is_var and is_date)
            # Manage "Magnitude Range for Variable"
            self.doubleSpinBox_12.setEnabled(is_var and not is_date)
            self.doubleSpinBox_11.setEnabled(is_var and not is_date)
            # Manage "Storm ID" dropdown and "Add" button
            self.comboBox_62.setEnabled(not is_var and not self.is_stormid_applied)
            self.pushButton_39.setEnabled(False)
            
            # Data Viewer > Graph > Filter > Sync "Variable" dropdown
            if var != "yyyymmddHHMM": self.comboBox_28.setCurrentText(var)
            else:                     self.comboBox_28.setCurrentIndex(0)

            # Adjust widgets
            self.is_resetting_vars = True
            if is_var:
                min, max = self.var_min_max[var]
                if is_date: # New date range
                    self.dateTimeEdit_19.setDateTimeRange(min, max)
                    self.dateTimeEdit_19.setDateTime(min)
                    self.dateTimeEdit_20.setDateTimeRange(min, max)
                    self.dateTimeEdit_20.setDateTime(max)
                    # Reset "Magnitude Range for Variable"
                    self.doubleSpinBox_12.setRange(-1, 1)
                    self.doubleSpinBox_12.setValue(0)
                    self.doubleSpinBox_11.setRange(-1, 1)
                    self.doubleSpinBox_11.setValue(0)
                else: # New magnitude range
                    self.doubleSpinBox_12.setRange(min, max)
                    self.doubleSpinBox_12.setValue(min)
                    self.doubleSpinBox_11.setRange(min, max)
                    self.doubleSpinBox_11.setValue(max)
                    # Reset "Date Range for Variable"
                    self.dateTimeEdit_19.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
                    self.dateTimeEdit_19.setDateTime(QDateTime(2000,1,1,0,0,0))
                    self.dateTimeEdit_20.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
                    self.dateTimeEdit_20.setDateTime(QDateTime(2000,1,1,0,0,0))
            else:
                # Reset "Magnitude Range for Variable"
                self.doubleSpinBox_12.setRange(-1, 1)
                self.doubleSpinBox_12.setValue(0)
                self.doubleSpinBox_11.setRange(-1, 1)
                self.doubleSpinBox_11.setValue(0)
                # Reset "Date Range for Variable"
                self.dateTimeEdit_19.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
                self.dateTimeEdit_19.setDateTime(QDateTime(2000,1,1,0,0,0))
                self.dateTimeEdit_20.setDateTimeRange(QDateTime(1999,1,1,0,0,0), QDateTime(2001,1,1,0,0,0))
                self.dateTimeEdit_20.setDateTime(QDateTime(2000,1,1,0,0,0))
                # Check "Storm ID"
                if self.comboBox_62.currentText() != self.comboBox_62.placeholderText():
                    cond = self.comboBox_62.currentText() in self.stormIDs
                    self.pushButton_39.setEnabled( cond )
                else:
                    pass
                    #self.statusBar.showMessage( "Data Viewer > Table > Not able to filter yet." + s2 )
            self.is_resetting_vars = False
    

    
    def func_DVtable_change_stormID(self):
        """
        Handle change in Storm ID selection (Timeseries only).

        GUI Location: Data Viewer (left) > "Table" tab > "Filter" group > "Storm ID" dropdown
		"""
        if not self.is_resetting_vars:
            cond = self.comboBox_62.currentText() in self.stormIDs
            self.pushButton_39.setEnabled( cond )
    

    
    def func_DVtable_check_datetime(self):
        """
        Verifies user-inputed date range. [Possible redundancy.] Syncs with "Graph" tab.
        
        GUI Location: Data Viewer (left) > "Table" tab > "Filter" group > "Magnitude Range for Variable" group > "Start" & "End" datetime boxes
        """
        if not self.is_resetting_vars:
            var = self.comboBox_27.currentText()
            min_lim, max_lim = self.var_min_max[var]
            min = self.dateTimeEdit_19.dateTime()
            max = self.dateTimeEdit_20.dateTime()
            cond = bool((min > min_lim or max < max_lim) and min < max)
            self.pushButton_39.setEnabled( cond )
            # Sync with "Date Range" in "Graph" tab
            if var == "yyyymmddHHMM" and cond:
                self.dateTimeEdit_21.setDateTimeRange(min, max)
                self.dateTimeEdit_21.setDateTime(min)
                self.dateTimeEdit_22.setDateTimeRange(min, max)
                self.dateTimeEdit_22.setDateTime(max)
                self.will_apply_date = cond
    

    
    def func_DVtable_check_magnitude(self):
        """
        Verifies user-inputed magnitude range. [Possible redundancy.]
        
        GUI Location: Data Viewer (left) > "Table" tab > "Filter" group > "Magnitude Range for Variable" group > "Min" & "Max" boxes
        """
        if not self.is_resetting_vars:
            min_lim, max_lim = self.var_min_max[self.comboBox_27.currentText()]
            min = self.doubleSpinBox_12.value()
            max = self.doubleSpinBox_11.value()
            self.will_apply_mag = bool((min > min_lim or max < max_lim) and min < max)
            self.pushButton_39.setEnabled( self.will_apply_mag )
    

    #
    # Data Viewer (left) > "Graph" tab > "Plot" button 
    #
    def func_DVplot_plot(self):
        """
        Plots a graph. Displays graph on default browser. Exports graph to an interactive HTML file, but PNG graphs can be exported from there.
        
        GUI Location: Data Viewer (left) > "Graph" tab > "Plot" button
        """
        txt = "An HTML file will be saved to the current directory and displayed in your default browser. You can save the graph as a PNG object from there.\n"
        if self.h5.is_timeseries:
            if len(self.plot_stormIDs) == 1:
                txt += "\nThis will apply to Storm ID #" + self.comboBox_63.currentText() + ".\n"
            else:
                txt += "\nThis will apply to the following Storm IDs: " + ", ".join(self.plot_stormIDs) + ".\n"
        txt += "\nWould you like to continue?"
        msgBox = QMessageBox.information( self.window, "About to Plot", txt, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes )
        
        if msgBox == QMessageBox.StandardButton.Yes:
            more_than_1 = len(self.plot_stormIDs) != 1
            # Save names for exporting file.
            self.active_var = self.comboBox_28.currentText()
            self.active_sID = "+".join(self.plot_stormIDs) if more_than_1 else self.comboBox_63.currentText()
            # If any date-time modified, take both. If not, take neither.
            min_dt = None; max_dt = None
            if len(self.plot_stormIDs) == 1 and not self.h5.is_timeseries:
                a = self.func_Q_to_d( self.dateTimeEdit_21 )
                b = self.func_Q_to_d( self.dateTimeEdit_22 )
                if a < b:
                    min_dt = a
                    max_dt = b
            # Graph here
            if self.h5.is_timeseries:
                df = self.h5.get_plot_data( self.active_var, min_dt, max_dt, stormIDs=self.plot_stormIDs, only_one_dt=self.only_one_dt )
                title = self.active_var + (" for Storm IDs " if more_than_1 else " for Storm ID ") + self.active_sID
                if more_than_1:
                    self.fig = px.line( df, x="Time Step", y=self.active_var, color="Storm ID", title=title, hover_data=['Date-Time'] )
                    self.fig.update_layout(hovermode="x") # Modify graph tooltip here
                elif self.only_one_dt:
                    self.fig = px.line( df, x="Storm ID", y=self.active_var, title=title )
                    self.fig.update_layout(hovermode="x") # Modify graph tooltip here
                else:
                    self.fig = px.line( df, x="Date-Time", y=self.active_var, title=title )
                    self.fig.update_layout(hovermode="x") # Modify graph tooltip here
                # Name
                t1 = "Timestep x " if more_than_1 else "Datetime x "
                t2 = "s " if more_than_1 else " "
                title = t1 + self.active_var + " (Storm ID" + t2 + self.active_sID + ") for " + self.curr_database #self.comboBox_62.currentText()
            
            else:
                df = self.h5.get_plot_data( self.active_var, min_dt, max_dt, only_one_dt=self.only_one_dt )
                title = self.active_var
                if self.only_one_dt:
                    self.fig = px.line( df, x="Storm ID", y=self.active_var, title=title )
                else:
                    self.fig = px.line( df, x="Date-Time", y=self.active_var, title=title )
                self.fig.update_layout(hovermode="x") # Modify graph tooltip here
                # Filename
                title = "Datetime x " + self.active_var + " for " + self.curr_database #self.comboBox_62.currentText()

            # Output
            fig_output = po.plot(self.fig, 
                                 filename = f"{title}.html",
                                 image_filename= f"{title}.png",
                                 auto_open = False)
            os.replace(f"{DIR_PROGRAM}{os.sep}{title}.html", f"{DIR_RESUTLS}{os.sep}{title}.html")
            x = Popen( [open_directory, DIR_RESUTLS] )
            time.sleep(1)
            x.kill()
            # Disable "Plot" button.
            self.pushButton_82.setStyleSheet( self.style_btn_normal )
            self.pushButton_82.setEnabled(False)
            # Change state
            self.state_2x2A_justplot = True
            self.state_2x2B_aplot = True
            chime.success()
    

    
    def func_DVplot_tooltip_for_pushButton_104(self):
        """
        Generates tooltip for "Graph" tab.
        
        GUI Location: Data Viewer (left) > "Graph" tab > "?" button
        """
        txt = "Must choose a variable to plot! Date range is optional.\nTimeseries only: Must also choose at least one Storm ID! Date range only works for one Storm ID."
        msgBox = QMessageBox.information( self.window, 
                                          "Selecting a Dataset", 
                                          txt, 
                                          QMessageBox.StandardButton.Ok, 
                                          QMessageBox.StandardButton.Ok )
    

    #
    # Data Viewer (left) > "Graph" tab > "Variable" combobox
    #
    def func_DVplot_change_var(self):
        """
        Handles variable change from the "Graph" tab.
        
        GUI Location: Data Viewer (left) > "Graph" tab > "Variable" combobox
        """
        if not self.is_resetting_vars and self.comboBox_28.count() != 0: # BUG FIX: There must be a variable
            self.func_judge_plotting()
            # Change state
            self.state_2x2A_justplot = False
    

    
    def func_DVplot_change_stormID(self):
        """
        Handles the change in Storm ID from the "Graph" tab.
        
        GUI Location: Data Viewer (left) > "Graph" tab > "Storm ID" dropdown
        """
        if not self.is_resetting_vars and self.comboBox_63.count() != 0: # BUG FIX: There must be a variable
            b1 = self.comboBox_63.currentText() in self.stormIDs
            b2 = self.comboBox_63.currentText() not in self.plot_stormIDs
            self.pushButton_85.setEnabled(b1 and b2)
            # Change state.
            self.state_2x2A_justplot = False
    

    
    def func_DVplot_add_stormID(self):
        """
        Add the data from a Storm ID to the plot (Timeseries only).
        
        GUI Location: Data Viewer (left) > "Graph" tab > "Add" button
        """
        self.plot_stormIDs.append( self.comboBox_63.currentText() )
        more_than_1 = len(self.plot_stormIDs) > 1
        # Sort list of IDs
        if more_than_1:
            self.plot_stormIDs = [str(x) for x in sorted([int(x) for x in self.plot_stormIDs])]
        # Handle date-time comboboxes
        self.dateTimeEdit_21.setEnabled(not more_than_1)
        self.dateTimeEdit_22.setEnabled(not more_than_1)
        if len(self.plot_stormIDs) == 1:
            min, max = self.h5.var_min_max_byID[ self.comboBox_63.currentText() ]["yyyymmddHHMM"]
            self.dateTimeEdit_21.setDateTimeRange(min, max)
            self.dateTimeEdit_21.setDateTime(min)
            self.dateTimeEdit_22.setDateTimeRange(min, max)
            self.dateTimeEdit_22.setDateTime(max)
        # Disable "Add" button
        self.pushButton_85.setEnabled(False)
        # Show storm IDs
        if more_than_1:
            self.label_3.setText( "Selected Storm IDs: " + ", ".join(self.plot_stormIDs) )
            self.func_disable_reset_button( self.pushButton_84 )
        elif len(self.plot_stormIDs) == 1:
            self.label_3.setText( "Selected Storm ID: " + self.comboBox_63.currentText() )
        # Set Clear button
        self.pushButton_83.setEnabled(True)
        self.pushButton_83.setStyleSheet( self.style_btn_reset_on )
        # Change state.
        self.state_2x2A_justplot = False
        # Check if plottable
        self.func_judge_plotting()
    

    
    def func_DVplot_clear_stormIDs(self):
        """
        Clears the selection of Storm ID(s) (Timeseries only).
        
        GUI Location: Data Viewer (left) > "Graph" tab > "Clear" button
        """
        self.plot_stormIDs = []
        self.label_3.setText("[No selected Storm IDs]")
        # Reset "Clear" button
        self.pushButton_83.setEnabled(False)
        self.pushButton_83.setStyleSheet( self.style_btn_normal )
        # Reset date-time comboboxes
        if self.pushButton_84.isEnabled():
            self.func_DVplot_reset_daterange()
        # Check if plottable
        self.func_judge_plotting()
        # Check if current Storm ID is ok
        self.func_DVplot_change_stormID()
    

    
    def func_judge_plotting(self):
        """
        Judges whether or not the plot can be done based on the user's selection.
        """
        is_var = self.comboBox_28.currentIndex() != 0
        is_ts = self.h5.is_timeseries # Is time series
        is_stormID = True # If not time series, don't worry
        if is_ts: is_stormID = len(self.plot_stormIDs) > 0
        is_good = is_var and is_stormID
        # Modify "Plot" button
        self.pushButton_82.setEnabled(is_good)
        self.pushButton_82.setStyleSheet( self.style_btn_run if is_good else self.style_btn_normal )
        # Set status
        txt = "Data Viewer > Graph > "
        if not is_good:
            if is_ts:
                if not is_var and not is_stormID: # If Variable and Storm ID are not valid (Timeseries)
                    txt += "Please select a Variable and a Storm ID."
                elif not is_stormID: # If Storm ID is not valid (Timeseries)
                    txt += "Please select a Storm ID."
                else: # If Variable is not valid (Timeseries)
                    txt += "Please select a Variable."
            else: # If Variable is not valid (Peaks)
                txt += "Please select a Variable."
        else:
            txt += "Ready to plot!"
        #self.statusBar.showMessage( txt )
    

    
    def func_DVplot_check_daterange(self):
        """
        If the date-time range is modified, handle "Reset" button.
        
        GUI Location: Data Viewer (left) > "Graph" tab > "Date Range for Variable" group > "Start" & "End" datetime boxes
        """
        now_min, now_max = self.var_min_max["yyyymmddHHMM"] # Sync with Table view
        min = self.dateTimeEdit_21.dateTime()
        max = self.dateTimeEdit_22.dateTime()
        if bool(min > now_min or max < now_max):
            self.func_enable_reset_button( self.pushButton_84 )
        else:
            self.func_disable_reset_button( self.pushButton_84 )
        # Make sure min <= max
        self.pushButton_82.setEnabled(min <= max)
        self.pushButton_82.setStyleSheet( self.style_btn_normal if min > max else self.style_btn_run )

    
    
    def func_DVplot_reset_daterange(self):
        """
        Resets the date-time range to default min/max values.
        
        GUI Location: Data Viewer (left) > "Graph" tab > "Reset" button
        """
        if len(self.plot_stormIDs) == 1:
            min, max = self.h5.var_min_max_byID[ self.comboBox_63.currentText() ]["yyyymmddHHMM"]
        else:
            min, max = self.var_min_max["yyyymmddHHMM"] # Sync with Table view
        self.dateTimeEdit_21.setDateTimeRange(min, max)
        self.dateTimeEdit_21.setDateTime(min)
        self.dateTimeEdit_22.setDateTimeRange(min, max)
        self.dateTimeEdit_22.setDateTime(max)
        # If plot is already made, then new date-range is different from old date-range.
        if self.state_2x2A_justplot:
            self.pushButton_82.setEnabled(True)
            self.pushButton_82.setStyleSheet( self.style_btn_run )
            self.state_2x2A_justplot = False






if __name__ == '__main__':
    win = QMainWindow()
    ui = StormSim_Converter(win)
    win.show()
    time.sleep(1)
    splash.finish(win)
    sys.exit( app.exec() )