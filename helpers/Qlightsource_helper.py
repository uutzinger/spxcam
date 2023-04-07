############################################################################################
# QT Light Source Helper Class
############################################################################################
# Interface to Blackfly LED camera sync program
# https://github.com/uutzinger/blackflysync
# ------------------------------------------------------------------------------------------
# Urs Utzinger
# University of Arizona 2022
# ------------------------------------------------------------------------------------------
# July 2022: initial work
############################################################################################

from PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, QSignalMapper
from PyQt5.QtWidgets import QLineEdit, QSlider, QCheckBox, QLabel

from parse import parse
import logging, time

NUM_LEDS = 13

class QLightSource(QObject):
    """
    Light SourceInterface for QT
    
    Enable/Disable LEDs
    Turn on//off LEDs manually
    LED intensity adjustment
    Read and store LED settings
    Push settings to User Interface
    """

    sendTextRequest              = pyqtSignal(str)                                         # request to transmit text to TX
    sendLinesRequest             = pyqtSignal(list)                                        # request to transmit lines of text to TX
    startReceiverRequest         = pyqtSignal()                                            # start serial receiver, expecting text
    connectLightSourceRequest    = pyqtSignal()                                            # receive serial input
    disconnectLightSourceRequest = pyqtSignal()                                            # stop receiving serial input
           
    def __init__(self, parent=None, ui=None):
        # super().__init__()
        super(QLightSource, self).__init__(parent)

        self.logger = logging.getLogger("LigthS_")           
                   
        if ui is None:
            self.logger.log(logging.ERROR, "[{}]: need to have access to User Interface".format(int(QThread.currentThreadId())))
        self.ui = ui
        
        ####################################################################################
        # setup user interface connections and limits
        
        self.logger.log(logging.INFO, "[{}]: initialized.".format(int(QThread.currentThreadId())))
                                   
    ########################################################################################
    # Functions internal

    def _setChannelIntensity(self, channel, intensity):
        lines = [ "s{}".format(channel-1),
                  "d{}".format(intensity),
                  "S{}".format(channel-1)
                ]
        self.sendLinesRequest.emit(lines)
        self.startReceiverRequest.emit()
        self.logger.log(logging.DEBUG, "[{}]: channel {} intensity {}".format(int(QThread.currentThreadId()),channel,intensity))

    def _manualTurnOnChannel(self,channel):
        lines = [ "a", 
                  "Z",
                  "s{}".format(channel-1),
                  "M"
                ]
        self.sendLinesRequest.emit(lines)
        self.startReceiverRequest.emit()
        self.logger.log(logging.DEBUG, "[{}]: turned on channel {}".format(int(QThread.currentThreadId()),channel))

    def _manualTurnOffChannel(self, channel):
        lines = [ "a", 
                  "s{}".format(channel-1),
                  "m"
                 ]
        self.sendLinesRequest.emit(lines)
        self.startReceiverRequest.emit()
        self.logger.log(logging.DEBUG, "[{}]: turned off channel {}".format(int(QThread.currentThreadId()),channel))

    ########################################################################################
    # Function slots

    @pyqtSlot()
    def setAutoAdvanceOn(self):
        self.sendTextRequest.emit("A")                                                     # turn on auto advance
        self.startReceiverRequest.emit()                                                   # get response
        self.logger.log(logging.DEBUG, "[{}]: autoadvance enabled".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def setAutoAdvanceOff(self):
        self.sendTextRequest.emit("a")                                                     # turn off auto advance
        self.startReceiverRequest.emit()                                                   # get response
        self.logger.log(logging.DEBUG, "[{}]: autoadvance disabled".format(int(QThread.currentThreadId())))
    

    @pyqtSlot()
    def storeChannelSettings(self):
        self.sendTextRequest.emit("E")                                                     # save settings in lightsource to EEPROM
        self.startReceiverRequest.emit()                                                   # get response
        self.logger.log(logging.DEBUG, "[{}]: channel settings stored in EEPROM".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def loadChannelSettings(self):
        lines = [ "e", 
                  "x"
                 ]
        self.connectLightSourceRequest.emit()
        self.sendLinesRequest.emit(lines)
        self.startReceiverRequest.emit()
        self.logger.log(logging.DEBUG, "[{}]: channel settings loaded from EEPROM".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def queryChannelSettings(self):
        self.connectLightSourceRequest.emit()
        self.sendTextRequest.emit("x")                                                     # query current settings
        self.startReceiverRequest.emit()
        self.logger.log(logging.DEBUG, "[{}]: channel settings loaded from EEPROM".format(int(QThread.currentThreadId())))
        
    @pyqtSlot()
    def turnOffAllChannels(self):
        self.sendTextRequest.emit("Z")                                                     # turn off all channels
        self.logger.log(logging.DEBUG, "[{}]: turned off all channels.".format(int(QThread.currentThreadId())))

    ########################################################################################
    # Turn On Channels Manually
    # LEDs remain on until push button is pressed again (latch)

    @pyqtSlot()
    def on_pushButton_TurnOnChannel(self):
        sender = self.sender()
        isChecked = sender.isChecked()
        senderName = sender.objectName()
        channel = int(parse("pushButton_TurnOnChannel{}", senderName)[0])
        if channel >= 1 and channel <=NUM_LEDS:
            if isChecked: 
                self._manualTurnOnChannel(channel)
                sender.setText("On")
            else: 
                self._manualTurnOffChannel(channel)
                sender.setText("Off")
            self.logger.log(logging.DEBUG, "[{}]: pushed channel {} manual button {}".format(int(QThread.currentThreadId()), channel, isChecked))
        else:
            self.logger.log(logging.DEBUG, "[{}]: not valid channel {}".format(int(QThread.currentThreadId()), channel))
            
    ########################################################################################
    # Enable Channels in the Measurement Sequence

    @pyqtSlot()
    def on_enableChannel(self):
        sender = self.sender()
        isChecked = sender.isChecked()
        senderName = sender.objectName()
        channel = int(parse("checkBox_MeasureChannel{}", senderName)[0])
        if channel >= 1 and channel <= NUM_LEDS:
            if isChecked: 
                self.sendTextRequest.emit("M{}".format(channel-1)) # enable channel
            else: 
                self.sendTextRequest.emit("m{}".format(channel-1)) # disable channel
            self.startReceiverRequest.emit()    
            self.logger.log(logging.DEBUG, "[{}]: channel {} is measured: {}".format(int(QThread.currentThreadId()), channel, isChecked))
        else:
            self.logger.log(logging.DEBUG, "[{}]: not valid channel {}".format(int(QThread.currentThreadId()), channel))
    
    ########################################################################################
    # Request channel information and update user interface
     
    @pyqtSlot(list)
    def on_ChannelSettings(self, lines):
        """ Channel settings from light source are available """
        self.logger.log(logging.DEBUG, "[{}]: channel settings received.".format(int(QThread.currentThreadId())))
        for text in lines:
            self.logger.log(logging.DEBUG, "[{}]: {}".format(int(QThread.currentThreadId()),text))
            # scan text for settings
            # "Channel: %2d pin: %2d %s %6.2f[%%] duty [%4d] Name: %s\r\n" 
            # text = "Channel:  0 pin:  2 On   97.00[%] duty [  61] Name: 365"
            # text = "Channel:  1 pin:  3 On    3.21[%] duty [1981] Name: 460"
            # text = "Channel:  2 pin:  4 On   11.62[%] duty [1809] Name: 525"
            r = parse("Channel: {:2d} pin: {:2d} {} {:6.2f}[%] duty [{:4d}] Name: {}", text)
            if r is not None:
                if len(r[:]) >= 6: # make sure we got correct status reponse
                    channel = r[0]
                    if r[2].strip() == 'On': 
                        enabled = True 
                    else: 
                        enabled = False
                    intensity = r[3]
                    name = str(r[5]).strip()
                    if name == '': name = "CH"+str(channel+1)
                    if channel>=0 and channel<=12 and intensity>=0. and intensity<=100. and self.ui is not None : # reasonable values
                        # find the user interface elements (condenses the code)
                        lineEdit         = self.ui.findChild(QLineEdit, "lineEdit_Channel"+str(channel+1))
                        horizontalSlider = self.ui.findChild(QSlider,   "horizontalSlider_Channel"+str(channel+1))
                        checkBoxMeasure  = self.ui.findChild(QCheckBox, "checkBox_MeasureChannel"+str(channel+1))
                        labelChannel     = self.ui.findChild(QLabel,    "label_Channel"+str(channel+1))
                        checkBoxDisplay  = self.ui.findChild(QCheckBox, "checkBox_DisplayChannel"+str(channel+1))
                        # block signals from user interface elements when changing their values
                        checkBoxMeasure.blockSignals(True)
                        checkBoxDisplay.blockSignals(True)
                        self.ui.comboBox_FirstChannel.blockSignals(True)
                        self.ui.comboBox_SecondChannel.blockSignals(True)
                        self.ui.comboBox_SelectBlueChannel.blockSignals(True)
                        self.ui.comboBox_SelectGreenChannel.blockSignals(True)
                        self.ui.comboBox_SelectRedChannel.blockSignals(True)
                        # update user interface values
                        horizontalSlider.setValue(int(intensity*10.0))
                        lineEdit.setText(str(intensity))
                        labelChannel.setText(name)
                        checkBoxMeasure.setText(name)
                        checkBoxMeasure.setChecked(enabled)
                        checkBoxDisplay.setText(name)
                        checkBoxDisplay.setChecked(enabled)
                        self.ui.comboBox_FirstChannel.setItemText(channel, name)
                        self.ui.comboBox_SecondChannel.setItemText(channel, name)
                        self.ui.comboBox_SelectBlueChannel.setItemText(channel, name)
                        self.ui.comboBox_SelectGreenChannel.setItemText(channel, name)
                        self.ui.comboBox_SelectRedChannel.setItemText(channel, name)
                        # unblock signals
                        checkBoxMeasure.blockSignals(False)
                        checkBoxDisplay.blockSignals(False)
                        self.ui.comboBox_FirstChannel.blockSignals(False)
                        self.ui.comboBox_SecondChannel.blockSignals(False)
                        self.ui.comboBox_SelectBlueChannel.blockSignals(False)
                        self.ui.comboBox_SelectGreenChannel.blockSignals(False)
                        self.ui.comboBox_SelectRedChannel.blockSignals(False)
                    # end values are in expected range
                # end got correct number of values
            # end found line with channel information
        # end for loop over lines received
        self.disconnectLightSourceRequest.emit()
        # self.serialWorker.textReceived.disconnect(self.on_ChannelSettings)               # disconnect serial receiver to channel settings handler
                
    ########################################################################################
    # LED Intensity, Horizontal Slider

    @pyqtSlot()
    def on_IntensitySliderReleased(self):
        """ When the slider is released take the value and send over serial port """
        sender = self.sender()
        value = sender.value()
        # find the user element to condense the code
        senderName = sender.objectName()
        channel = int(parse("horizontalSlider_Channel{}", senderName)[0])
        if channel >= 1 and channel <=NUM_LEDS:
            self._setChannelIntensity(channel, float(value)/10.)
        self.logger.log(logging.DEBUG, "[{}]: intensity slider on channel {} released at value {}.".format(int(QThread.currentThreadId()),channel,value))

    @pyqtSlot(int)
    def on_IntensitySliderChanged(self,value):
        """ Update the line edit box when the slider is moved """
        sender = self.sender()
        senderName = sender.objectName()
        channel = int(parse("horizontalSlider_Channel{}", senderName)[0])
        if channel >= 1 and channel <= NUM_LEDS and self.ui is not None:
            lineEdit = self.ui.findChild(QLineEdit, "lineEdit_Channel"+str(channel))
            lineEdit.setText(str(float(value)/10.))
            self.logger.log(logging.DEBUG, "[{}]: intensity channel {} changed to {}.".format(int(QThread.currentThreadId()),channel,value))
        else:
            self.logger.log(logging.DEBUG, "[{}]: not valid channel {}.".format(int(QThread.currentThreadId()),channel))

    ########################################################################################
    # LED Intensity, Line Edit

    @pyqtSlot()
    def on_IntensityLineEditChanged(self):
        """ Manually entered text into the line edit field, update slider and send to serial port """
        sender = self.sender()
        value = float(sender.text())
        senderName = sender.objectName()
        channel = int(parse("lineEdit_Channel{}", senderName)[0])
        if value >= 0. and value <=100. and channel>=0 and channel <= NUM_LEDS and self.ui is not None:
            horizontalSlider = self.ui.findChild(QSlider, "horizontalSlider_Channel"+str(channel))
            horizontalSlider.setValue(int(value*10.))           
            self._setChannelIntensity(channel, value)
            self.logger.log(logging.DEBUG, "[{}]: intensity channel {} changed".format(int(QThread.currentThreadId()), channel))
