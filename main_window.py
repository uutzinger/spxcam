############################################################################################
# Multispectral Camera User Interface
# Handles Light Source, Camera, and Serial Communication
# Urs Utzinger, 2022, 2023
############################################################################################
# ** https://realpython.com/learning-paths/pyqt-gui-programming/
# CSC-121, Graphical Python Programming, Using 2 QThread objects to emit signals to a Python GUI App
#
# Example large python QT program    
# https://gitlab.com/william.belanger/obsuite
#
# Matplot
# https://codeloop.org/how-to-embed-matplotlib-graph-in-pyqt5/
# https://stackoverflow.com/questions/61530741/put-a-matplotlib-plot-as-a-qgraphicsitem-into-a-qgraphicsview

# Number of Light Sources
numChannels = 13

# QT imports
from PyQt5 import QtCore, QtWidgets, QtGui, uic
from PyQt5.QtCore import pyqtSignal, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QLineEdit, QSlider, QPushButton, QCheckBox
from PyQt5.QtGui import QIcon

# System
import logging

# Numerical
import numpy as np

# Custom imports
from helpers.Qserial_helper      import QSerial, QSerialUI
from helpers.Qlightsource_helper import QLightSource
from helpers.Qcamera_helper      import QCamera, QCameraUI, cameraType
# from helpers.Qdisplay_helper     import QDisplay, QDisplayUI
# from Processing_helper           import QDataCube

# QT
# Deal with high resolution displays
if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

###########################################################################################
# Main Window
###########################################################################################

