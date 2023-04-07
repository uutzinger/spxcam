# Matrix Algebra
import numpy as np
from   numba import vectorize, jit, prange
import cv2
import math
import time
import logging

from PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, QSignalMapper
from PyQt5.QtWidgets import QLineEdit, QSlider, QCheckBox, QLabel

numChannels =  13

class QDisplayUI(QObject):
    def __init__(self, parent=None, ui=None):
        super(QDisplayUI, self).__init__(parent)

        self.ui = ui
        self.displayImage = np.zeros((height,width,3), dtype = np.uint8)
       
    def on_changeDisplayedChannels(self):
        """  """        
        # create index of channels in data cube that will be displayed
        self.indx = []
        self.name = []       
        if self.ui.checkBox_DisplayBackground.isChecked(): 
            self.indx.append(0)
            self.name.append("Background")
            
        _tmp=0      
        for channel in range(numChannels):            
            checkBoxA = self.ui.findChild( QCheckBox, "checkBox_MeasureChannel"+str(channel+1))
            checkBoxB = self.ui.findChild( QCheckBox, "checkBox_DisplayChannel"+str(channel+1))
            if checkBoxA.isChecked(): 
                _tmp += 1
                if checkBoxB.isChecked(): 
                    self.indx.append(_tmp)
                    self.name.append(checkBoxA.text())

    
            
