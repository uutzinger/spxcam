###########################################################################################
# Blackfly Camera Class
###########################################################################################

# Open FLIR driver
import PySpin
from   PySpin.PySpin import TriggerMode_Off, TriggerSource_Software
# QT
from   PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, QSignalMapper
from   PyQt5.QtWidgets import QLineEdit, QSlider, QCheckBox, QLabel
#QT System
import logging, time
# Numerical Tools
import numpy as np

class BlackflyCapture(QObject):
    imageDataReady    = pyqtSignal(float, np.ndarray)                                     # image received on serial port
    fpsReady          = pyqtSignal(float)
    
    def __init__(self, configs, parent=None, camera_num=0):
        super(BlackflyCapture, self).__init__(parent)

        self.logger = logging.getLogger("QBlackF")           

        self._camera_num     = camera_num
        self._exposure       = configs['exposure']
        self._camera_res     = configs['camera_res']
        self._output_res     = configs['output_res']
        self._output_width   = self._output_res[0]
        self._output_height  = self._output_res[1]
        self._framerate      = configs['fps']
        self._autoexposure   = configs['autoexposure']       # autoexposure depends on camera
        self._binning        = configs['binning']
        self._framerate      = configs['fps']
        self._offset         = configs['offset']
        self._adc            = configs['adc']
        self._trigout        = configs['trigout']            # -1 no trigout, 1 = line 1 ..
        self._ttlinv         = configs['ttlinv']             # False = normal, True=inverted
        self._trigin         = configs['trigin']             # -1 no trigin,  1 = line 1 ..

        # Init vars
        self.frame_time   = 0.0
        self.measured_fps = 0.0
        self.stopped = True
        
    def update(self):
        """
        Continously read Capture
        """
        last_time = last_emit = time.perf_counter()
        
        while not self.stopped:
            current_time = time.perf_counter()

            # Get New Image
            if self.cam is not None:
                image_result = self.cam.GetNextImage(1000) # timeout in ms, function blocks until timeout
                if not image_result.IsIncomplete(): # should always be complete
                    # self.frame_time = self.cam.EventExposureEndTimestamp.GetValue()
                    img = image_result.GetNDArray() # get inmage as NumPy array
                    try: image_result.Release() # make next frame available, can create error during debug
                    except: self.logger.log(logging.WARNING, "[CAM]: Can not release image!")
                    self.datacube.add(img)

            # FPS calculation
            self.measured_fps = (0.9 * self.measured_fps) + (0.1/(current_time - last_time)) # low pass filter
            if current_time - last_emit > 0.5:
                self.fpsReady.emit(self.measured_fps)
                last_emit =  current_time
                self.logger.log(logging.DEBUG, "[CAM]: FPS: {}.".format(self.measured_fps))
            last_time = current_time

    def openCamera(self):
        """
        Open up the camera so we can begin capturing frames
        """

        # Open Library and Camera
        #########################
        self.system = PySpin.System.GetInstance() # open library
        self.version = self.system.GetLibraryVersion() # Get current library version
        self.logger.log(logging.INFO, "[PySpin]: Driver:Version: {}.{}.{}.{}.".format(self.version.major,  self.version.minor, self.version.type, self.version.build))
        # Retrieve list of cameras from the system
        self.cam_list = self.system.GetCameras()
        self.num_cameras = self.cam_list.GetSize()
        self.logger.log(logging.INFO, "[PySpin]: Number of Cameras: {}.".format(self.num_cameras))
        if self.num_cameras == 0:
            # Finish if there are no cameras
            self.cam_list.Clear() # Clear camera list before releasing system
            self.system.ReleaseInstance() # Release system instance
            self.logger.log(logging.CRITICAL, "[PySpin]: No Cameras Found!")
            self.cam_open = False
            self.cam = None
            return False
        # Open the camera
        self.cam = self.cam_list[self._camera_num]
        # Get device information
        self.nodemap_tldevice = self.cam.GetTLDeviceNodeMap()
        self.node_device_information = PySpin.CCategoryPtr(self.nodemap_tldevice.GetNode('DeviceInformation'))
        if PySpin.IsAvailable(self.node_device_information) and PySpin.IsReadable(self.node_device_information):
            features = self.node_device_information.GetFeatures()
            for feature in features:
                node_feature = PySpin.CValuePtr(feature)
                if PySpin.IsReadable(node_feature): 
                    self.logger.log(logging.INFO, "[PySpin]: Camera Features: {} {}.".format(node_feature.GetName(), node_feature.ToString()))
                else: 
                    self.logger.log(logging.WARNING, "[PySpin]: Camera Features: {}.".format('Node not readable'))
                    return False
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera Features: {}.".format('Device control information not available.'))
            return False
        
        # Initialize camera
        # -----------------
        self.cam.Init()
        self.cam_open = True

        # Camera Settings
        # ---------------

        # 1 Set Sensor
        #   - Binning, should be set before setting width and height
        #   - Width and Height
        #   - Offset (hor,vert), should be set after setting binning and resolution
        #   - Bit Depth (8, 10, 12 or 14bit), will also set Pixel Format to either Mono8 or Mono16, affects frame rte

        # Binning Mode Vertical & Horizontal
        # Binning only on chip
        self.cam.BinningSelector.SetValue(PySpin.BinningSelector_Sensor)
        if self.cam.BinningVerticalMode.GetAccessMode() == PySpin.RW:
            self.cam.BinningVerticalMode.SetValue(PySpin.BinningVerticalMode_Sum)
            self.logger.log(logging.INFO, "[PySpin]: Camera:BinningVerticalMode: {}.".format(self.cam.BinningVerticalMode.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:BinningVerticalMode: no access")
        if self.cam.BinningHorizontalMode.GetAccessMode() == PySpin.RW:
            self.cam.BinningHorizontalMode.SetValue(PySpin.BinningHorizontalMode_Sum)
            self.logger.log(logging.INFO, "[PySpin]: Camera:BinningHorizonalMode: {}.".format(self.cam.BinningHorizontalMode.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:BinningHorizonalMode: no access")

        # features changeable by user
        self.adc         = self._adc
        self.binning     = self._binning
        self.offset      = self._offset
        self.resolution  = self._camera_res

        # 2 Turn off features
        #   - ISP (off)
        #   - Automatic Gain (off)
        #   - Gamma (set to 1.0 then off)
        #   - Automatic Exposure (off preferred for high frame rate)
        #   - Acquisition Mode = Continous
        #   - Acquisiton Frame Rate Enable = True
        #   - Exposure Mode Timed
        #   - Gamme Enable Off
        
        # ISP OFF
        if self.cam.IspEnable.GetAccessMode() == PySpin.RW:
            self.cam.IspEnable.SetValue(False)
            self.logger.log(logging.INFO, "[PySpin]: Camera:ISP Enable: {}.".format(self.cam.IspEnable.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:ISP Enable: no access.")
        # Gain OFF
        if self.cam.GainSelector.GetAccessMode() == PySpin.RW: 
            self.cam.GainSelector.SetValue(PySpin.GainSelector_All)
            self.logger.log(logging.INFO, "[PySpin]: Camera:GainSelector: {}.".format(self.cam.GainSelector.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:GainSelector: no acces.")
        if self.cam.Gain.GetAccessMode() == PySpin.RW:
            self.cam.Gain.SetValue(1.0)
            self.logger.log(logging.INFO, "[PySpin]: Camera:Gain: {}.".format(self.cam.Gain.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:Gain: no access.")
        if self.cam.GainAuto.GetAccessMode() == PySpin.RW:
            self.cam.GainAuto.SetValue(PySpin.GainAuto_Off)
            self.logger.log(logging.INFO, "[PySpin]: Camera:GainAuto: {}.".format(self.cam.GainAuto.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:GainAuto: no access.")
        # Acquisition Mode = Continous
        if self.cam.AcquisitionMode.GetAccessMode() == PySpin.RW:
            self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
            self.logger.log(logging.INFO, "[PySpin]: Camera:AcquistionMode: {}.".format(self.cam.AcquisitionMode.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:AcquisionMode: no access.")
        # Exposure Mode Timed
        if self.cam.ExposureMode.GetAccessMode() == PySpin.RW:
            self.cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)        
            self.logger.log(logging.INFO, "[PySpin]: Camera:ExposureMode: {}.".format(self.cam.ExposureMode.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:ExposureMode: no access.")
        # Acquisiton Frame Rate Enable = True
        if self.cam.AcquisitionFrameRateEnable.GetAccessMode() == PySpin.RW:
            self.cam.AcquisitionFrameRateEnable.SetValue(True)
            self.logger.log(logging.INFO, "[PySpin]: Camera:AcquisionFrameRateEnable: {}.".format(self.cam.AcquisitionFrameRateEnable.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:AcquisionFrameRateEnable: no access.")
        # Gamma Off
        if self.cam.GammaEnable.GetAccessMode() == PySpin.RW:
            self.cam.GammaEnable.SetValue(True)
        if self.cam.Gamma.GetAccessMode() == PySpin.RW:
            self.cam.Gamma.SetValue(1.0)
            self.logger.log(logging.INFO, "[PySpin]: Camera:Gamma: {}.".format(self.cam.Gamma.GetValue()))
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:Gamma: no access.")
        if self.cam.GammaEnable.GetAccessMode() == PySpin.RW:
            self.cam.GammaEnable.SetValue(False)
            self.logger.log(logging.INFO, "[PySpin]: Camera:GammaEnable: {}.".format(self.cam.GammaEnable.GetValue()))    
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:GammaEnable: no access.")

        # features changable by client
        self.autoexposure = self._autoexposure 

        # 3 Digital Output and Digitial Input
        #   - Set Input Trigger, if set to -1 use software trigger
        self.trigin  = self._trigin
        #   Set Output Trigger, Line 1 has opto isolator but transitions slow, line 2 takes about 4-10 us to transition
        self.trigout = self._trigout 

        # 4 Aquistion
        #   - Continous 
        #   - FPS, should be set after turning off auto feature, ADC bit depth, binning as they slow down camera
        self.exposure = self._exposure
        self.fps = self._framerate
            
        self.logger.log(logging.INFO, "[PySpin]: camera opened.")

        return True

    def closeCamera(self):
        try: 
            self.cam.EndAcquisition()
            self.cam.DeInit()
            # self.cam.Release()
            del self.cam
            self.cam_list.Clear()          # clear camera list before releasing system
            self.system.ReleaseInstance()  # release system instance
        except: pass

    def startAquistion(self):
        self.cam.BeginAcquisition() # Start Aquision
        # if trigger source is Software: execute, otherwise nothing goes
        self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Software)
        if self.cam.TriggerSource.GetValue() == PySpin.TriggerSource_Software:
            self.cam.TriggerSoftware()
            self.logger.log(logging.INFO, "[PySpin]: Camera:TriggerSource: executed.")
        else:
            self.logger.log(logging.WARNING, "[PySpin]: Camera:TriggerSource: no access.")
        self.stopped = False

        self.logger.log(logging.INFO, "[PySpin]: Acquiring images.")
    
    def stopAquistion(self):
        self.stopped = True
        self.cam.EndAcquisition()

        self.logger.log(logging.INFO, "[PySpin]: Stopped acquiring images.")

    # Setting and Reading internal camera settings
    ########################################################################################

    @property
    def width(self):
        """returns video capture width """
        if self.cam_open:
            return self.cam.Width.GetValue()
        else: return -1
    @width.setter
    def width(self, val):
        """sets video capture width """
        if (val is None) or (val == -1):
            self.logger.log(logging.WARNING, "[PySpin]: Camera:Width not changed:{}.".format(val))
            return
        if self.cam_open:
            val = max(self.cam.Width.GetMin(), min(self.cam.Width.GetMax(), val))
            if self.cam.Width.GetAccessMode() == PySpin.RW:
                self.cam.Width.SetValue(val)
                self._camera_res = (int(self.cam.Width.GetValue()), int(self._camera_res[1]))
                self.logger.log(logging.INFO, "[PySpin]: Camera:Width:{}.".format(val))
            else:
                self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set width to {}!".format(val))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set resolution, camera not open!")

    @property
    def height(self):
        """returns video capture height """
        if self.cam_open:
            return self.cam.Height.GetValue()
        else: return -1
    @height.setter
    def height(self, val):
        """sets video capture width """
        if (val is None) or (val == -1):
            self.logger.log(logging.WARNING, "[PySpin]: Camera:Height not changed:{}.".format(val))
            return
        if self.cam_open:
            val = max(self.cam.Height.GetMin(), min(self.cam.Height.GetMax(), val)) 
            if self.cam.Height.GetAccessMode() == PySpin.RW:
                self.cam.Height.SetValue(val)
                self._camera_res = (int(self._camera_res[0]), int(self.cam.Height.GetValue()))
                self.logger.log(logging.INFO, "[PySpin]: Camera:Height:{}.".format(val))
            else:
                self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set height to {}!".format(val))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set resolution, camera not open!")

    @property
    def resolution(self):
        """returns current resolution width x height """
        if self.cam_open:
            return (int(self.cam.Width.GetValue()), int(self.cam.Height.GetValue()))
        else: 
            return (-1, -1)
    @resolution.setter
    def resolution(self, val):
        """sets video capture resolution """
        if val is None: return
        if self.cam_open:
            if len(val) > 1: # we have width x height
                _tmp0 = max(self.cam.Width.GetMin(),  min(self.cam.Width.GetMax(),  val[0]))
                _tmp1 = max(self.cam.Height.GetMin(), min(self.cam.Height.GetMax(), val[1]))
                val = (_tmp0, _tmp1)
                if self.cam.Width.GetAccessMode() == PySpin.RW:
                    self.cam.Width.SetValue(int(val[0]))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:Width:{}.".format(val[0]))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set width to {}!".format(val[0]))
                    return
                if self.cam.Height.GetAccessMode() == PySpin.RW:
                    self.cam.Height.SetValue(int(val[1]))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:Height:{}.".format(val[1]))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set height to {}!".format(val[1]))
                    return
            else: # given only one value for resolution, make image square
                val = max(self.cam.Width.GetMin(), min(self.cam.Width.GetMax(), val))
                val = max(self.cam.Height.GetMin(), min(self.cam.Height.GetMax(), val))
                if self.cam.Width.GetAccessMode() == PySpin.RW:
                    self.cam.Width.SetValue(int(val))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:Width:{}.".format(val))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set resolution to {},{}!".format(val,val))
                    return
                if self.cam.Height.GetAccessMode() == PySpin.RW:
                    self.cam.Height.SetValue(int(val)) 
                    self.logger.log(logging.INFO, "[PySpin]: Height:{}.".format(val))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set resolution to {},{}!".format(val,val))
                    return
            self._camera_res = (int(self.cam.Width.GetValue()), int(self.cam.Height.GetValue()))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set resolution, camera not open!")

    @property
    def offset(self):
        """returns current sesor offset """
        if self.cam_open:
            return (self.cam.OffsetX.GetValue(), self.cam.OffsetY.GetValue())
        else: 
            return (float("NaN"), float("NaN")) 
    @offset.setter
    def offset(self, val):
        """sets sensor offset """
        if val is None: return
        if self.cam_open:
            if len(val) > 1: # have horizontal and vertical
                _tmp0 = max(min(self.cam.OffsetX.GetMin(), val[0]), self.cam.OffsetX.GetMax())
                _tmp1 = max(min(self.cam.OffsetY.GetMin(), val[1]), self.cam.OffsetY.GetMax())
                val = (_tmp0, _tmp1)
                if self.cam.OffsetX.GetAccessMode() == PySpin.RW:
                    self.cam.OffsetX.SetValue(int(val[0]))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:OffsetX:{}.".format(val[0]))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set X offset to {}!".format(val[0]))
                    return
                if self.cam.OffsetY.GetAccessMode() == PySpin.RW:
                    self.cam.OffsetY.SetValue(int(val[1]))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:OffsetY:{}.".format(val[1]))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Y offset to {}!".format(val[1]))
                    return
            else: # given only one value for offset
                val = max(min(self.cam.OffsetX.GetMin(), val), self.cam.OffsetX.GetMax())
                val = max(min(self.cam.OffsetY.GetMin(), val), self.cam.OffsetY.GetMax())
                if self.cam.OffsetX.GetAccessMode() == PySpin.RW:
                    self.cam.OffsetX.SetValue(int(val))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:OffsetX:{}.".format(val))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set X offset to {}!".format(val))
                    return
                if self.cam.OffsetY.GetAccessMode() == PySpin.RW:
                    self.cam.OffsetY.SetValue(int(val))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:OffsetY:{}.".format(val))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Y offset to {},{}!".format(val))
                    return
            self._offset = (self.cam.OffsetX.GetValue(), self.cam.OffsetY.GetValue())
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set offset, camera not open!")

    @property
    def binning(self):
        """returns binning horizontal, vertical """
        if self.cam_open:
            return (self.cam.BinningHorizontal.GetValue(), self.cam.BinningVertical.GetValue())
        else: 
            return (-1, -1)
    @binning.setter
    def binning(self, val):
        """sets sensor biginning """
        if val is None: return
        if self.cam_open:
            if len(val) > 1: # have horizontal x vertical
                _tmp0 = min(max(val[0], self.cam.BinningHorizontal.GetMin()), self.cam.BinningHorizontal.GetMax()) 
                _tmp1 = min(max(val[1], self.cam.BinningVertical.GetMin()), self.cam.BinningVertical.GetMax())
                val = (_tmp0, _tmp1)
                if self.cam.BinningHorizontal.GetAccessMode() == PySpin.RW:
                    self.cam.BinningHorizontal.SetValue(int(val[0]))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:BinningHorizontal:{}.".format(val[0]))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set horizontal binning to {}!".format(val[0]))
                    return
                if self.cam.BinningVertical.GetAccessMode() == PySpin.RW:
                    self.cam.BinningVertical.SetValue(int(val[1]))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:BinningVertical:{}.".format(val[1]))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set vertical binning to {}!".format(val[1]))
                    return
            else: # given only one value for binning
                _tmp0 = min(max(val[0], self.cam.BinningHorizontal.GetMin()), self.cam.BinningHorizontal.GetMax()) 
                _tmp1 = min(max(val[1], self.cam.BinningVertical.GetMin()), self.cam.BinningVertical.GetMax()) 
                val = (_tmp0, _tmp1)
                if self.cam.BinningHorizontal.GetAccessMode() == PySpin.RW:
                    self.cam.BinningHorizontal.SetValue(int(val))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:BinningHorizontal:{}.".format(val))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set horizontal binning to {}!".format(val))
                    return
                if self.cam.BinningVertical.GetAccessMode() == PySpin.RW:
                    self.cam.BinningVertical.SetValue(int(val))
                    self.logger.log(logging.INFO, "[PySpin]: Camera:BinningVertical:{}.".format(val))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set vertical binning to {}!".format(val))
                    return
            self._binning = (self.cam.BinningHorizontal.GetValue(), self.cam.BinningVertical.GetValue())
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set binning, camera not open!")

    @property
    def exposure(self):
        """returns curent exposure """
        if self.cam_open:
            return self.cam.ExposureTime.GetValue()
        else: 
            return float("NaN")
    @exposure.setter
    def exposure(self, val):
        """sets exposure """
        if (val is None) or (val == -1):
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set exposure to {}!".format(val))
            return
        # Setting exposure implies that autoexposure is off and exposure mode is timed 
        if self.cam.ExposureMode.GetValue() != PySpin.ExposureMode_Timed:
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set exposure! Exposure Mode needs to be Timed.")
            return
        if self.cam.ExposureAuto.GetValue() != PySpin.ExposureAuto_Off:
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set exposure! Exposure is Auto.")
            return
        # Setting exposure
        if self.cam_open:
            if self.cam.ExposureTime.GetAccessMode() == PySpin.RW:
                self.cam.ExposureTime.SetValue(max(self.cam.ExposureTime.GetMin(), min(self.cam.ExposureTime.GetMax(), float(val))))
                self._exposure = self.cam.ExposureTime.GetValue()
                self.logger.log(logging.INFO, "[PySpin]: Camera:Exposure:{}.".format(self._exposure))
            else:
                self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set expsosure to:{}.".format(self._exposure))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set exposure, camera not open!")

    @property
    def autoexposure(self):
        """returns curent auto exposure state """
        if self.cam_open:
            if (self.cam.ExposureAuto.GetValue() == PySpin.ExposureAuto_Continuous) or (self.cam.ExposureAuto.GetValue() == PySpin.ExposureAuto_Once):
                return 1
            else:
                return 0
        else: return -1
    @autoexposure.setter
    def autoexposure(self, val):
        """sets autoexposure """
        # On:
        # 1) Turn on autoexposure
        # 2) Update FPS as autoexposure reduces framerate
        # Off:
        # 1) Turn off autoexposre
        # 2) Set exposure 
        # 3) Set max FPS
        if (val is None) or (val == -1):
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set Autoexposure to:{}.".format(val))
            return
        if self.cam_open:
            if val > 0: 
                # Setting Autoexposure on
                if self.cam.ExposureAuto.GetAccessMode() == PySpin.RW:
                    self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
                    self.logger.log(logging.INFO, "[PySpin]: Camera:Autoexposure:{}.".format(1))
                    self._autoexposure = 1
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Autoexposure to:{}.".format(val))
                    return
                if self.cam.AcquisitionFrameRate.GetAccessMode() == PySpin.RW:
                    self.cam.AcquisitionFrameRate.SetValue(min(self.cam.AcquisitionFrameRate.GetMax(),self._framerate))
                    self._framerate = self.cam.AcquisitionFrameRate.GetValue()
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Frame Rate to:{}.".format(self._framerate))
            else:
                # Setting Autoexposure off
                if self.cam.ExposureAuto.GetAccessMode() == PySpin.RW:
                    self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
                    self.logger.log(logging.INFO, "[PySpin]: Camera:Autoexposure: {}.".format(0))
                    self._autoexposure = 0
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Autoexposure to: {}.".format(val))
                    return
                if self.cam.ExposureTime.GetAccessMode() == PySpin.RW:
                    self.cam.ExposureTime.SetValue(max(self.cam.ExposureTime.GetMin(), min(self.cam.ExposureTime.GetMax(), self._exposure)))
                    self._exposure = self.cam.ExposureTime.GetValue()
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to adjust Exposure Time.")
                    return
                if self.cam.AcquisitionFrameRate.GetAccessMode() == PySpin.RW:
                    self.cam.AcquisitionFrameRate.SetValue(min(self.cam.AcquisitionFrameRate.GetMax(), self._framerate))
                    self._framerate = self.cam.AcquisitionFrameRate.GetValue()
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Frame Rate to:{}.".format(self._framerate))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set auto exposure, camera not open!")

    @property
    def fps(self):
        """returns current frames per second setting """
        if self.cam_open:
            return self.cam.AcquisitionFrameRate.GetValue() 
        else: return float("NaN")
    @fps.setter
    def fps(self, val):
        """set frames per second in camera """
        if (val is None) or (val == -1):
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set framerate to:{}.".format(val))
            return
        if self.cam_open:
            if self.cam.AcquisitionFrameRate.GetAccessMode() == PySpin.RW:
                self.cam.AcquisitionFrameRate.SetValue(min(self.cam.AcquisitionFrameRate.GetMax(), float(val)))
                self._framerate = self.cam.AcquisitionFrameRate.GetValue()
                self.logger.log(logging.INFO, "[PySpin]: Camera:FPS:{}.".format(self._framerate))
            else:
                self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set FPS to:{}.".format(self._framerate))

    @property
    def adc(self):
        """returns adc bitdetpth """
        if self.cam_open:
            _tmp = self.cam.AdcBitDepth.GetValue()
            if _tmp == PySpin.AdcBitDepth_Bit8:
                return 8
            elif _tmp == PySpin.AdcBitDepth_Bit10:
                return 10
            elif _tmp == PySpin.AdcBitDepth_Bit12:
                return 12
            elif _tmp == PySpin.AdcBitDepth_Bit14:
                return 14
            else:
                return -1
        else: return -1
    @adc.setter
    def adc(self, val):
        """sets adc bit depth """
        if (val is None) or (val == -1):
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set adc bit depth to {}!".format(val))
            return
        if self.cam_open:
            if val == 8:
                if self.cam.AdcBitDepth.GetAccessMode() == PySpin.RW:
                    self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit8) 
                    self._adc = 8
                    self.logger.log(logging.INFO, "[PySpin]: Camera:ADC:{}.".format(self._adc))
                    if self.cam.PixelFormat.GetAccessMode() == PySpin.RW:
                        self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)
                        self.logger.log(logging.INFO, "[PySpin]: Camera:PixelFormat:{}.".format('Mono8'))
                    else:
                        self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Pixel Format to:{}.".format('Mono8'))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set ADC to:{}.".format(val))
            elif val == 10:
                if self.cam.AdcBitDepth.GetAccessMode() == PySpin.RW:
                    self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit10) 
                    self._adc = 10
                    self.logger.log(logging.INFO, "[PySpin]: Camera:ADC:{}.".format(self._adc))
                    if self.cam.PixelFormat.GetAccessMode() == PySpin.RW:
                        self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono16)
                        self.logger.log(logging.INFO, "[PySpin]: Camera:PixelFormat:{}.".format('Mono16'))
                    else:
                        self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Pixel Format to:{}.".format('Mono16'))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set ADC to:{}.".format(val))
            elif val == 12:
                if self.cam.AdcBitDepth.GetAccessMode() == PySpin.RW:
                    self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit12) 
                    self._adc = 12
                    self.logger.log(logging.INFO, "[PySpin]: Camera:ADC:{}.".format(self._adc))
                    if self.cam.PixelFormat.GetAccessMode() == PySpin.RW:
                        self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono16)
                        self.logger.log(logging.INFO, "[PySpin]: Camera:PixelFormat:{}.".format('Mono16'))
                    else:
                        self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Pixel Format to:{}.".format('Mono16'))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set ADC to:{}.".format(val))
            elif val == 14:
                if self.cam.AdcBitDepth.GetAccessMode() == PySpin.RW:
                    self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit14) 
                    self._adc = 14
                    self.logger.log(logging.INFO, "[PySpin]: Camera:ADC:{}.".format(self._adc))
                    if self.cam.PixelFormat.GetAccessMode() == PySpin.RW:
                        self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono16)
                        self.logger.log(logging.INFO, "[PySpin]: Camera:PixelFormat:{}.".format('Mono16'))
                    else:
                        self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set Pixel Format to:{}.".format('Mono16'))
                else:
                    self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set ADC to:{}.".format(val))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set ADC, camera not open!")

    @property
    def pixelformat(self):
        """returns pixel format """
        if self.cam_open:
            _tmp = self.cam.PixelFormat.GetValue()
            if _tmp == PySpin.PixelFormat_Mono8:
                return 'Mono8'
            elif _tmp == PySpin.PixelFormat_Mono10:
                return 'Mono10'
            elif _tmp == PySpin.PixelFormat_Mono10p:
                return 'Mono10p'
            elif _tmp == PySpin.PixelFormat_Mono10Packed:
                return 'Mono10Packed'
            elif _tmp == PySpin.PixelFormat_Mono12:
                return 'Mono12'
            elif _tmp == PySpin.PixelFormat_Mono12p:
                return 'Mono12p'
            elif _tmp == PySpin.PixelFormat_Mono12Packed:
                return 'Mono12Packed'
            elif _tmp == PySpin.PixelFormat_Mono16:
                return 'Mono16'
            return 'None'
        else: return -1

    @property
    def ttlinv(self):
        """returns tigger output ttl polarity """
        if self.cam_open:
            return self.cam.LineInverter.GetValue()
        else: return -1
    @ttlinv.setter
    def ttlinv(self, val):
        """sets trigger logic polarity """
        if (val is None):
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set trigger level to:{}!".format(val))
            return
        if self.cam_open:
            if val == 0: # Want regular trigger output polarity
                self.cam.LineInverter.SetValue(False)
                self._ttlinv = False
            elif val == 1: # want inverted trigger output polarity
                self.cam.LineInverter.SetValue(True)
                self._ttlinv = True
            self.logger.log(logging.INFO, "[PySpin]: Camera:Trigger Output Logic Inverted:{}.".format(self._ttlinv))
        else: # camera not open
            self.logger.log(logging.INFO, "[PySpin]: Camera:Failed to set Trigger Output Polarity, camera not open!")

    @property
    def trigout(self):
        """returns tigger output setting """
        if self.cam_open:
            if self.cam.LineSelector.GetAccessMode() == PySpin.RW:
                self.cam.LineSelector.SetValue(PySpin.LineSelector_Line0)
                if self.cam.LineMode.GetValue == PySpin.LineMode_Output:    return 0
                self.cam.LineSelector.SetValue(PySpin.LineSelector_Line1)
                if self.cam.LineMode.GetValue == PySpin.LineMode_Output:    return 1
                self.cam.LineSelector.SetValue(PySpin.LineSelector_Line2)
                if self.cam.LineMode.GetValue == PySpin.LineMode_Output:    return 2
                self.cam.LineSelector.SetValue(PySpin.LineSelector_Line3)
                if self.cam.LineMode.GetValue == PySpin.LineMode_Output:    return 3
            return -1
        else: return -1
    @trigout.setter
    def trigout(self, val):
        """sets trigger output line """
        # Line Selector Line 0,1,2,3
        # Line Mode Out
        #   0 Input Only
        #   1 Output Only
        #   2 Input and Output
        #   3 Input Only
        # Line Inverer True or False
        # Line Source Exposure Active
        if (val is None):
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set trigger output on line:{}!".format(val))
            return
        if self.cam_open:
            if val == 1: # want trigger output on line 1, need pullup to 3V on line 1, set line 2 to 3V
                # set line 1 to Exposure Active
                if self.cam.LineSelector.GetAccessMode() == PySpin.RW:  
                    self.cam.LineSelector.SetValue(PySpin.LineSelector_Line1)
                    if self.cam.LineMode.GetAccessMode() == PySpin.RW:      self.cam.LineMode.SetValue(PySpin.LineMode_Output)
                    if self.cam.LineInverter.GetAccessMode() == PySpin.RW:  self.cam.LineInverter.SetValue(self._ttlinv)
                    if self.cam.LineSource.GetAccessMode() == PySpin.RW:    self.cam.LineSource.SetValue(PySpin.LineSource_ExposureActive)
                    self._trigout = 1
                else:
                    self._trigout = -1
                self.logger.log(logging.INFO, "[PySpin]: Camera:Trigger Output:{}.".format(self._trigout))
            elif val == 2: # best option
                # Line Selector Line 2
                # Line Mode Out
                # Line Inverer True or False
                # Line Source Exposure Active
                if self.cam.LineSelector.GetAccessMode() == PySpin.RW:  
                    self.cam.LineSelector.SetValue(PySpin.LineSelector_Line2)
                    if self.cam.LineMode.GetAccessMode() == PySpin.RW:      self.cam.LineMode.SetValue(PySpin.LineMode_Output)
                    if self.cam.LineInverter.GetAccessMode() == PySpin.RW:  self.cam.LineInverter.SetValue(self._ttlinv)
                    if self.cam.LineSource.GetAccessMode() == PySpin.RW:    self.cam.LineSource.SetValue(PySpin.LineSource_ExposureActive)
                    self._trigout = 2
                else:
                    self._trigout = -1
                self.logger.log(logging.INFO, "[PySpin]: Camera:Trigger Output:{}.".format(self._trigout))
            else:
                self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set trigger output on line {}!".format(val))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set trigger output, camera not open!")

    @property
    def trigin(self):
        """returns tigger input setting """
        if self.cam_open:
            if self.cam.TriggerSource.GetAccessMode() == PySpin.RW:
                if   self.cam.TriggerSource.GetValue()==PySpin.TriggerSource_Line0:    return 0
                elif self.cam.TriggerSource.GetValue()==PySpin.TriggerSource_Line1:    return 1
                elif self.cam.TriggerSource.GetValue()==PySpin.TriggerSource_Line2:    return 2
                elif self.cam.TriggerSource.GetValue()==PySpin.TriggerSource_Line3:    return 3
                elif self.cam.TriggerSource.GetValue()==PySpin.TriggerSource_Software: return -1
            else: 
                self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not read trigger source!")
                return -1
        else: 
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to read trigger output, camera not open!")
            return -1
        
    @trigin.setter
    def trigin(self, val):
        """sets trigger input line """
        if (val is None):
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set trigger input on line None!")
            return
        if self.cam_open:
            if val == -1: # no external trigger, trigger source is software
                if self.cam.TriggerSelector.GetAccessMode() == PySpin.RW:
                    self.cam.TriggerSelector.SetValue(PySpin.TriggerSelector_AcquisitionStart)
                if self.cam.TriggerMode.GetAccessMode() == PySpin.RW:
                    self.cam.TriggerMode.SetValue(PySpin.TriggerMode_On)
                if self.cam.TriggerSource.GetAccessMode() == PySpin.RW:
                    self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Software)
                if self.cam.TriggerOverlap.GetAccessMode() == PySpin.RW:
                    self.cam.TriggerOverlap.SetValue(PySpin.TriggerOverlap_ReadOut)
                if self.cam.TriggerDelay.GetAccessMode() == PySpin.RW:
                    self.cam.TriggerDelay.SetValue(self.cam.TriggerDelay.GetMin())
                self._trigout = -1
                self.logger.log(logging.INFO, "[PySpin]: Camera:Trigger Output:{}.".format(self._trigout))
            elif val == 0: # trigger is line 0
                if self.cam.TriggerSelector.GetAccessMode() == PySpin.RW:   self.cam.TriggerSelector.SetValue(PySpin.TriggerSelector_FrameStart)
                if self.cam.TriggerMode.GetAccessMode() == PySpin.RW:       self.cam.TriggerMode.SetValue(PySpin.TriggerMode_On)
                if self.cam.TriggerSource.GetAccessMode() == PySpin.RW:     self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line0)
                if self.cam.TriggerActivation.GetAccessMode() == PySpin.RW:
                    if self._ttlinv:                                        self.cam.TriggerActivation.SetValue(PySpin.TriggerActivation_FallingEdge)
                    else:                                                   self.cam.TriggerActivation.SetValue(PySpin.TriggerActivation_RisingEdge)
                if self.cam.TriggerOverlap.GetAccessMode() == PySpin.RW:    self.cam.TriggerOverlap.SetValue(PySpin.TriggerOverlap_Off)
                if self.cam.TriggerDelay.GetAccessMode() == PySpin.RW:      self.cam.TriggerDelay.SetValue(self.cam.TriggerDelay.GetMin())
                self._trigout = 0
                self.logger.log(logging.INFO, "[PySpin]: Camera:Trigger Output:{}.".format(self._trigout))
            elif val == 2: # trigger is line 2
                if self.cam.TriggerSelector.GetAccessMode() == PySpin.RW:   self.cam.TriggerSelector.SetValue(PySpin.TriggerSelector_FrameStart)
                if self.cam.TriggerMode.GetAccessMode() == PySpin.RW:       self.cam.TriggerMode.SetValue(PySpin.TriggerMode_On)
                if self.cam.TriggerSource.GetAccessMode() == PySpin.RW:     self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line2)
                if self.cam.TriggerActivation.GetAccessMode() == PySpin.RW:
                    if self._ttlinv:                                        self.cam.TriggerActivation.SetValue(PySpin.TriggerActivation_FallingEdge)
                    else:                                                   self.cam.TriggerActivation.SetValue(PySpin.TriggerActivation_RisingEdge)
                if self.cam.TriggerOverlap.GetAccessMode() == PySpin.RW:    self.cam.TriggerOverlap.SetValue(PySpin.TriggerOverlap_Off)
                if self.cam.TriggerDelay.GetAccessMode() == PySpin.RW:      self.cam.TriggerDelay.SetValue(self.cam.TriggerDelay.GetMin())
                self._trigout = 2
                self.logger.log(logging.INFO, "[PySpin]: Camera:Trigger Output:{}.".format(self._trigout))
            elif val == 3: # trigger is line 3
                if self.cam.TriggerSelector.GetAccessMode() == PySpin.RW:   self.cam.TriggerSelector.SetValue(PySpin.TriggerSelector_FrameStart)
                if self.cam.TriggerMode.GetAccessMode() == PySpin.RW:       self.cam.TriggerMode.SetValue(PySpin.TriggerMode_On)
                if self.cam.TriggerSource.GetAccessMode() == PySpin.RW:     self.cam.TriggerSource.SetValue(PySpin.TriggerSource_Line3)
                if self.cam.TriggerActivation.GetAccessMode() == PySpin.RW:
                    if self._ttlinv:                                        self.cam.TriggerActivation.SetValue(PySpin.TriggerActivation_FallingEdge)
                    else:                                                   self.cam.TriggerActivation.SetValue(PySpin.TriggerActivation_RisingEdge)
                if self.cam.TriggerOverlap.GetAccessMode() == PySpin.RW:    self.cam.TriggerOverlap.SetValue(PySpin.TriggerOverlap_Off)
                if self.cam.TriggerDelay.GetAccessMode() == PySpin.RW:      self.cam.TriggerDelay.SetValue(self.cam.TriggerDelay.GetMin())
                self._trigout = 3
                self.logger.log(logging.INFO, "[PySpin]: Camera:Trigger Output:{}.".format(self._trigout))
            else:
                self.logger.log(logging.ERROR, "[PySpin]: Camera:Can not set trigger output on line {}!".format(val))
        else: # camera not open
            self.logger.log(logging.ERROR, "[PySpin]: Camera:Failed to set trigger, camera not open!")
