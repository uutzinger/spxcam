from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, QApplication, QDesktopWidget, QDialog, QFileDialog,
                             QHBoxLayout, QLabel, QMainWindow, QToolBar, QVBoxLayout, QWidget, uic)
import pkg_resources
from helpers.serial_helper import Serial

if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    
class main_window(QMainWindow):
    """Create the main window that stores all of the widgets necessary for the application."""

    def __init__(self, ser: Serial, parent=None):
        """Initialize the components of the main window."""
        super(main_window, self).__init__(parent)

        QMainWindow.__init__(self)
        uic.loadUi('ui/main_window.ui', self)

        window_icon = pkg_resources.resource_filename('camera_gui.images',
                                                      'ic_insert_drive_file_black_48dp_1x.png')
        self.setWindowIcon(QIcon(window_icon))
        
        # Original
        self.Clear_Output.clicked.connect(self.pushButton_SerialClearOutput)       
        self.UiComponents()  #setting DropDown
        
        self.menu_bar=self.menuBar() # menuBar      
        
        #self.about_dialog = AboutDialog()

        #self.status_bar = self.statusBar()
        #self.status_bar.showMessage('Ready', 5000)

        #self.help_menu()
        # self.tool_bar_items()

        self.ser=ser

    def UiComponents(self):
       
        channel_list = [sublist[1] for sublist in self.ser.ports]
        self.comboBoxDropDown_SerialPorts.addItems(channel_list)   
        
        baudSelection = map(str, self.ser.baudrates) 
        self.comboBoxDropDown_SerialPorts_Baudrates.addItems(baudSelection)
                
        self.comboBoxDropDown_SerialPorts_Baudrates.setCurrentIndex(len(self.ser.baudrates)-1) 
        self.comboBoxDropDown_SerialPorts_Baudrates.activated.connect(self.activated)
        self.comboBoxDropDown_SerialPorts_Baudrates.currentTextChanged.connect(self.text_changed)
        self.comboBoxDropDown_SerialPorts_Baudrates.currentIndexChanged.connect(self.index_changed)
              
