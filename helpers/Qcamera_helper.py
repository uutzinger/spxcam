############################################################################################
# QT Camera Helper Class
############################################################################################
# ------------------------------------------------------------------------------------------
# Urs Utzinger
# University of Arizona 2022
# ------------------------------------------------------------------------------------------
# July 2022: initial work
############################################################################################

############################################################################################
# Helpful readings:
# ------------------------------------------------------------------------------------------
# https://www.youtube.com/watch?v=dTDgbx-XelY
# http://qtandopencv.blogspot.com/2020/06/asynchronous-video-capture-written-by.html
############################################################################################

# System
from cmath import pi
import logging
import time
import platform
import os
import sys
from enum import Enum
# Numerical Tools
import numpy as np
# QT
from PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, QStandardPaths
from PyQt5.QtWidgets import QLineEdit, QSlider, QCheckBox, QLabel, QFileDialog,  QGraphicsScene, QGraphicsPixmapItem
from PyQt5.QtGui import QImage,QPixmap
# Supported Cameras
import PySpin
import cv2

# TODO CHECK INTO SEPARATE FILES OR NOT

from helpers.BlackFly import BlackflyCapture
from helpers.OpenCV import OpenCVCapture
# Processing
from helpers.Processing_helper import QDataCube

NUM_CHANNELS = 14

class cameraType(Enum):
    opencv   = 0    # supported
    blackfly = 1    # supported
    nano     = 2    #
    rtp      = 3    #
    rtsp     = 4    #
    libcam   = 5    #
    pi       = 6    #

###########################################################################################
# Q CameraUI Class
###########################################################################################
# How to add image to Graphics View and update it with thread
#    https://stackoverflow.com/questions/51129840/playing-image-sequence-in-qgraphicsview-mysterious-memory-leak
# OpenCV to QT
#   https://amin-ahmadi.com/2018/03/29/how-to-read-process-and-display-videos-using-qt-and-opencv/
#   https://codeloop.org/pyqt5-qgraphicview-and-qgraphicscene-introduction/
#   https://codeloop.org/pyqt5-how-to-add-image-in-pyqt-window/
#   https://python.hotexamples.com/examples/PyQt5.QtWidgets/QGraphicsScene/addItem/python-qgraphicsscene-additem-method-examples.html