class mainWindow(QMainWindow):
    """
    Create the main window that stores all of the widgets necessary for the application.
    """
        
    #-------------------------------------------------------------------------------------
    # Initialize
    #-------------------------------------------------------------------------------------

    def __init__(self, parent=None):
        """
        Initialize the components of the main window.
        This will create the connections between slots and signals in both directions.
        
        Serial:
        Create serial worker and move it to separate thread.

        Lightsource:        
        ...
        
        Camera:
        ...
        """
        super(mainWindow, self).__init__(parent) # parent constructor
        
        self.logger = logging.getLogger("Main___")

        #----------------------------------------------------------------------------------------------------------------------
        # User Interface
        #----------------------------------------------------------------------------------------------------------------------
        self.ui = uic.loadUi('mainWindow.ui', self)
        # window_icon = pkg_resources.resource_filename('camera_gui.images', 'camera_48.png')
        # self.setWindowIcon(QIcon(window_icon))
        self.setWindowTitle("Camera GUI")

        #----------------------------------------------------------------------------------------------------------------------
        # Serial
        #----------------------------------------------------------------------------------------------------------------------
       
        # Serial Thread 
        self.serialThread = QThread()                                                      # create QThread object
        self.serialThread.start()                                                          # start thread which will start worker

        # Create user interface hook for serial
        self.serialUI     = QSerialUI(ui=self.ui)                                          # create serial userinterface object

        # Create serial worker
        self.serialWorker = QSerial()                                                      # create serial worker object

        # Connect worker / thread
        self.serialWorker.finished.connect(         self.serialThread.quit               ) # if worker emits finished quite worker thread
        self.serialWorker.finished.connect(         self.serialWorker.deleteLater        ) # delete worker at some time
        self.serialThread.finished.connect(         self.serialThread.deleteLater        ) # delete thread at some time

        # Signals from Serial to Serial-UI
        self.serialWorker.textReceived.connect(     self.serialUI.on_SerialReceivedText  ) # connect text display to serial receiver signal
        self.serialWorker.newPortListReady.connect( self.serialUI.on_newPortListReady    ) # connect new port list to its ready signal
        self.serialWorker.newBaudListReady.connect( self.serialUI.on_newBaudListReady    ) # connect new baud list to its ready signal
        self.serialWorker.serialStatusReady.connect(self.serialUI.on_serialStatusReady   ) # connect display serial status to ready signal

        # Signals from Serial-UI to Serial
        self.serialUI.changePortRequest.connect(    self.serialWorker.on_changePortRequest    ) # conenct changing port
        self.serialUI.closePortRequest.connect(     self.serialWorker.on_closePortRequest     ) # connect close port
        self.serialUI.changeBaudRequest.connect(    self.serialWorker.on_changeBaudRateRequest) # connect changing baudrate
        self.serialUI.scanPortsRequest.connect(     self.serialWorker.on_scanPortsRequest     ) # connect request to scan ports
        self.serialUI.scanBaudRatesRequest.connect( self.serialWorker.on_scanBaudRatesRequest ) # connect request to scan baudrates
        self.serialUI.setupReceiverRequest.connect( self.serialWorker.on_setupReceiverRequest ) # connect start receiver
        self.serialUI.startReceiverRequest.connect( self.serialWorker.on_startReceiverRequest ) # connect start receiver
        self.serialUI.sendTextRequest.connect(      self.serialWorker.on_sendTextRequest      ) # connect sending text
        self.serialUI.sendLinesRequest.connect(     self.serialWorker.on_sendLinesRequest     ) # connect sending lines of text
        self.serialUI.serialStatusRequest.connect(  self.serialWorker.on_serialStatusRequest  ) # connect request for serial status
        self.serialUI.finishWorkerRequest.connect(  self.serialWorker.on_stopWorkerRequest    ) # connect finish request

        self.serialWorker.moveToThread(self.serialThread)                                       # move worker to thread

        self.serialUI.scanPortsRequest.emit()                                                   # request to scan for serial ports
        self.serialUI.setupReceiverRequest.emit()                                               # establishes QTimer in the QThread from above
                                                                                                # can not establish timer in init function because
                                                                                                # its executed in parent's thread

        # Signals from User Interface to Serial-UI

        # User selected Port or Baud 
        self.ui.comboBoxDropDown_SerialPorts.currentIndexChanged.connect(self.serialUI.on_comboBoxDropDown_SerialPorts )
        self.ui.comboBoxDropDown_BaudRates.currentIndexChanged.connect(  self.serialUI.on_comboBoxDropDown_BaudRates   )
        # User clicked scan ports, send, clear or save
        self.ui.pushButton_SerialScan.clicked.connect(                   self.serialUI.on_pushButton_SerialScan        ) # Scan for ports
        self.ui.pushButton_SerialSend.clicked.connect(                   self.serialUI.on_serialMonitorSend   ) # Send text to serial port
        self.ui.lineEdit_SerialText.returnPressed.connect(               self.serialUI.on_serialMonitorSend   ) # Send text as soon as enter key is pressed
        self.ui.pushButton_SerialClearOutput.clicked.connect(            self.serialUI.on_pushButton_SerialClearOutput ) # Clear serial receive window
        self.ui.pushButton_SerialSave.clicked.connect(                   self.serialUI.on_pushButton_SerialSave        ) # Save text from serial receive window
        # User hit up/down arrow in serial lineEdit
        self.shortcutUpArrow = QtWidgets.QShortcut(QtGui.QKeySequence.MoveToPreviousLine, self.ui.lineEdit_SerialText, self.serialUI.on_serialMonitorSendUpArrowPressed)
        self.shortcutDownArrow = QtWidgets.QShortcut(QtGui.QKeySequence.MoveToNextLine, self.ui.lineEdit_SerialText, self.serialUI.on_serialMonitorSendDownArrowPressed)

        # Done with Serial
        self.logger.log(logging.INFO, "[{}]: serial initialized.".format(int(QThread.currentThreadId())))
        
        #----------------------------------------------------------------------------------------------------------------------
        # Light Source 
        #----------------------------------------------------------------------------------------------------------------------
        
        # Light Source Worker        
        self.lightSourceWorker = QLightSource(ui=self.ui)

        # Connect Signals
        self.lightSourceWorker.sendTextRequest.connect( self.serialWorker.on_sendTextRequest ) # connect sending text
        self.lightSourceWorker.sendLinesRequest.connect( self.serialWorker.on_sendLinesRequest) # connect sending lines of text
        self.lightSourceWorker.startReceiverRequest.connect( self.serialWorker.on_startReceiverRequest ) # connect start receiver
        self.lightSourceWorker.connectLightSourceRequest.connect( lambda: self.serialWorker.textReceived.connect(self.lightSourceWorker.on_ChannelSettings) ) 
        self.lightSourceWorker.disconnectLightSourceRequest.connect( lambda: self.serialWorker.textReceived.disconnect(self.lightSourceWorker.on_ChannelSettings) ) 
        
        # Pushbutton manual On/Off
        for channel in range(numChannels):
            pushButton = self.ui.findChild(QPushButton, "pushButton_TurnOnChannel"+str(channel+1))
            pushButton.setCheckable(True)
            pushButton.setText("Off")
            pushButton.clicked.connect(self.lightSourceWorker.on_pushButton_TurnOnChannel)

        # Intensity Slider
        for channel in range(numChannels):
            horizontalSlider = self.ui.findChild(QSlider, "horizontalSlider_Channel"+str(channel+1))
            horizontalSlider.setMinimum(0)  
            horizontalSlider.setMaximum(1000)
            horizontalSlider.valueChanged.connect( self.lightSourceWorker.on_IntensitySliderChanged )
            horizontalSlider.sliderReleased.connect( self.lightSourceWorker.on_IntensitySliderReleased )

        # Intensity Line Edit
        for channel in range(numChannels):
            lineEdit = self.ui.findChild(QLineEdit, "lineEdit_Channel"+str(channel+1))
            lineEdit.returnPressed.connect( self.lightSourceWorker.on_IntensityLineEditChanged )
                
        # "turn off all channels"
        self.ui.pushButton_TurnOffAllChannels.clicked.connect(      self.lightSourceWorker.turnOffAllChannels )
        # "enable auto advance"
        self.ui.pushButton_EnableAutoAdvance.clicked.connect(       self.lightSourceWorker.setAutoAdvanceOn )
        # "disable auto advance"
        self.ui.pushButton_DisableAutoAdvance.clicked.connect(      self.lightSourceWorker.setAutoAdvanceOff )
        # "query current settings"        
        self.ui.pushButton_QueryLightSourceSettings.clicked.connect(self.lightSourceWorker.queryChannelSettings ) 
        # "save settings (eeprom)"
        self.ui.pushButton_SaveLightSourceSettings.clicked.connect( self.lightSourceWorker.storeChannelSettings )
        # "load settings (eeprom)"
        self.ui.pushButton_LoadLightSourceSettings.clicked.connect( self.lightSourceWorker.loadChannelSettings )

        # Checkbox Enable/Disable Channel
        for channel in range(numChannels):
            checkBox = self.ui.findChild( QCheckBox, "checkBox_MeasureChannel"+str(channel+1))
            checkBox.stateChanged.connect( self.lightSourceWorker.on_enableChannel)
                                    
        self.logger.log(logging.INFO, "[{}]: light source initialized.".format(int(QThread.currentThreadId())))

        #----------------------------------------------------------------------------------------------------------------------
        # Camera
        #----------------------------------------------------------------------------------------------------------------------
        
        # Camera capture thread
        self.cameraThread = QThread()                                                      # create QThread object
        self.cameraThread.start()                                                          # start thread which will start worker

        # Create user interface hook for camera
        self.cameraUI     = QCameraUI(ui=self.ui)                                          # create serial user interface object

        # Create camera worker
        self.cameraWorker = QCamera()

        # Connect worker / thread
        self.cameraWorker.finished.connect(         self.cameraThread.quit               ) # if worker emits finished quite worker thread
        self.cameraWorker.finished.connect(         self.cameraWorker.deleteLater        ) # delete worker at some time
        self.cameraThread.finished.connect(         self.cameraThread.deleteLater        ) # delete thread at some time

        # Signals from Camera to Camera-UI
        self.cameraWorker.fpsReady.connect(         self.cameraUI.on_FPSINReady )
        self.cameraWorker.newCameraListReady.connect(self.cameraUI.on_newCameraListReady  ) #
        
        # Signals from Camera to processWorker
        self.cameraWorker.imageDataReady.connect(   self.processWorker.on_imageDataReady )

        # Signals from Processor to Camera-UI
        # self.processWorker.fpsReady.connect(          self.cameraUI.on_FPSOUTReady )
        # self.processWorker.newImageDataReady.connect( self.cameraUI.on_newImageDataReady )

        # Signals from Camera-UI to Camera
        self.cameraUI.changeCameraRequest.connect( self.cameraWorker.on_changeCamera )     # cameraWorker shall change camera
        self.cameraUI.changeExposureRequest.connect( self.cameraWorker.on_changeExposure)  # cameraWorker shall change exposure
        self.cameraUI.changeFrameRateRequest.connect(self.cameraWorker.on_changeFrameRate) # cameraWorker shall change frame rate
        self.cameraUI.changeBinningRequest.connect(self.cameraWorker.on_changeBinning)     # cameraWorker shall change binning
        self.cameraUI.startCameraRequest.connect(self.cameraWorker.on_startCamera)         # cameraWorker shall start camera
        self.cameraUI.stopCameraRequest.connect(self.cameraWorker.on_stopCamera)           # cameraWorker shall stop camera
        self.cameraUI.scanCameraRequest.connect( self.cameraWorker.on_scanCameras )        # connect changing port
        # on_closeCamera
        
        # Signals from User Interface to Camera-UI
        # User clicked scan camera, calibrate, start, stop           
        self.ui.pushButton_CameraStart.clicked.connect( self.cameraUI.on_Stop )
        self.ui.pushButton_CameraStop.clicked.connect( self.cameraUI.on_Start )
        self.ui.pushButton_CameraCalibrate.clicked.connect( self.cameraUI.on_Calibrate )
        self.ui.pushButton_CameraScan.clicked.connect( self.cameraUI.on_ScanCamera )
        # User selected camera
        self.ui.comboBoxDropDown_Cameras.currentIndexChanged.connect( self.cameraUI.on_ChangeCamera) # connect changing camera
        # User selected binning, entered exposure time, frame rate
        self.ui.comboBox_SelectBinning.currentIndexChanged.connect( self.cameraUI.on_ChangeBinning)  # connect changing binning
        self.ui.lineEdit_CameraFrameRate.returnPressed.connect( self.cameraUI.on_FrameRateChanged )
        self.ui.lineEdit_CameraExposureTime.returnPressed.connect( self.cameraUI.on_ExposureTimeChanged )

        self.cameraWorker.moveToThread(self.cameraThread)                                       # move worker to thread

        self.cameraUI.scanCameraRequest.emit()                                                  # request to scan for cameras

        self.logger.log(logging.INFO, "[{}]: camera initialized.".format(int(QThread.currentThreadId())))


        #----------------------------------------------------------------------------------------------------------------------
        # Processors
        #----------------------------------------------------------------------------------------------------------------------
        
        # Camera capture thread
        self.processThread = QThread()                                                      # create QThread object
        self.processThread.start()                                                          # start thread which will start worker

        # Flatfield
        # flatfield = np.zeros((depth, height, width), dtype=np.uint16)
        
        # flatfield[0, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit0', dtype='float32', delimiter=','))
        # flatfield[1, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit1', dtype='float32', delimiter=','))
        # flatfield[2, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit2', dtype='float32', delimiter=','))
        # flatfield[3, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit3', dtype='float32', delimiter=','))
        # flatfield[4, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit4', dtype='float32', delimiter=','))
        # flatfield[5, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit5', dtype='float32', delimiter=','))
        # flatfield[6, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit6', dtype='float32', delimiter=','))
        # flatfield[7, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit7', dtype='float32', delimiter=','))
        # flatfield[8, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit8', dtype='float32', delimiter=','))
        # flatfield[9, :,:]=np.unit16(2**8 * np.loadtxt('configs\fit9', dtype='float32', delimiter=','))
        # flatfield[10,:,:]=np.unit16(2**8 * np.loadtxt('configs\fit10', dtype='float32', delimiter=','))
        # flatfield[11,:,:]=np.unit16(2**8 * np.loadtxt('configs\fit12', dtype='float32', delimiter=','))
        # flatfield[12,:,:]=np.unit16(2**8 * np.loadtxt('configs\fit12', dtype='float32', delimiter=','))
        # flatfield[13,:,:]=np.unit16(2**8 * np.loadtxt('configs\background', dtype='float32', delimiter=','))

        #----------------------------------------------------------------------------------------------------------------------
        # Finish up
        #----------------------------------------------------------------------------------------------------------------------
        self.show() 


###########################################################################################
# Testing Main Window
###########################################################################################

if __name__ == "__main__":
    import sys
    from PyQt5 import QtWidgets
    import logging
    
    # set logging lelvel
    # CRITICAL  50
    # ERROR     40
    # WARNING   30
    # INFO      20
    # DEBUG     10
    # NOTSET     0
    logging.basicConfig(level=logging.DEBUG)
    
    app = QtWidgets.QApplication(sys.argv)
    
    win = mainWindow()
    d = app.desktop()
    scalingX = d.logicalDpiX()/96.0
    scalingY = d.logicalDpiY()/96.0
    win.resize(int(1200*scalingX), int(620*scalingY))
    win.show()
    sys.exit(app.exec_())
    
