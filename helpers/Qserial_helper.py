############################################################################################
# QT Serial Helper
############################################################################################
# July 2022: initial work
# ------------------------------------------------------------------------------------------
# Urs Utzinger
# University of Arizona 2022
############################################################################################

############################################################################################
# Helpful readings:
# ------------------------------------------------------------------------------------------
# Signals and Slots
#      https://realpython.com/python-pyqt-qthread/
#      https://www.tutorialspoint.com/pyqt/pyqt_signals_and_slots.htm
#   Examples
#      https://stackoverflow.com/questions/41026032/pyqt5-how-to-send-a-signal-to-a-worker-thread
#      https://stackoverflow.com/questions/68163578/stopping-an-infinite-loop-in-a-worker-thread-in-pyqt5-the-simplest-way
#      https://stackoverflow.com/questions/61625043/threading-with-qrunnable-proper-manner-of-sending-bi-directional-callbacks
#      https://stackoverflow.com/questions/52973090/pyqt5-signal-communication-between-worker-thread-and-main-window-is-not-working
#      https://stackoverflow.com/questions/61625043/threading-with-qrunnable-proper-manner-of-sending-bi-directional-callbacks
#
# Threads
#   https://realpython.com/python-pyqt-qthread/
#   http://blog.debao.me/2013/08/how-to-use-qthread-in-the-right-way-part-1/
#
# Timer, infinite loop
#   Can not use forever loop as loop blocks worker from processing signals.
#   Start jobs wigth Qtimer or create function with time.sleep() followed by QApplication.processEvents()
# 
#      https://stackoverflow.com/questions/55651718/how-to-use-a-qtimer-in-a-separate-qthread
#      https://programmer.ink/think/no-event-loop-or-use-of-qtimer-in-non-gui-qt-threads.html
#      https://stackoverflow.com/questions/47661854/use-qtimer-to-run-functions-in-an-infinte-loop
#      https://stackoverflow.com/questions/10492480/starting-qtimer-in-a-qthread
#      LOWQ https://www.pythonfixing.com/2022/03/fixed-how-to-use-qtimer-inside-qthread.html
#      https://stackoverflow.com/questions/23607294/qtimer-in-worker-thread
#      https://stackoverflow.com/questions/60649644/how-to-properly-stop-qtimer-from-another-thread
#
# Serial
#   Examples using pySerial
#      https://programmer.group/python-uses-pyqt5-to-write-a-simple-serial-assistant.html
#      https://github.com/mcagriaksoy/Serial-Communication-GUI-Program/blob/master/qt.py
#      https://hl4rny.tistory.com/433
#      https://iosoft.blog/pyqt-serial-terminal-code/
#   Examples using QSerialPort
#      https://stackoverflow.com/questions/55070483/connect-to-serial-from-a-pyqt-gui
#      https://ymt-lab.com/en/post/2021/pyqt5-serial-monitor/
#
# Console Application
#      https://stackoverflow.com/questions/4180394/how-do-i-create-a-simple-qt-console-application-in-c
#
############################################################################################
from serial import Serial as sp
from serial import EIGHTBITS, PARITY_NONE, STOPBITS_ONE
from serial.tools import list_ports 
import time, logging

from enum import Enum

from PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, QStandardPaths
from PyQt5.QtWidgets import QLineEdit, QSlider, QCheckBox, QLabel, QFileDialog

class SerialReceiverState(Enum):
    """ 
    When data is expected on the serial input we use timer to read line by line.
    When no data is expected we are stopped state
    When data is expected but has not yet arrived we are in awaiting state
    When data has arrived and there might be more data arriving we are in receiving state
    When there is no longer data arriving we are in finished state
    When we expected data but no data arrived we will end up in state timeout 
    """
    stopped               =  0
    awaitingData          =  1
    receivingData         =  2
    finishedReceivingData =  3
    timedOut              = -1
    
############################################################################################
# QSerial interaction with User Interface
# This section of the code cannot be move to a separate thread because it modifies to UI
############################################################################################