class QCameraUI(QObject):
    """ 
    Camera User Interface Interactions

    Signals
        = For cameraWorker
        scanCameraRequest              # cameraWorker shall scan cameras
        changeCameraRequest            # cameraWorker shall change camera
        changeExposureRequest          # cameraWorker shall change exposure
        changeFrameRateRequest         # cameraWorker shall change frame rate
        changeBinningRequest           # cameraWorker shall change binning
        startCameraRequest             # cameraWorker shall start camera
        stopCameraRequest              # cameraWorker shall stop camera
        setDisplayedChannels           # cameraWorker shall set displayed channels


    Slots
        = Forward requests to cameraWorker
        on_Start                # check selected measurement and display channels and emit setDisplayChannels
        on Stop                 # emit signal to CameraWorker
        on_Calibrate            # emit signal to CameraWorker
        on_ScanCameras          # emit signal to CameraWorker
        on_ChangeCamera         # emit signal to CameraWorker
        on_FrameRateChanged     # emit signal to CameraWorker
        on_ExposureTimeChanged  # emit signal to CameraWorker
        on_ChangeBinning      # emit signal to CameraWorker

        = Update UI
        on_FPSINReady           # update number on display
        on_FPSOUTReady          # update number on display
        on_ImageDataReady       # display it        
        on_newCameraListReady   # populate camera list on pull down menu
        on_newImageDataReady    # cameraWorker returns new image data
        
    This section can not go to separate thread as it interfaces to UI
    
    """

    startCameraRequest     = pyqtSignal()    # start camera image acquisition
    stopCameraRequest      = pyqtSignal()    # stop camera image acquisition
    scanCameraRequest      = pyqtSignal()    # scan for blackfly and opencv cameras
    calibrateCameraRequest = pyqtSignal()    # calibrate camera response
    
    changeCameraRequest    = pyqtSignal(int)  # change camera to one at index int
    changeExposureRequest  = pyqtSignal(int)  # change exposure time to microseconds
    changeFrameRateRequest = pyqtSignal(int)  # change frame rate to int
    changeBinningRequest   = pyqtSignal(list) # change binning vet hor
        
    setDisplayedChannelsRequest = pyqtSignal(np.ndarray, list)
        
    def __init__(self, parent=None, ui=None):
        # super().__init__()
        super(QCameraUI, self).__init__(parent)

        self.logger = logging.getLogger("CameraUI_") 
 
        if ui is None:
            self.logger.log(logging.ERROR, "[{}]: need to have access to User Interface".format(int(QThread.currentThreadId())))
        self.ui = ui

        # create graphics scene and place it in the graphicsView
        self.scene = QGraphicsScene(self)
        self.ui.graphicsView.setScene(self.scene)

        # create pixmap item and add it to the scene
        self.pixmap = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap)
        
        # add other items to the graphcis scence
        # e.g. text, shape etc...

        from configs import blackfly_configs as bf_configs
        from configs import opencv_configs
        # Search for camera signatures as cv_configs
        
        self.logger.log(logging.INFO, "[{}]: initialized.".format(int(QThread.currentThreadId())))
   

    def _measuredChannels(self):
        """ 
        Scan for selected channels, 
        figure out how many and which ones are selected 
        """        
        MeasuredChannels  = np.zeros(NUM_CHANNELS, dtype=np.bool_)
        MeasuredChannels[0] = 1 # always measure background
        for channel in range(NUM_CHANNELS-1):
            checkBox = self.ui.findChild( QCheckBox, "checkBox_MeasureChannel"+str(channel+1))
            if checkBox.isChecked:
                MeasuredChannels[channel+1] = True
            else:
                MeasuredChannels[channel+1] = False
        return MeasuredChannels

    def _displayedChannels(self):
        """
        Scan for selected channels, 
        figure out how many and which ones are selected 
        """        
        DisplayedChannels  = np.zeros(NUM_CHANNELS, dtype=np.bool_)
        
        for channel in range(NUM_CHANNELS-1):
            checkBox = self.ui.findChild( QCheckBox, "checkBox_MeasureChannel"+str(channel+1))
            if checkBox.isChecked:
                DisplayedChannels[channel+1] = True
            else:
                DisplayedChannels[channel+1] = False
        return DisplayedChannels

    ########################################################################################
    # Function slots
          
    @pyqtSlot(float)
    def on_FPSInReady(self, fps):
        """
        this will update frames per second display
        """
        self.ui.lcdNumber_FPSIN.display("{:5.1f}".format(fps)) 

    @pyqtSlot(float)
    def on_FPSOutReady(self, fps):
        """
        this will update frames per second display
        """
        self.ui.lcdNumber_FPSOUT.display("{:5.1f}".format(fps)) 

    @pyqtSlot(np.ndarray)
    def on_ImageDataReady(self, image):
        """
        this will display image in image window
        """

        (depth, height, width) = image.shape
        if depth > 1:  
            _img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) # swap B and R color channels
            _imgQ = QImage(_img.data, width, height, QImage.Format_RGB888) # convert to QImage
        else: 
            _img = image
            _imgQ = QImage(_img.data, width, height, QImage.Format_Grayscale8) # convert to QImage
        _pixmap = QPixmap.fromImage(_imgQ)
        self.pixmap.SetPixmap(_pixmap)        

    @pyqtSlot(list)
    def on_newCameraListReady(self, cameraDesc):
        """ 
        New camera list available
        """        
        self.logger.log(logging.DEBUG, "[{}]: camera list received.".format(int(QThread.currentThreadId())))
        self.cameraNames  = []
        self.cameraNumbers = []
        for i in range(len(cameraDesc)):
            self.cameraNumbers.append(cameraDesc[i]["number"])
            self.cameraNames.append(cameraDesc[i]["name"])
        # populate bull down menu with all camera options
        # block the box from emitting changed index signal when items are added
        self.ui.comboBoxDropDown_Cameras.blockSignals(True)
        selected = self.ui.comboBoxDropDown_Cameras.currentText() # what is currently selected in the box?
        self.ui.comboBoxDropDown_Cameras.clear()
        # populate new items
        self.ui.comboBoxDropDown_Cameras.addItems(self.cameraNames)
        # search for the previously selected item
        index = self.ui.comboBoxDropDown_Cameras.findText(selected)
        if index > -1: # if we found previously selected item
            self.ui.comboBoxDropDown_Cameras.setCurrentIndex(index)
        else:  # if we did not find previous item set box to last item (None)
            self.ui.comboBoxDropDown_Cameras.setCurrentIndex(0)
        # enable signals again
        self.ui.comboBoxDropDown_Cameras.blockSignals(False)

    # Handing off signals to Camera

    @pyqtSlot()
    def on_Start(self):
        
        # Channel selection:        
        # Example
        # 01234567 8 possible channels
        # 01110110 measured channels
        # 00110010 displayed channels
        # 00110010 both channels
        # x012x34x index in the measured channels
      
        # channels selected for measurement
        mChannels = self._measuredChannels()
        # channels selected for display
        dChannels = self._displayedChannels()
        # both measured and displayed channels
        bChannels = mChannels & dChannels
        # which images from the measured channels need to be displayed?
        indexCube  = np.array([])
        indexNames = np.array([])
        j=0
        for i in range(NUM_CHANNELS):
            if bChannels[i]:
              # indexCube.append(j)
               indexCube = np.append(indexCube, j)
               indexNames = np.append(indexNames, i)
               #indexNames.append(i)
            if mChannels[i]:
               j += 1
        # the names of the channels are:
        channelNames = []
        for i in range(len(indexNames)):
            checkBoxDisplay  = self.ui.findChild(QCheckBox, "checkBox_DisplayChannel"+str(i))            
            channelNames.append(checkBoxDisplay.text())

        # announce channels display
        self.setDisplayedChannelsRequest.emit(indexCube, channelNames)

        # what processing
        # do we want bg-subtraction, flat field correction, 
        # binning, temporal filtering, save to file or 
        # save to ram
        
        # what to analyze
        # do we want Analysis, Color, Physio, Spectrum?
        
        # emit signal to camera handler to start acquisition       
        self.startCameraRequest.emit()

    @pyqtSlot()
    def on_Stop(self):
        self.stopCameraRequest.emit()       

    @pyqtSlot()
    def on_ScanCamera(self):
        self.scanCameraRequest.emit()

    @pyqtSlot()
    def on_Calibrate(self):
        self.calibrateCameraRequest.emit()

    @pyqtSlot(int)
    def on_ChangeCamera(self, indx):
        self.changeCameraRequest.emit(indx)
        
    @pyqtSlot(int)
    def on_ExposureTimeChanged(self, exposure):
        self.changeExposureRequest.emit(exposure)

    @pyqtSlot(int)
    def on_FrameRateChanged(self, fps):
        self.changeFrameRateRequest.emit(fps)


    @pyqtSlot(list)
    def on_ChangeBinning(self, bin ):
        self.changeBinningRequest.emit(bin) 
         
