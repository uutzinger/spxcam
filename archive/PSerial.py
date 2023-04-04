################################################################################
# Serial Helper Class
################################################################################
# Open, close port
# Change baudrate
# Background thread to send and receive data
# Queue to transmit and receive data from threads
# QObject and QThread to ingrated into QT application
#
# Urs Utzinger, Devesh Koshla
# University of Arizona 2022
################################################################################
# July 2022: Initial Release
################################################################################

from serial import Serial as sp
from serial import EIGHTBITS, PARITY_NONE, STOPBITS_ONE
from serial.tools import list_ports 
import time

################################################################################
# Serial Class with python thread and queues
################################################################################

# Multi Threading
from threading import Thread
from queue import Queue

# Logging
import logging

class PSerial(Thread):
    """
    Serial Wrapper.
    Without these the function Serial.in_waiting does not seem to work.
    """
    
    def __init__(self, queue_size: int = 0):
        self.ser = None
        self.logger = logging.getLogger("PSerial")           
        self._port = ""
        self._baud = -1
        self.ser_open = False
        
        if queue_size != 0:
            self.rx = Queue(maxsize=queue_size)
            self.tx = Queue(maxsize=queue_size)
            self.stopped  = True
            _ = self.scanPorts()
            Thread.__init__(self)
    
    # Thread Functions
    # only active if thread is used and queue is given
    ############################################################################
    def stop(self):
        """stop the thread"""
        self.stopped = True
        self.close()

    def start(self):
        """start the thread"""
        if self.ser_open: 
            self.stopped = False
            T_rx = Thread(target=self.update_receive)
            T_rx.daemon = True # run in background
            T_rx.start() 
            T_tx = Thread(target=self.update_transmit)
            T_tx.daemon = True # run in background
            T_tx.start() 
        else:
            self.stopped = True
            self.logger.log(logging.ERROR, "[SER]: can not start read/write thread, port is no open!")

    # This runs continously after start
    def update_receive(self):
        """update the serial receiving thread"""
        while not self.stopped:
            if self.ser_open:
                line = self.ser.readline().decode().rstrip('\r\n') # is blocking
                if len(line) > 0: 
                    if (not self.rx.full()): self.rx.put_nowait(line)
                    else: self.logger.log(logging.WARNING, "[SER]: Rx bufer is full!")
            else: time.sleep(1) # wait for port to open
                
    def update_transmit(self):
        """update the serial transmission thread"""
        while not self.stopped:
            if self.ser_open:
                text = self.tx.get(block=True, timeout=None) # is blocking
                self.ser.write(text.encode())
            else: time.sleep(1) # wait for port to open

    # Helper functions
    ############################################################################

    def scanports(self):
        """ scans for all available ports """
        self._ports = [
            [p.device, p.description]
            for p in list_ports.comports()
        ]
        return len(self._ports)

    def open(self, port, baud):
        """ opens specified port """
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
        """ closes serial port """
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
        """ switch to diffferent port """
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
    
    # Make internal variable port, baudrate, current port and current baudrate accessible
    ############################################################################
        
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

if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    ser = PSerial(queue_size=128)                                                   # Create serial helper object
    print(ser.ports)
    if len(ser.ports) > 0:
        ser.open(ser.ports[0][0], baud=115200)                                      # Open the ports
        #  Test direct serial port access ----------------------------------
        ser.write("?\r\n")
        print('Send status request')
        time.sleep(1)
        while ser.avail() > 0:
            line = ser.readline()                                                   # obtain all responses
            print(line)                                                             # display responses        
        #  Test python threaded serial port with Queue ----------------------
        ser.start()                                                                 # Start background threads
        if ser.tx.empty() and ser.rx.empty():
            ser.tx.put_nowait("?\r\n")
            print('Send status request')
        time.sleep(1)
        while not ser.rx.empty():
            line = ser.rx.get(block=True, timeout=None)                             # obtain all responses
            print(line)                                                             # display responses

        #  Test continous python threaded serial port with Queue ------------
        stop = False
        last_txtime = time.time()
        while (not stop):
            current_time = time.time()
            if (current_time - last_txtime) > 2:
                if ser.tx.empty() and ser.rx.empty():
                    ser.tx.put_nowait(".\r\n")
                    print('Send status request')
                last_txtime = current_time
            time.sleep(1)
            while not ser.rx.empty():
                line = ser.rx.get(block=True, timeout=None)                         # obtain all responses
                print(line)                                                         # display responses
                
    ser.stop()                                                                      # something went wrong