class QSerialUI(QObject):
    """
    Serial Interface for QT
    
    Signals
        scanPortsRequest
        scanBaudRatesRequest
        changePortRequest
        sendTextRequest
        sendLinesRequest
        startReceiverRequest
        setupReceiverRequest
        serialStatusRequest
        finishWorkerRequest
        closePortRequest
        
    Slots
        on_serialMonitorSend
        on_serialMonitorSendUpArrowPressed
        on_serialMonitorSendDownArrowPressed
        on_pushButton_SerialClearOutput
        on_pushButton_SerialSave
        on_pushButton_SerialScan
        on_comboBoxDropDown_SerialPorts
        on_comboBoxDropDown_BaudRates
        on_serialStatusReady
        on_newPortListReady
        on_newBaudListReady
        on_SerialReceivedText
                   
    """

    # Signals
    ########################################################################################

    scanPortsRequest     = pyqtSignal()                                                    # port scan
    scanBaudRatesRequest = pyqtSignal()                                                    # baudrates scan
    changePortRequest    = pyqtSignal(str, int)                                            # port and baudrate to change
    changeBaudRequest    = pyqtSignal(int)                                                 # request serial baud rate to change
    sendTextRequest      = pyqtSignal(str)                                                 # request to transmit text to TX
    sendLinesRequest     = pyqtSignal(list)                                                # request to transmit lines of text to TX
    startReceiverRequest = pyqtSignal()                                                    # start serial receiver, expecting text
    setupReceiverRequest = pyqtSignal()                                                    # start serial receiver, expecting text
    serialStatusRequest  = pyqtSignal()                                                    # request serial port and baudrate status
    finishWorkerRequest  = pyqtSignal()                                                    # request worker to finish
    closePortRequest     = pyqtSignal()                                                    # close the current serial Port

    defaultBaudRate = 115200
           
    def __init__(self, parent=None, ui=None):
        # super().__init__()
        super(QSerialUI, self).__init__(parent)

        # state variables, poplated by service routines
        self.BaudRates             = []                                                    # e.g. (1200, 2400, 9600, 115200)
        self.serialPortNames       = []                                                    # human readable
        self.serialPorts           = []                                                    # e.g. COM6
        self.serialPort            = ""                                                    # e.g. COM6
        self.serialBaudRate        = -1                                                    # e.g. 115200
        self.serialSendHistory     = []                                                    # previously sent commands
        self.serialSendHistoryIndx = -1                                                    #

        self.logger = logging.getLogger("QSerUI_")           
                   
        if ui is None:
            self.logger.log(logging.ERROR, "[{}]: need to have access to User Interface".format(int(QThread.currentThreadId())))
        self.ui = ui
                
        self.logger.log(logging.INFO, "[{}]: initialized.".format(int(QThread.currentThreadId())))

    # Rewsponse to User Interface Signals
    ########################################################################################

    @pyqtSlot()
    def on_serialMonitorSend(self):
        """
        Transmitting Text from UI
        """
        text = self.ui.lineEdit_SerialText.text()                                          # obtain text from send input window
        self.serialSendHistory.append(text)                                                # keep history of previously sent commands
        self.sendTextRequest.emit(text)
        self.ui.lineEdit_SerialText.clear()
        self.startReceiverRequest.emit()
        
    @pyqtSlot()
    def on_serialMonitorSendUpArrowPressed(self):
        """ 
        Handle special keys on lineEdit: UpArrow
        """
        # increment history pointer
        self.serialSendHistoryIndx += 1
        # if pointer at end of buffer restart at -1
        if self.serialSendHistoryIndx == len(self.serialSendHistory):
            self.serialSendHistoryIndx = -1
        # populate with previous sent command from history buffer
        # if index -1 set use empty string as previous sent command
        if self.serialSendHistoryIndx == -1:
            self.ui.lineEdit_SerialText.setText("")
        else: 
            self.ui.lineEdit_SerialText.setText(self.serialSendHistory[self.serialSendHistoryIndx])

    @pyqtSlot()
    def on_serialMonitorSendDownArrowPressed(self):
        """ 
        Handle special keys on lineEdit: DownArrow
        """
        # increment history pointer
        self.serialSendHistoryIndx -= 1
        # if pointer at start of buffer reset index to end of buffer 
        if self.serialSendHistoryIndx == -2:
            self.serialSendHistoryIndx = len(self.serialSendHistory) - 1
        # populate with previous sent command from history buffer
        # if index -1 set use empty string as previous sent command
        if self.serialSendHistoryIndx == -1:
            self.ui.lineEdit_SerialText.setText("")
        else: 
            self.ui.lineEdit_SerialText.setText(self.serialSendHistory[self.serialSendHistoryIndx])

    @pyqtSlot()
    def on_pushButton_SerialClearOutput(self):
        """ 
        Clearing Text Display Window 
        """
        self.ui.textBrowser_SerialTextDisplay.clear()

    @pyqtSlot()
    def on_pushButton_SerialSave(self):
        """ 
        Saving Text from Display Window into Text File 
        """
        stdFileName = QStandardPaths.writableLocation(QtCore.QStandardPaths.DocumentsLocation) + "/Serial.txt"
        fname = QFileDialog.getSaveFileName(self, 'Save as', stdFileName, "Text files (*.txt)")
        # check if fname is valid, user can select cancel
        with open(fname[0], 'w') as f: 
            f.write(self.ui.textBrowser_SerialTextDisplay.toPlainText())

    @pyqtSlot()
    def on_pushButton_SerialScan(self):
        """ 
        Updating Serial Port List
        """
        self.scanPortsRequest.emit()
        self.logger.log(logging.INFO, "[{}]: scanning for serial ports.".format(int(QThread.currentThreadId())))
        # Serial worker will create newPortList signal which is handeled by on_newPortList below 

    @pyqtSlot()
    def on_comboBoxDropDown_SerialPorts(self):
        """ 
        New Port Selected 
        """
        lenSerialPorts     = len(self.serialPorts)
        lenBaudRates       = len(self.BaudRates)
        if lenSerialPorts > 0: # only continue if we have recognized serial ports
            index = self.ui.comboBoxDropDown_SerialPorts.currentIndex()
            if index == lenSerialPorts: # "None" was selected so close the port
                self.closePort.emit()
                return
            else:
                port = self.serialPorts[index] # we have valid port
            if lenBaudRates > 0: # if we have recognized serial baudrates
                index = self.ui.comboBoxDropDown_BaudRates.currentIndex()
                if index < lenBaudRates: # last entry is -1
                    baudrate = self.BaudRates[index]
                else:
                    baudrate = self.defaultBaudRate                                        # use default baud rate
            else: 
                baudrate = self.defaultBaudRate                                            # use default baud rate, user can change later
                
            # change port if port or baudrate changed                    
            if (port != self.serialPort):
                QTimer.singleShot(0,   lambda: self.changePortRequest.emit(port, baudrate)) # takes 11ms to open
                self.serialBaudRate = baudrate
                self.serialPort = port
                QTimer.singleShot(50, lambda: self.scanBaudRatesRequest.emit())            # request to scan serial baudrates
                QTimer.singleShot(100,  lambda: self.serialStatusRequest.emit())           # request to report serial port status
                self.logger.log(logging.INFO, "[{}]: port {} baud {}".format(int(QThread.currentThreadId()), port, baudrate))
            elif (baudrate != self.serialBaudRate):
                self.changeBaud.emit(baudrate)
                self.logger.log(logging.INFO, "[{}]: baudrate {}".format(int(QThread.currentThreadId()), baudrate))
            else: 
                self.logger.log(logging.DEBUG, "[{}]: port and baudrate remain the same".format(int(QThread.currentThreadId()), port, baudrate))
        else: 
            self.logger.log(logging.DEBUG, "[{}]: no ports available".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def on_comboBoxDropDown_BaudRates(self):
        """ 
        New BaudRate selected 
        """
        lenBaudRates = len(self.BaudRates)
        if lenBaudRates > 0:                                                               # if we have recognized serial baudrates
            index = self.ui.comboBoxDropDown_BaudRates.currentIndex()
            if index < lenBaudRates:                                                       # last entry is -1
                baudrate = self.BaudRates[index]
            else:
                baudrate = self.defaultBaudRate                                            # use default baud rate                            
            if (baudrate != self.serialBaudRate):                                          # change baudrate if different from current
                self.changeBaud.emit(baudrate)
                self.logger.log(logging.INFO, "[{}]: baudrate {}".format(int(QThread.currentThreadId()), baudrate))
            else: 
                self.logger.log(logging.INFO, "[{}]: baudrate remains the same".format(int(QThread.currentThreadId())))
        else: 
            self.logger.log(logging.INFO, "[{}]: no baudrates available".format(int(QThread.currentThreadId())))

    # Response to Serial Signals
    ########################################################################################

    @pyqtSlot(str, int)
    def on_serialStatusReady(self, port, baud):
        """ 
        Serial status report available 
        """
        self.serialPort = port
        self.serialBaudRate = baud
        # adjust the combobox current itemt to match the current port
        try:
            if self.serialPort == "":
                index = self.serialPorts.index("None")                                     # find current port in serial port list
            else:
                index = self.serialPorts.index(self.serialPort)                            # find current port in serial port list
            self.ui.comboBoxDropDown_SerialPorts.setCurrentIndex(index)                    # update serial port combobox
            self.logger.log(logging.DEBUG, "[{}]: port {}.".format(int(QThread.currentThreadId()),self.serialPortNames[index]))
        except:
            self.logger.log(logging.DEBUG, "[{}]: port not available.".format(int(QThread.currentThreadId())))
        # adjust the combobox current item to match the current baudrate
        try: 
            index = self.BaudRates.index(self.serialBaudRate)                              # find baud rate in serial baud rate list
            self.ui.comboBoxDropDown_BaudRates.setCurrentIndex(index)                      #  baud combobox
            self.logger.log(logging.DEBUG, "[{}]: baudrate {}.".format(int(QThread.currentThreadId()),self.BaudRates[index]))
        except:
            self.logger.log(logging.DEBUG, "[{}]: no baudrate available.".format(int(QThread.currentThreadId())))

    @pyqtSlot(list, list)
    def on_newPortListReady(self, ports, portNames):
        """ 
        New serial port list available 
        """
        self.logger.log(logging.DEBUG, "[{}]: port list received.".format(int(QThread.currentThreadId())))
        self.serialPorts = ports
        self.serialPortNames = portNames
        lenPortNames = len(self.serialPortNames)
        # block the box from emitting changed index signal when items are added
        self.ui.comboBoxDropDown_SerialPorts.blockSignals(True)
        # what is currently selected in the box?
        selected = self.ui.comboBoxDropDown_SerialPorts.currentText()
        # populate new items
        self.ui.comboBoxDropDown_SerialPorts.clear()
        self.ui.comboBoxDropDown_SerialPorts.addItems(self.serialPortNames+['None'])
        # search for the previously selected item
        index = self.ui.comboBoxDropDown_SerialPorts.findText(selected)
        if index > -1: # if we found previously selected item
            self.ui.comboBoxDropDown_SerialPorts.setCurrentIndex(index)
        else:  # if we did not find previous item set box to last item (None)
            self.ui.comboBoxDropDown_SerialPorts.setCurrentIndex(lenPortNames)
        # enable signals again
        self.ui.comboBoxDropDown_SerialPorts.blockSignals(False)

    @pyqtSlot(tuple)
    def on_newBaudListReady(self, bauderates):
        """ 
        New baud rate list available
        For logic and sequence of commands refer to newPortList
        """
        self.logger.log(logging.DEBUG, "[{}]: baud list received.".format(int(QThread.currentThreadId())))
        self.BaudRates = list(bauderates)
        lenBaudRates = len(self.BaudRates)
        self.ui.comboBoxDropDown_BaudRates.blockSignals(True)
        selected = self.ui.comboBoxDropDown_BaudRates.currentText()
        self.ui.comboBoxDropDown_BaudRates.clear()
        self.ui.comboBoxDropDown_BaudRates.addItems([str(x) for x in self.BaudRates + [-1]])
        if (selected == '-1' or selected == ''):
            index = self.ui.comboBoxDropDown_BaudRates.findText(str(self.serialBaudRate))
        else: 
            index = self.ui.comboBoxDropDown_BaudRates.findText(selected)
        if index > -1:
            self.ui.comboBoxDropDown_BaudRates.setCurrentIndex(index)
        else:
            self.ui.comboBoxDropDown_BaudRates.setCurrentIndex(lenBaudRates)        
        self.ui.comboBoxDropDown_BaudRates.blockSignals(False)

    @pyqtSlot(list)
    def on_SerialReceivedText(self, lines):
        """ Received text on serial port """
        self.logger.log(logging.DEBUG, "[{}]: text received.".format(int(QThread.currentThreadId())))
        for text in lines:
            self.logger.log(logging.DEBUG, "[{}]: {}".format(int(QThread.currentThreadId()),text))
            self.ui.textBrowser_SerialTextDisplay.append("{}".format(text))

############################################################################################
# Q Serial
# separate thread handling serial input and output
############################################################################################

class QSerial(QObject):
    """
    Serial Interface for QT

    Worker Signals
        textReceived              recevied text (list of lines) on serial RX
        newPortListReady          compled a port scan
        newBaudListReady          compled a baud scan
        serialStatusReady         report port and baudrate

    Worker Slots
        on_startReceiverRequest()        start timer that reads input port
        on_stopReceiverRequest()         stop  timer that reads input port
        on_stopWorkerRequest()           stop  timer and close serial port
        on_sendTextRequest(text)         worker received request to transmit text
        on_changePortRequest(port, baud) worker received request to change port
        on_closePortRequest()            worker received request to close current port
        on_changeBaudRequest(baud)       worker received request to change baud rate
        on_scanPortsRequest()            worker received request to scan for serial ports
        on_scanBaudRatesRequest()        worker received request to scan for serial baudrates
        on_serialStatusRequest()         worker received request to report current port and baudrate 

    """
        
    # Signals
    ########################################################################################
    textReceived     = pyqtSignal(list)                                                    # text received on serial port
    newPortListReady = pyqtSignal(list, list)                                              # updated list of serial ports is available
    newBaudListReady = pyqtSignal(tuple)                                                   # updated list of baudrates is available
    serialStatusReady= pyqtSignal(str, int)                                                # serial status is available
    finished         = pyqtSignal() 
    # stopReceiverRequest = pyqtSignal()
        
    def __init__(self, parent=None):
        # super().__init__()
        super(QSerial, self).__init__(parent)

        self.logger = logging.getLogger("QSerial")           

        self.ser = PSerial()
        self.ser.scanports()
        self.lines = [] # received lines of text
        self.serialPorts     = [sublist[0] for sublist in self.ser.ports] # COM3 ...
        self.serialPortNames = [sublist[1] for sublist in self.ser.ports] # USB ... (COM3)
        self.serialBaudRates = self.ser.baudrates
        
        self.textLineTerminator = '\r\n'

        # Adjust response time, shorter interval will result in faster display of text 
        # but take more cpu resources
        # Teensy checks serial input every 1ms
        self.RECEIVER_INTERVAL    =     10 # [ms] 0.01 seconds
        self.RECEIVER_FINISHCOUNT =      1 # [times] = 0.01 seconds, receiver will finish when there was no input 5 times
        self.RECEIVER_TIMEOUT     =   2000 # 2.000 seconds        

        self.logger.log(logging.INFO, "[{}]: initialized.".format(int(QThread.currentThreadId())))
        
    # Slots
    ########################################################################################

    @pyqtSlot()
    def on_setupReceiverRequest(self):
        """ 
        Set up a QTimer for reading data from serial input line at predefined interval.
        Does not start the timer.
        We can not create timer in init function because it will not move with QSerial when its moved to new thread.
        """
        self.serialReceiverState = SerialReceiverState.stopped
        self.receiverTimer = QTimer()
        self.receiverTimer.setInterval(self.RECEIVER_INTERVAL) 
        self.receiverTimer.timeout.connect(self._updateReceiver)
        self.logger.log(logging.DEBUG, "[{}]: setup receiver timer on thread.".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def on_startReceiverRequest(self):
        """ 
        Set up a QTimer for reading data from serial input line (RX) every 1..100 ms
        We will need to start receiver each time we send a command over serial (TX) and expecting a response on (RX).
        Text is sent from main task. 
        Response will need to be analyzed in main task.
        """
        self.receiverTimer.start()
        self.receiverTimerStartedTime =  time.time()
        self.receiverTimerTimeout = self.RECEIVER_TIMEOUT
        self.serialReceiverState = SerialReceiverState.awaitingData
        self.logger.log(logging.INFO, "[{}]: started receiver.".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def on_stopReceiverRequest(self):
        """ 
        Stop the timer
        """
        self.receiverTimer.stop()
        self.serialReceiverState = SerialReceiverState.stopped
        self.logger.log(logging.INFO, "[{}]: stopped receiver.".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def _updateReceiver(self):
        """ 
        Reading lines of text from serial RX 
        State Machine:
          - stopped (timer not running)
          - awaiting data (started, checking if data available)
          - receiving data (data is available on port, checking if more data arrives)
          - finished receiving data (no more data arrived, stop timer)
          - timeout (no data arrived until timout, stop timer)
        """
         
        if self.ser.ser_open and (self.serialReceiverState != SerialReceiverState.stopped):
            # initialize
            if   self.serialReceiverState == SerialReceiverState.awaitingData:
                self.lines = []
                
            # update states
            if (time.time()-self.receiverTimerStartedTime) < self.RECEIVER_TIMEOUT:
                avail = self.ser.avail()
                if avail > 0:
                    self.logger.log(logging.DEBUG, "[{}]: checking input, {} chars available.".format(int(QThread.currentThreadId()),avail))
                    self.serialReceiverState = SerialReceiverState.receivingData
                else:
                    if self.serialReceiverState == SerialReceiverState.receivingData:
                        self.serialReceiverState = SerialReceiverState.finishedReceivingData
                        self.serialReceiverCountDown = 0
            else:
                self.serialReceiverState = SerialReceiverState.timedOut

            # execute/advance state machine
            if self.serialReceiverState == SerialReceiverState.receivingData:
                while self.ser.avail() > 0:
                    line = self.ser.readline()
                    self.logger.log(logging.INFO, "[{}]: {}".format(int(QThread.currentThreadId()),line))
                    self.lines.append(line)
            elif self.serialReceiverState == SerialReceiverState.finishedReceivingData:
                self.serialReceiverCountDown += 1
                if self.serialReceiverCountDown >= self.RECEIVER_FINISHCOUNT:
                    self.receiverTimer.stop()
                    self.textReceived.emit(self.lines)
                    self.serialReceiverState = SerialReceiverState.stopped
                    self.logger.log(logging.DEBUG, "[{}]: finished receiving text.".format(int(QThread.currentThreadId())))
            elif self.serialReceiverState == SerialReceiverState.timedOut:
                self.receiverTimer.stop()
                self.serialReceiverState = SerialReceiverState.stopped
                self.logger.log(logging.DEBUG, "[{}]: receiving timedout.".format(int(QThread.currentThreadId())))
        else:
            self.logger.log(logging.DEBUG, "[{}]: checking input, receiver is stopped or port is not open.".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def on_stopWorkerRequest(self): 
        """ 
        Worker received request to stop
        We want to stop timer and close serial port and then let subscribers know that serial worker is no longer available
        """
        self.receiverTimer.stop()        
        self.ser.close()
        self.serialPort = ""
        self.serialBaurate = -1
        self.logger.log(logging.DEBUG, "[{}]: stopped timer, closed port.".format(int(QThread.currentThreadId())))
        self.finished.emit()
            
    @pyqtSlot(str)
    def on_sendTextRequest(self, text):
        """ Request to transmit text to serial TX line """
        if self.ser.ser_open:
            res = self.ser.write(text+self.textLineTerminator)
            self.logger.log(logging.INFO, "[{}]: transmitted \"{}\" [{}].".format(int(QThread.currentThreadId()),text, res))
        else:
            self.logger.log(logging.INFO, "[{}]: tx, port not opened.".format(int(QThread.currentThreadId())))

    @pyqtSlot(list)
    def on_sendLinesRequest(self, lines: list):
        """ Request to transmit multiple lines of text to serial TX line"""
        if self.ser.ser_open:
            for text in lines:
                res = self.ser.write(text+self.textLineTerminator)
                self.logger.log(logging.INFO, "[{}]: transmitted \"{}\" [{}].".format(int(QThread.currentThreadId()),text, res))
        else:
            self.logger.log(logging.INFO, "[{}]: tx, port not opened.".format(int(QThread.currentThreadId())))

    @pyqtSlot(str, int)
    def on_changePortRequest(self, port, baud):
        """ Request to change port received """
        self.ser.close()
        if port != "":
            self.ser.open(port, baud)

    @pyqtSlot()
    def on_closePortRequest(self):
        """ Request to close port received """
        self.ser.close()

    @pyqtSlot(int)
    def on_changeBaudRateRequest(self, baud):
        """ new baudrate received """
        if (baud is None) or (baud <= 0):
            self.logger.log(logging.WARNING, "[{}]: range error, baudrate not changed to {},".format(int(QThread.currentThreadId()), baud))
            return
        else:            
            if self.ser.ser_open:
                if self.serialBaudRates.index(baud) >= 0:
                    self.ser.baud = baud # change baud rate
                    if self.ser.baud == baud: # check if new value matches desired value
                        self.serialBaudRate = baud  # update local variable
                        self.logger.log(logging.DEBUG, "[{}]: changed baudrate to {}.".format(int(QThread.currentThreadId()), baud))
                    else:
                        self.serialBaudRate = self.ser.baud
                        self.logger.log(logging.ERROR, "[{}]: failed to set baudrate to {}.".format(int(QThread.currentThreadId()), baud))
                else: 
                    self.logger.log(logging.ERROR, "[{}]: baudrate {} no available.".format(int(QThread.currentThreadId()), baud))
                    self.serialBaudRate = -1
            else:
                self.logger.log(logging.ERROR, "[{}]: failed to set baudrate, serial port not open!".format(int(QThread.currentThreadId())))

    @pyqtSlot()
    def on_scanPortsRequest(self):
        """ Request to scan for serial ports received """            
        if self.ser.scanports() > 0 :
            self.serialPorts =     [sublist[0] for sublist in self.ser.ports]
            self.serialPortNames = [sublist[1] for sublist in self.ser.ports]
        else :
            self.serialPorts = []
            self.serialPortNames = []        
        self.logger.log(logging.DEBUG, "[{}]: Port(s) {} available.".format(int(QThread.currentThreadId()),self.serialPortNames))
        self.newPortListReady.emit(self.serialPorts, self.serialPortNames)
        
    @pyqtSlot()
    def on_scanBaudRatesRequest(self):
        """ Request to report serial baud rates received """
        if self.ser.ser_open:
            self.serialBaudRates = self.ser.baudrates
        else:
            self.serialBaudRates = ()
        if len(self.serialBaudRates) > 0:
            self.logger.log(logging.DEBUG, "[{}]: baudrate(s) {} available.".format(int(QThread.currentThreadId()),self.serialBaudRates))
        else:
            self.logger.log(logging.ERROR, "[{}]: no baudrates available, port is closed.".format(int(QThread.currentThreadId())))
        self.newBaudListReady.emit(self.serialBaudRates)

    @pyqtSlot()
    def on_serialStatusRequest(self):
        """ Request to report serial port and baudrate received"""
        self.logger.log(logging.DEBUG, "[{}]: provided serial status".format(int(QThread.currentThreadId())))
        if self.ser.ser_open:
            self.serialStatusReady.emit(self.ser.port, self.ser.baud)
        else:
            self.serialStatusReady.emit("", self.ser.baud)

################################################################################
# Serial Low Level 
################################################################################

class PSerial():
    """
    Serial Wrapper.
    Without this class the function Serial.in_waiting does not seem to work.
    """
    
    def __init__(self):

        self.logger = logging.getLogger("PSerial")           

        self.ser = None
        self._port = ""
        self._baud = -1
        self.ser_open = False
        
        _ = self.scanports()
    
    def scanports(self):
        """ 
        scans for all available ports 
        """
        self._ports = [
            [p.device, p.description]
            for p in list_ports.comports()
        ]
        return len(self._ports)

    def open(self, port, baud):
        """ 
        open specified port 
        """
        try:       
            self.ser = sp(
                port = port,                   # the serial device
                baudrate = baud,               # often 115200 but Teensy sends/receives as fast as possible
                bytesize = EIGHTBITS,          # most common option
                parity = PARITY_NONE,          # most common option
                stopbits = STOPBITS_ONE,       # most common option
                timeout = None,                # wait until requested characters are received on read request
                rtscts = False,                # do not use 'request to send' and 'clear to send' handshaking
                write_timeout = None,          # wait until requested characters are sent
                dsrdtr = False,                # dont want 'data set ready' signaling
                inter_byte_timeout = None,     # disable intercharacter timeout
                exclusive = None,              # do not share port in POSIX
                xonxoff = False )              # dont have 'xon/xoff' hangshaking in serial data stream

        except: 
            self.ser_open = False
            self.ser = None
            self._port=""
            self._baud=-1
            self.logger.log(logging.ERROR, "[SER]: failed to open port {}.".format(port))
            return False
        
        else: 
            self.logger.log(logging.INFO, "[SER]: {} opened with baud {}.".format(port, baud))
            self.ser_open = True
            self._baud = baud
            self._port = port
            return True
        
    def close(self):
        """ 
        closes serial port 
        """
        self.ser_open = False
        if (self.ser is not None):
            self.ser_open = False
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.ser.close()
            self._port = ""
            self._baud = -1
        self.logger.log(logging.INFO, "[SER]: closed.")
  
    def changeport(self, port, baud):
        """ 
        switch to diffferent port 
        """
        self.close()
        self.open(port, baud)
    
    def readline(self):
        """ reads a line of text """
        return self.ser.readline().decode().rstrip('\r\n')

    def writeline(self, line):
        """ sends a line of text """
        return self.ser.write((line+'\r\n').encode())

    def write(self, text):
        """ sends text """
        return self.ser.write(text.encode())

    def avail(self):
        """ is there data in the receiving buffer? """
        if self.ser is not None:
            return self.ser.in_waiting
        else:
            return -1
    
    # Setting and Reading internal variables
    ########################################################################################
        
    @property
    def ports(self):
        """ returns list of ports """
        return self._ports    
    @property
    def baudrates(self):
        """ returns list of baudrates """
        if self.ser_open:
            return self.ser.BAUDRATES
        else:
            return ()
    @property
    def connected(self):
        """ return true if connected """
        return self.ser_open

    @property
    def port(self):
        """ returns current port """
        if self.ser_open: return self._port
        else: return ""
    @port.setter
    def port(self, val):
        """ sets serial port """
        if (val is None) or  (val == ""):
            self.logger.log(logging.WARNING, "[SER]: no port given {}.".format(val))
            return
        else:
            if self.changeport(self, val, self.baud):
                self.logger.log(logging.INFO, "[SER]: port:{}.".format(val))
                self._port = val
            else:
                self.logger.log(logging.ERROR, "[SER]: failed to open port {}.".format(val))

    @property
    def baud(self):
        """ returns current serial baudrate """
        if self.ser_open: return self._baud
        else: return -1
    @baud.setter
    def baud(self, val):
        """ sets serial baud rate """
        if (val is None) or (val <= 0):
            self.logger.log(logging.WARNING, "[SER]: baudrate not changed to {}.".format(val))
            return
        if self.ser_open:
            self.ser.baudrate = val        # set new baudrate
            self._baud = self.ser.baudrate # request baudrate
            if (self._baud == val) : 
                self.logger.log(logging.INFO, "[SER]: baudrate:{}.".format(val))
            else:
                self.logger.log(logging.ERROR, "[SER]: failed to set baudrate to {}.".format(val))
        else:
            self.logger.log(logging.CRITICAL, "[SER]: failed to set baudrate, serial port not open!")


#####################################################################################
# Testing
#####################################################################################

if __name__ == '__main__':

    class MainTask(QObject):
        """ 
        Create the main task 
        
        Main Task Signals
            scanPortsRequest                initiate a serial port scan
            scanBaudRatesRequest            initiate a serial baudrate scan on curent port
            changePortRequest               user wants to change the port 
            changeBaudRequest               user wants to change the baudrate
            sendTextRequest                 user wants to transmit data to serial TX
            serialStatusRequest             user wants to know current port and baudrate
            runTestsRequest                 user wants to run tests
            finishWorkerRequest             user wants to finish worker

        Main Task Slots
            on_runTests():
            on_serialStatusReady(port, baud)
            on_newPortListReady(ports, portNames)
            on_newBaudListReady(bauderates)
            on_textReceived(lines)

        """

        # -------------------------------------------------
        # For program with QT User Interface this section will need to be integrated into MainWindow.
        # Examples in runTests would need to be connected to buttons.
        # Received text woul need to be displayed in text box.
        # -------------------------------------------------
        
        ####################################################
        # Serial Signals in main task
        ####################################################
        scanPortsRequest        = pyqtSignal()                                                        # request serial port scan
        scanBaudRatesRequest    = pyqtSignal()                                                        # request serial baudrates scan
        changePortRequest       = pyqtSignal(str, int)                                                # request serial port and baudrate to change
        changeBaudRequest       = pyqtSignal(int)                                                     # request serial baud rate to change
        sendTextRequest         = pyqtSignal(str, bool)                                                     # request to transmit text to TX
        startReceiverRequest    = pyqtSignal()
        serialStatusRequest     = pyqtSignal()                                                        # request serial port and baudrate status
        # test sequence of signals
        runTestsRequest         = pyqtSignal()                                                        # request execution of tests
        # stop worker
        finishWorkerRequest     = pyqtSignal()                                                        # request worker to finish
        
        def __init__(self, parent=None):
            """
            Initialize the components of main task.
            This will create worker and move it to seprate thread.
            This will create all the connections between slots and signals in both directions.
            """
            super().__init__(parent) # parent constructor
            # QMainWindow.__init__(self)
            
            self.logger = logging.getLogger("Main___")           

            ####################################################
            # Serial:  
            ####################################################
            self.serialBaudRates = []
            self.serialPortNames = []
            self.serialPorts     = []
            
            # Thread & Worker
            # Worker will operate in its own thread
            self.serialThread = QThread()                                                      # create QThread object
            # Lets start the Thread
            self.serialThread.start()                                                          # start thread which will start worker

            self.serialWorker = QSerial()                                                      # create worker object
            self.serialWorker.moveToThread(self.serialThread)                                  # move worker to thread        

            # Connecting Signal and Slots
            
            # Stop Worker / Thread
            self.serialWorker.finished.connect(         self.serialThread.quit                   )    # if worker emits finished quite worker thread
            self.serialWorker.finished.connect(         self.serialWorker.deleteLater            )    # delete worker at some time
            self.serialThread.finished.connect(         self.serialThread.deleteLater            )    # delete thread at some time

            # Signals from Worker to Main Window
            self.serialWorker.textReceived.connect(     self.on_textReceived                     )    # connect text display to serial receiver signal
            self.serialWorker.newPortListReady.connect( self.on_newPortList                      )    # connect new port list to its ready signal
            self.serialWorker.newBaudListReady.connect( self.on_newBaudList                      )    # connect new baud list to its ready signal
            self.serialWorker.serialStatusReady.connect(self.on_serialStatus                     )    # connect display serial status to ready signal

            # Signals from Main to Worker
            self.sendTextRequest.connect(               self.serialWorker.on_sendTextRequest     )    # connect sending text
            self.startReceiverRequest.connect(          self.serialWorker.on_startReceiverRequest)    # connect start receiver
            self.changePortRequest.connect(             self.serialWorker.on_changePortRequest   )    # conenct changing port
            self.changeBaudRequest.connect(             self.serialWorker.on_changeBaudRateRequest   )    # connect changing baudrate
            self.scanPortsRequest.connect(              self.serialWorker.on_scanPortsRequest    )    # connect request to scan ports
            self.scanBaudRatesRequest.connect(          self.serialWorker.on_scanBaudRatesRequest)    # connect request to scan baudrates
            self.serialStatusRequest.connect(           self.serialWorker.on_serialStatusRequest )    # connect request for serial status
            self.finishWorkerRequest.connect(           self.serialWorker.on_stopWrokerRequest   )    # connect finish request
            # Signals from Application to Main
            self.runTests.connect(                      self.on_runTests                         )    # connect test fucntion


            self.logger.log(logging.INFO, "[{}]: initialized.".format(int(QThread.currentThreadId())))

        def on_runTests(self):
            self.logger.log(logging.INFO, "[{}]: running tests.".format(int(QThread.currentThreadId())))
            QTimer.singleShot(0,     lambda: self.scanPortsRequest.emit())                            # request to port scan
            QTimer.singleShot(100,   lambda: self.changePortRequest.emit(self.serialPorts[-1], 9600)) # request to change/open port, at this time serialPorts list should be updates
            QTimer.singleShot(200,   lambda: self.scanBaudRatesRequest.emit())                        # scan baudrates again as we have port open now
            QTimer.singleShot(300,   lambda: self.serialStatusRequest.emit())                         # request serial status
            QTimer.singleShot(400,   lambda: self.changeBaudRequest.emit(115200))                     # request to change baud
            QTimer.singleShot(500,   lambda: self.serialStatusRequest.emit())                         # request serial status
            QTimer.singleShot(600,   lambda: self.sendTextRequest.emit("?"))                          # request serial status
            QTimer.singleShot(600,   lambda: self.startReceiverRequest.emit())                        # expecting a response
            QTimer.singleShot(2000,  lambda: self.finishWorkerRequest.emit())                         # request serial status
            QTimer.singleShot(2100, QCoreApplication.quit)                                            # request QApplication to quit

        @pyqtSlot(str, int)
        def on_serialStatusReady(self, port, baud):
            """ Received serial status report """
            self.serialPort = port
            self.serialBaud = baud
            try:
                index = self.serialPorts.index(self.serialPort)                                           # find current port in serial port list
                self.logger.log(logging.DEBUG, "[{}]: port {}.".format(int(QThread.currentThreadId()),self.serialPortNames[index]))
            except:
                self.logger.log(logging.DEBUG, "[{}]: port not available.".format(int(QThread.currentThreadId())))
            try: 
                index = self.serialBaudRates.index(self.serialBaud)                                       # find baud rate in serial baud rate list
                self.logger.log(logging.DEBUG, "[{}]: baudrate {}.".format(int(QThread.currentThreadId()),self.serialBaudRates[index]))
                
            except:
                self.logger.log(logging.DEBUG, "[{}]: no baudrate available.".format(int(QThread.currentThreadId())))

        @pyqtSlot(list, list)
        def on_newPortListReady(self, ports, portNames):
            """ Received new serial port list """
            self.logger.log(logging.DEBUG, "[{}]: port list received.".format(int(QThread.currentThreadId())))
            self.serialPorts = ports
            self.serialPortNames = portNames

        @pyqtSlot(tuple)
        def on_newBaudListReady(self, bauderates):
            """ Received new serial baud rate list """
            self.logger.log(logging.DEBUG, "[{}]: baud list received.".format(int(QThread.currentThreadId())))
            self.serialBaudRates = bauderates

        @pyqtSlot(list)     
        def on_textReceived(self, lines):
            """ Received text on serial port """
            self.logger.log(logging.DEBUG, "[{}]: text received.".format(int(QThread.currentThreadId())))
            for text in lines:
                self.logger.log(logging.INFO, "[{}]: {}".format(int(QThread.currentThreadId()),text))
                # print("{}".format(text))
    
# if __name__ == '__main__':
    
    from PyQt5.QtCore import QCoreApplication, QTimer
    import logging
 
    # set logging lelvel
    # CRITICAL  50
    # ERROR     40
    # WARNING   30
    # INFO      20
    # DEBUG     10
    # NOTSET     0

    logging.basicConfig(level=logging.INFO)
    
    import sys
    app = QCoreApplication.instance()
    if app is None:
        app  = QCoreApplication(sys.argv)
        
    task = MainTask()
    QTimer.singleShot(0, lambda: task.runTests.emit())
    sys.exit(app.exec())

    