class QCamera(QObject):
    """
    Camera Interface for QT
    Goes to separate thread
    
    Signals
        imageDataReady
        cameraStatusReady
        cameraFinished
        newCameraListReady
        fpsReady
        
    Worker functions
        on_startCamera
        on_stopCamera
        on_scanCameras
        on_closeCamera
        
        on_changeCamera
        on_changeExposure
        on_changeFrameRate
        on_changeBinning    
    
    """

    # Signals
    ########################################################################################
    imageDataReady     = pyqtSignal(list) 
    cameraStatusReady  = pyqtSignal(list)                                               # camera status is available
    cameraFinished     = pyqtSignal() 
    newCameraListReady = pyqtSignal(list)                                               # new camera list is available
    fpsReady           = pyqtSignal(float)                                              # fps is available

    def __init__(self, parent=None):
        # super().__init__()
        super(QCamera, self).__init__(parent)

        self.logger = logging.getLogger("CameraUI_") 
            
        camCV2      = self._probeOpenCVCameras()
        camBlackFly = self._probeBlackFlyCameras()
        self.cameraDesc = [{"name": "None", "number": -1, "fourcc": "NULL", "width": 0, "height": 0}] + camBlackFly + camCV2 
        self.newCameraListReady.emit(self.cameraDesc)
        
        self.logger.log(logging.DEBUG, "QCamera initialized")
               
    # Functions internal
    ########################################################################################

    def _probeBlackFlyCameras(self):
        '''
        Scans cameras and returns fourcc, width and height
        '''
        arr=[]
        _system = PySpin.System.GetInstance() # open library
        _cam_list = _system.GetCameras()
        _camListSize=_cam_list.GetSize()
        for camera_num in range(_cam_list.GetSize()):
            _cam = _cam_list.GetByIndex(camera_num)            
            _camWidth=720 # int(_cam.Width.GetValue())
            _camHeight=540 # int(_cam.Height.GetValue())            
            arr.extend([{"name": _cam.TLDevice.DeviceModelName.GetValue(), "number": camera_num, "fourcc": "FLIR", "width": _camWidth, "height":_camHeight}])
            del _cam
        _cam_list.Clear() # clear camera list before releasing system        
        _system.ReleaseInstance()        
        return arr
        
    def _probeOpenCVCameras(numcams: int = 10):
        '''
        Scans cameras and returns default fourcc, width and height
        '''
        index = 0        
        arr = []      
        camera_num=0
        #i = range(numcams)
        i=1
        while i > 0:
            cap = cv2.VideoCapture(index)
            if cap.read()[0]:
                tmp = cap.get(cv2.CAP_PROP_FOURCC)
                fourcc = "".join([chr((int(tmp) >> 8 * i) & 0xFF) for i in range(4)])
                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                cap.release()
                arr.extend([{"name": "CV - " + str(camera_num), "number": camera_num, "fourcc": fourcc, "width": width, "height": height}])
            else:               
                cap.release()
                break
            camera_num += 1
            i -= 1
        return arr
               
    # @pyqtSlot()    
    def on_startCamera(self):        
       #TODO need to know datacube depth which is the number of selected measurement channels
        depth=10 # TODO This just random number
        self.camera.startAcquisition(depth=depth, flatfield=None)
        # self.camera.datacube.dataCubeReady.connect() # needs to go to processing
        # self.camera.datacube.dataCubeReady.connect() # needs to go to display
        self.logger.log(logging.DEBUG, "QCamera started")
        self.camera.update() # will run forever unless stop issued
        # This does not stop until camera is stopped

    @pyqtSlot()
    def on_stopCamera(self):
        self.camera.stopAcquisition()
        self.logger.log(logging.DEBUG, "QCamera stopped")

    @pyqtSlot()
    def on_scanCameras(self):
        # stop camera and acquisition
        try: 
            if self.camera.cam_open:
                self.camera.stopAcquisition()
                self.camera.closeCamera()
        except: pass        
        camCV2      = self._probeOpenCVCameras()
        self.logger.log(logging.DEBUG, "QCamera scanned for openCV cameras")
        camBlackFly = self._probeBlackFlyCameras()
        self.logger.log(logging.DEBUG, "QCamera scanned fro BlackFly cameras")
        
        self.cameraDesc = [{"name": "None", "number": -1, "fourcc": "NULL", "width": 0, "height": 0}] + camBlackFly + camCV2 
       
        if not camBlackFly:
            self.cameraDesc.extend(camBlackFly)
        if not camCV2:
            self.cameraDesc.extend(camCV2)
        self.newCameraListReady.emit(self.cameraDesc)
        
             
    #@pyqtSlot(int)
    def on_changeCamera(self, indx):
        # stop camera and acquisition
        try: 
            if self.camera.cam_open:
                self.camera.stopAcquisition()
                self.camera.closeCamera()
        except: pass
        
        _cameraDescription = self.cameraDesc[indx]
        self.cam_num = _cameraDescription['number']        
        
        if "CV" in _cameraDescription['name']:
            self.cameratype = cameraType.opencv
            from configs.opencv_configs import configs as configs
            self.configs    = configs
            self.camera = OpenCVCapture(camera_num=0,configs=self.configs)
            self.logger.log(logging.DEBUG, "QCamera opened OpenCV camera")
            
        elif "Blackfly" in _cameraDescription['name']:
            self.cameratype = cameraType.blackfly
            from configs.blackfly_configs import configs as configs
            self.configs    = configs
            self.camera = BlackflyCapture(self.configs)
            self.logger.log(logging.DEBUG, "QCamera opened BlackFly camera")

        else:
            self.logger.log(logging.ERROR, "QCamera camera type not recognized")

        #self.camera.fpsReady.connect(self.fpsReady.emit)

    @pyqtSlot(int)
    def on_changeExposure(self, exposure):
        self.camera.exposure(exposure)

    @pyqtSlot(int)
    def on_changeFrameRate(self, fps):
        self.camera.fps(fps)
    
    # because data cube is allocated in cameraWorker
    @pyqtSlot(list)
    def on_changeBinning(self, binning):
        pass