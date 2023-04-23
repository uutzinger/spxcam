# Matrix Algebra
import numpy as np
from   numba import vectorize, jit, prange
import cv2
import math
import time
import logging

from PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, QSignalMapper
from PyQt5.QtWidgets import QLineEdit, QSlider, QCheckBox, QLabel

class QProcessWorker(QObject):
    """ 
    Process Worker Class

    Signals      
        = For processWorker
        NEED TO DEVELOP
    Slots
      on_changeBinning
      on_processRequest
      
    """

    @pyqtSlot(list)
    def on_changeBinning(self, binning):
       self

    
class QDataCube():
    """ 
    Data Cube Class
      initialize  create datacube
      add(image)  add image to stack, when full emit signal and start at beginning again
      sort()      sort so that lowest intensity is first image in stack
      bgflat()    subtract background, multiply flatfield
      bin2        binning 2x2 (explicit code is faster than general binning with slicing and summing in numpy)
      bin3        binning 3x3
      bin4        binning 4x4
      bin5        binning 5x5
      bin6        binning 6x6
      bin9        binning 9x9
      bin10       binning 10x10
      bin12       binning 12x12
      bin15       binning 15x15
      bin18       binning 18x18
      bin20       binning 20x20

    Signals  
        dataCubeReady    
        = For processWorker
        NEED TO DEVELOP
    Slots
      on_changeBinning
    """

    dataCubeReady = pyqtSignal(np.ndarray)                                          # we have a complete datacube
    
    def __init__(self, parent=None, width=720, height=540, depth=14, flatfield = None):
        super(QDataCube, self).__init__()

        self.logger = logging.getLogger("QDataC_")           
        
        # Variables
        ###########
        self.width     = width
        self.height    = height
        self.depth     = depth
        self.data      = np.zeros((depth, height, width), 'uint8')                   # allocate space for the data cube images
        self.bg        = np.zeros((height, width), 'uint8')                          # allocate space for background image
        self.flat      = 256*np.ones((depth, height, width), 'uint16')               # flatfield correction image, scaled so that 255=100%
        self.inten     = np.zeros(depth, 'uint16')                                   # average intentisy in each image of the stack
        self.data_indx = 0                                                           # current location to fill the data cube with new image

        if flatfield is None:
            self.logger.log(logging.ERROR, "Status:Need to provide flatfield!")
            return None
        else: 
            self.ff = flatfield

    # need functions to collect images into data cube and sort it
    def add(self, image):
        self.data[self.data_indx,:,:] = image
        self.data_indx += 1
        if self.data_indx >= self.depth:
            self.dataCubeReady.emit(self.data)
            self.data_indx = 0

    def sort(self, delta: tuple = (64,64)):
        """ Sorts data cube so that first image is the one with lowest intensity (background) """
        # create intensity reading for each image in the stack
        bg_dx = delta[1]                                    # take intensity values at delta x intervals
        bg_dy = delta[0]                                    # take intensity values at delta y intervals
        (depth, width, height) = self.data.shape  
        self.inten = np.sum(self.data[:,::bg_dx,::bg_dy], axis=(1,2)) # intensities at selected points in image
        # create sorting index        
        background_indx = np.argmin(self.inten)             # lowest itensity
        indx  = np.arange(0, depth)                         # 0..depth-1
        indx  = indx + background_indx + 1                  # index shifted
        indx  = indx%depth                                  # now bg is at first location in indx
        # data sorted
        self.data = self.data[indx,:,:]                     # rearrange data cube
    
    def cube2DisplayImage(self, displayImage, indx=[0], name=[]):
        """ 
        Flattens the data cube to a display image.
        If 3 channels are selected, this requires 2x2 tile. 
        It will add channel label to the image tiles. 
        indx is selected channels
        name is the channel names with same length as indx
        """
        
        font             = cv2.FONT_HERSHEY_SIMPLEX
        fontScale        = 1
        lineType         = 2
        
        (depth,height,width) = self.data.shape
        # if len(indx) == depth:
        # maybe faster option if all images are selected
        # 
        
        # arrange selected images in a grid
        columns = math.ceil(math.sqrt(len(indx))) # how many columns are needed?
        rows   = math.ceil(len(indx)/columns)     # how many rows are needed?
        empty  = np.zeros((height,width), dtype=_htmp.dtype)
        i = 0
        for y in range(rows):
            _htmp = self.data[indx[i],:,:]
            for x in range(columns-1):
                if i < len(indx):
                    _htmp=cv2.hconcat((_htmp,self.data[indx[i+1],:,:]))
                else:
                    _htmp=cv2.hconcat((_htmp,empty))
                i +=1
            if y == 0:
                _vtmp = _htmp
            else:
                _vtmp=cv2.vconcat((_vtmp,_htmp))

        # resize grid of images to fit into display image
        (height, width) = _vtmp.shape[:2]
        (newHeight, newWidth) = displayImage.shape[:2]
        scale = max(height/newHeight, width/newWidth)
        dsize = (int(width // scale), int(height // scale))
        img = cv2.resize(_vtmp, dsize, cv2.INTER_LINEAR)
        (height, width) = img.shape[:2]
        # copy grid image into display image: display image has 3 channels        
        displayImage[0:height,0:width,0] = img
        displayImage[0:height,0:width,1] = img
        displayImage[0:height,0:width,2] = img
        if len(name) > 0:
            # add text to the individual images
            x = y = 0
            dx = width / columns
            dy = height / rows
            for i in indx:
                (Label_width, Label_height), BaseLine = cv2.getTextSize(name[i], fontFace=font, fontScale=fontScale, thickness=lineType)
                h = Label_height + BaseLine
                loc_x = int(x * dx)
                loc_y = int(y * dy + h)
                cv2.rectangle(displayImage,
                    (loc_x, loc_y),
                    (loc_x + Label_width, loc_y + h),
                    (255,255,255), -1, )
                cv2.putText(displayImage, 
                    text=name[i], 
                    org=(loc_x, loc_y), 
                    fontFace=font, 
                    fontScale=fontScale, 
                    color=(0,0,0), 
                    thickness=lineType)
                # update location
                x += 1
                if x >= columns-1: 
                    x=0
                    y+=1

                
    # Faltfield Correction and Background removal
    #            result stack  bg     ff
    @vectorize(['uint16(uint8, uint8, uint16)'], nopython=True, fastmath=True, cache=True)
    def bgflat8(data_cube, background, flatfield):
        """Background removal, flat field correction, white balance """
        return np.multiply(np.subtract(data_cube, background), flatfield) # 8bit subtraction, 16bit multiplication

    # Faltfield Correction and Background removal
    #            result stack  bg     ff
    @vectorize(['uint32(uint16, uint16, uint16)'], nopython=True, fastmath=True, cache=True)
    def bgflat16(data_cube, background, flatfield):
        """Background removal, flat field correction, white balance """
        return np.multiply(np.subtract(data_cube, background), flatfield) # 8bit subtraction, 16bit multiplication

    # General purpose binning, this is 3 times slower compared to the routines below
    # @jit(nopython=True, fastmath=True, cache=True)
    # def rebin(arr, bin_x, bin_y, dtype=np.uint16):
    #     # https://stackoverflow.com/questions/36063658/how-to-bin-a-2d-array-in-numpy
    #     m,n,o = np.shape(arr)
    #     shape = (m//bin_x, bin_x, n//bin_y, bin_y, o)
    #     arr_ = arr.astype(dtype)
    #     return arr_.reshape(shape).sum(3).sum(1)

    # Binning 2 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin2(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//2,n,o), dtype='uint16')
        arr_out = np.empty((m//2,n//2,o), dtype='uint16')
        for i in prange(m//2):
            arr_tmp[i,:,:] =  arr_in[i*2,:,:] +  arr_in[i*2+1,:,:]
        for j in prange(n//2):
            arr_out[:,j,:] = arr_tmp[:,j*2,:] + arr_tmp[:,j*2+1,:] 
        return arr_out

    # Binning 3 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin3(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//3,n,o), dtype='uint16')
        arr_out = np.empty((m//3,n//3,o), dtype='uint16')
        for i in prange(m//3):
            arr_tmp[i,:,:] =  arr_in[i*3,:,:] +  arr_in[i*3+1,:,:] +  arr_in[i*3+2,:,:] 
        for j in prange(n//3):
            arr_out[:,j,:] = arr_tmp[:,j*3,:] + arr_tmp[:,j*3+1,:] + arr_tmp[:,j*3+2,:] 
        return arr_out

    # Binning 4 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin4(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//4,n,o), dtype='uint16')
        arr_out = np.empty((m//4,n//4,o), dtype='uint16')
        for i in prange(m//4):
            arr_tmp[i,:,:] =  arr_in[i*4,:,:] +  arr_in[i*4+1,:,:] +  arr_in[i*4+2,:,:] +  arr_in[i*4+3,:,:]
        for j in prange(n//4):
            arr_out[:,j,:] = arr_tmp[:,j*4,:] + arr_tmp[:,j*4+1,:] + arr_tmp[:,j*4+2,:] + arr_tmp[:,j*4+3,:]
        return arr_out

    # Binning 5 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin5(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//5,n,o), dtype='uint16')
        arr_out = np.empty((m//5,n//5,o), dtype='uint16')
        for i in prange(m//5):
            arr_tmp[i,:,:] =  arr_in[i*5,:,:] +  arr_in[i*5+1,:,:] +  arr_in[i*5+2,:,:] +  arr_in[i*5+3,:,:] +  arr_in[i*5+4,:,:]
        for j in prange(n//5):
            arr_out[:,j,:] = arr_tmp[:,j*5,:] + arr_tmp[:,j*5+1,:] + arr_tmp[:,j*5+2,:] + arr_tmp[:,j*5+3,:] + arr_tmp[:,j*5+4,:] 
        return arr_out

    # Binning 6 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin6(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//6,n,o), dtype='uint16')
        arr_out = np.empty((m//6,n//6,o), dtype='uint16')
        for i in prange(m//6):
            arr_tmp[i,:,:] =  arr_in[i*6,:,:] +  arr_in[i*6+1,:,:] +  arr_in[i*6+2,:,:] +  arr_in[i*6+3,:,:] +  arr_in[i*6+4,:,:]  \
                           +  arr_in[i*6+5,:,:]
        for j in prange(n//6):
            arr_out[:,j,:] = arr_tmp[:,j*6,:] + arr_tmp[:,j*6+1,:] + arr_tmp[:,j*6+2,:] + arr_tmp[:,j*6+3,:] + arr_tmp[:,j*6+4,:] \
                           + arr_tmp[:,j*6+5,:]  
        return arr_out

    # Binning 9 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin9(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//9,n,o), dtype='uint16')
        arr_out = np.empty((m//9,n//9,o), dtype='uint16')
        for i in prange(m//9):
            arr_tmp[i,:,:] =  arr_in[i*9,:,:]   + arr_in[i*9+1,:,:]  + arr_in[i*9+2,:,:]  + arr_in[i*9+3,:,:]  +  arr_in[i*9+4,:,:] \
                           +  arr_in[i*9+5,:,:] + arr_in[i*9+6,:,:]  + arr_in[i*9+7,:,:]  + arr_in[i*9+8,:,:] 
        for j in prange(n//9):
            arr_out[:,j,:] = arr_tmp[:,j*9,:]   + arr_tmp[:,j*9+1,:] + arr_tmp[:,j*9+2,:] + arr_tmp[:,j*9+3,:] + arr_tmp[:,j*9+4,:] \
                           + arr_tmp[:,j*9+5,:] + arr_tmp[:,j*9+6,:] + arr_tmp[:,j*9+7,:] + arr_tmp[:,j*9+8,:]
        return arr_out

    # Binning 10 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin10(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//10,n,o), dtype='uint16')
        arr_out = np.empty((m//10,n//10,o), dtype='uint16')
        for i in prange(m//10):
            arr_tmp[i,:,:] =  arr_in[i*10,:,:]   + arr_in[i*10+1,:,:] +  arr_in[i*10+2,:,:] +  arr_in[i*10+3,:,:] +  arr_in[i*10+4,:,:] \
                            + arr_in[i*10+5,:,:] + arr_in[i*10+6,:,:] +  arr_in[i*10+7,:,:] +  arr_in[i*10+8,:,:] +  arr_in[i*10+9,:,:]

        for j in prange(n//10):
            arr_out[:,j,:] = arr_tmp[:,j*10,:]   + arr_tmp[:,j*10+1,:] + arr_tmp[:,j*10+2,:] + arr_tmp[:,j*10+3,:] + arr_tmp[:,j*10+4,:] \
                           + arr_tmp[:,j*10+5,:] + arr_tmp[:,j*10+6,:] + arr_tmp[:,j*10+7,:] + arr_tmp[:,j*10+8,:] + arr_tmp[:,j*10+9,:]
        return arr_out

    # Binning 12 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin12(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//12,n,o), dtype='uint16')
        arr_out = np.empty((m//12,n//12,o), dtype='uint32')
        for i in prange(m//12):
            arr_tmp[i,:,:] =  arr_in[i*12,:,:]    + arr_in[i*12+1,:,:]  + arr_in[i*12+2,:,:]  + arr_in[i*12+3,:,:]  + arr_in[i*12+4,:,:]  \
                            + arr_in[i*12+5,:,:]  + arr_in[i*12+6,:,:]  + arr_in[i*12+7,:,:]  + arr_in[i*12+8,:,:]  + arr_in[i*12+9,:,:]  \
                            + arr_in[i*12+10,:,:] + arr_in[i*12+11,:,:] 

        for j in prange(n//12):
            arr_out[:,j,:]  = arr_tmp[:,j*12,:]    + arr_tmp[:,j*12+1,:]  + arr_tmp[:,j*12+2,:] + arr_tmp[:,j*12+3,:] + arr_tmp[:,j*12+4,:] \
                            + arr_tmp[:,j*12+5,:]  + arr_tmp[:,j*12+6,:]  + arr_tmp[:,j*12+7,:] + arr_tmp[:,j*12+8,:] + arr_tmp[:,j*12+9,:] \
                            + arr_tmp[:,j*12+10,:] + arr_tmp[:,j*12+11,:] 
        return arr_out

    # Binning 15 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin15(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//15,n,o), dtype='uint16')
        arr_out = np.empty((m//15,n//15,o), dtype='uint32')
        for i in prange(m//15):
            arr_tmp[i,:,:] =  arr_in[i*15,:,:]    + arr_in[i*15+1,:,:]  + arr_in[i*15+2,:,:]  + arr_in[i*15+3,:,:]  + arr_in[i*15+4,:,:]  \
                            + arr_in[i*15+5,:,:]  + arr_in[i*15+6,:,:]  + arr_in[i*15+7,:,:]  + arr_in[i*15+8,:,:]  + arr_in[i*15+9,:,:]  \
                            + arr_in[i*15+10,:,:] + arr_in[i*15+11,:,:] + arr_in[i*15+12,:,:] + arr_in[i*15+13,:,:] + arr_in[i*15+14,:,:] 

        for j in prange(n//15):
            arr_out[:,j,:]  = arr_tmp[:,j*15,:]    + arr_tmp[:,j*15+1,:]  + arr_tmp[:,j*15+2,:]  + arr_tmp[:,j*15+3,:]  + arr_tmp[:,j*15+4,:]  \
                            + arr_tmp[:,j*15+5,:]  + arr_tmp[:,j*15+6,:]  + arr_tmp[:,j*15+7,:]  + arr_tmp[:,j*15+8,:]  + arr_tmp[:,j*15+9,:]  \
                            + arr_tmp[:,j*15+10,:] + arr_tmp[:,j*15+11,:] + arr_tmp[:,j*15+12,:] + arr_tmp[:,j*15+13,:] + arr_tmp[:,j*15+14,:]
        return arr_out

    # Binning 18 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin18(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//18,n,o), dtype='uint16')
        arr_out = np.empty((m//18,n//18,o), dtype='uint32')
        for i in prange(m//18):
            arr_tmp[i,:,:] =  arr_in[i*18,:,:]    + arr_in[i*18+1,:,:]  + arr_in[i*18+2,:,:]  + arr_in[i*18+3,:,:]  + arr_in[i*18+4,:,:]  \
                            + arr_in[i*18+5,:,:]  + arr_in[i*18+6,:,:]  + arr_in[i*18+7,:,:]  + arr_in[i*18+8,:,:]  + arr_in[i*18+9,:,:]  \
                            + arr_in[i*18+10,:,:] + arr_in[i*18+11,:,:] + arr_in[i*18+12,:,:] + arr_in[i*18+13,:,:] + arr_in[i*18+14,:,:] \
                            + arr_in[i*18+15,:,:] + arr_in[i*18+16,:,:] + arr_in[i*18+17,:,:] 

        for j in prange(n//18):
            arr_out[:,j,:]  = arr_tmp[:,j*18,:]    + arr_tmp[:,j*18+1,:]  + arr_tmp[:,j*18+2,:]  + arr_tmp[:,j*18+3,:]  + arr_tmp[:,j*18+4,:]  \
                            + arr_tmp[:,j*18+5,:]  + arr_tmp[:,j*18+6,:]  + arr_tmp[:,j*18+7,:]  + arr_tmp[:,j*18+8,:]  + arr_tmp[:,j*18+9,:]  \
                            + arr_tmp[:,j*18+10,:] + arr_tmp[:,j*18+11,:] + arr_tmp[:,j*18+12,:] + arr_tmp[:,j*18+13,:] + arr_tmp[:,j*18+14,:] \
                            + arr_tmp[:,j*18+15,:] + arr_tmp[:,j*18+16,:] + arr_tmp[:,j*18+17,:]  
        return arr_out

    # Binning 20 pixels of the 8bit images
    @jit(nopython=True, fastmath=True, parallel=True, cache=True)
    def bin20(arr_in):
        m,n,o   = np.shape(arr_in)
        arr_tmp = np.empty((m//20,n,o), dtype='uint16')
        arr_out = np.empty((m//20,n//20,o), dtype='uint32')
        for i in prange(m//20):
            arr_tmp[i,:,:] =  arr_in[i*20,:,:]  + arr_in[i*20+1,:,:]  + arr_in[i*20+2,:,:]  + arr_in[i*20+3,:,:]  + arr_in[i*20+4,:,:]  + arr_in[i*20+5,:,:]  + \
                            arr_in[i*20+6,:,:]  + arr_in[i*20+7,:,:]  + arr_in[i*20+8,:,:]  + arr_in[i*20+9,:,:]  + arr_in[i*20+10,:,:] + arr_in[i*20+11,:,:] + \
                            arr_in[i*20+12,:,:] + arr_in[i*20+13,:,:] + arr_in[i*20+14,:,:] + arr_in[i*20+15,:,:] + arr_in[i*20+16,:,:] + arr_in[i*20+17,:,:] + \
                            arr_in[i*20+18,:,:] + arr_in[i*20+19,:,:]

        for j in prange(n//20):
            arr_out[:,j,:]  = arr_tmp[:,j*20,:]  + arr_tmp[:,j*20+1,:]  + arr_tmp[:,j*20+2,:]  + arr_tmp[:,j*20+3,:]  + arr_tmp[:,j*10+4,:]  + arr_tmp[:,j*20+5,:]  + \
                            arr_tmp[:,j*20+6,:]  + arr_tmp[:,j*20+7,:]  + arr_tmp[:,j*20+8,:]  + arr_tmp[:,j*20+9,:]  + arr_tmp[:,j*20+10,:] + arr_tmp[:,j*20+11,:] + \
                            arr_tmp[:,j*20+12,:] + arr_tmp[:,j*20+13,:] + arr_tmp[:,j*10+14,:] + arr_tmp[:,j*20+15,:] + arr_tmp[:,j*20+16,:] + arr_tmp[:,j*20+17,:] + \
                            arr_tmp[:,j*20+18,:] + arr_tmp[:,j*20+19,:] 
        return arr_out


class QDataDisplay(QObject):

    # Transform band passed data to display image
    # Goal is to enhace small changes and to convert data to 0..1 range
    # A few example options:
    # data = np.sqrt(np.multiply(data,abs(data_bandpass)))
    # data = np.sqrt(255.*np.absolute(data_highpass)).astype('uint8')
    # data = (128.-data_highpass).astype('uint8')
    # data = np.left_shift(np.sqrt((np.multiply(data_lowpass,np.absolute(data_highpass)))).astype('uint8'),2)
    @vectorize(['float32(float32)'], nopython=True, fastmath=True, cache=True)
    def displaytrans(data_bandpass):
        return np.sqrt(16.*np.abs(data_bandpass))

    def resizeimg(img, newWidth, newHeight, pad = False, mode = cv2.BORDER_CONSTANT):
        """
        Scale & pad image, image will not change aspect ratio
        input image, width and height
        if padding enabled new image will become requested size
        if padding disabled one dimension of new image might be smaller than requested
        padding mode: cv2.BORDER_CONSTANT uses 0/black to pad
        For padding, image is centered and padded top&bottom or left&right
        This function allocates new image.
        """
        # origin: UU
        
        # We can  also place img on top left corner and pad with black pixels on the right and bottom of the image
        #   return np.pad(img_r, ((t, b), (l, r), (0,0)), mode=mode), factor    
        #   return np.pad(img_r, ((0, diff_y), (0, diff_x), (0,0)), mode=mode), factor 
        #   copyMakeBorder seems to be faster
        
        (height, width) = img.shape[:2]
        
        # Stretch factor, stretch the same in horizontal and vertial to maintain aspect ratio, if requested pad image
        factor = min(newWidth  / width, newHeight / height) # smaller size resize
        dsize = (int(width * factor), int(height * factor)) # destination size, might be smaller than the requested new size horizontal or vertical
        img_r = cv2.resize(img, dsize, cv2.INTER_LINEAR)
        
        if pad:
            diff_x = newWidth  - img_r.shape[1]
            diff_y = newHeight - img_r.shape[0]
            # center the image and pad
            l = diff_x // 2
            t = diff_y // 2
            r = diff_x - l
            b = diff_y - t
            if img_r.ndim == 3:
                size = (img_r.shape[0]+t+b, img_r.shape[1]+l+r, img_r.shape[2])
            elif img_r.ndim == 2:
                size = (img_r.shape[0]+t+b, img_r.shape[1]+l+r)
            else:
                return None, None, None, None
            img_out = np.empty(size,dtype=img.dtype)
            cv2.copyMakeBorder(dst=img_out, src=img_r, top=t, bottom=b, left=l, right=r, borderType=mode, value=0)
            return img_out, factor, l, t
        else:
            l=t=0
            return img_r, factor, l, t

class threeBandEqualizerProcessor():
    """3 Band Equalizer"""

    # Initialize the Processor Thread
    def __init__(self, res: tuple, gain_low: float, gain_mid: float, gain_high: float, fc_low: float, fc_high: float, fs: float):

        self.fs = fs
        self.fcl = fc_low
        self.fch = fc_high
     
             # Gain Controls
        self.lg   = gain_low     # low  gain
        self.mg   = gain_mid     # mid  gain
        self.hg   = gain_high    # high gain
           
        # Filter #1 (Low band)   
        self.f1p0 = np.zeros(res, 'float32')   # Poles ...
        self.f1p1 = np.zeros(res, 'float32')
        self.f1p2 = np.zeros(res, 'float32')
        self.f1p3 = np.zeros(res, 'float32')

        # Filter #2 (High band)
        self.f2p0 = np.zeros(res, 'float32')   # Poles ...
        self.f2p1 = np.zeros(res, 'float32')
        self.f2p2 = np.zeros(res, 'float32')
        self.f2p3 = np.zeros(res, 'float32')

        # Sample history buffer
        self.sdm1 = np.zeros(res, 'float32')   # Sample data minus 1
        self.sdm2 = np.zeros(res, 'float32')   #                   2
        self.sdm3 = np.zeros(res, 'float32')   #                   3

        self.vsa = 1.0 / 4294967295.0          # Very small amount (Denormal Fix)

        self.lf = 2 * math.sin(math.pi * (self.fcl / self.fs))
        self.hf = 2 * math.sin(math.pi * (self.fch / self.fs))

        self.l = np.zeros(res, 'float32')      # low  frequency sample
        self.m = np.zeros(res, 'float32')      # mid  frequency sample
        self.h = np.zeros(res, 'float32')      # high frequency sample
  
    def equalize(self, data):
        """ three band equalizer """
       
        start_time = time.perf_counter()

        # Filter #1 (low pass)
        self.f1p0  += (self.lf * (data      - self.f1p0)) + self.vsa
        self.f1p1  += (self.lf * (self.f1p0 - self.f1p1))
        self.f1p2  += (self.lf * (self.f1p1 - self.f1p2))
        self.f1p3  += (self.lf * (self.f1p2 - self.f1p3))
        self.l      = self.f1p3

        # Filter #2 (high pass)
        self.f2p0  += (self.hf * (data      - self.f2p0)) + self.vsa
        self.f2p1  += (self.hf * (self.f2p0 - self.f2p1))
        self.f2p2  += (self.hf * (self.f2p1 - self.f2p2))
        self.f2p3  += (self.hf * (self.f2p2 - self.f2p3))
        self.h      = self.sdm3 - self.f2p3

        # Calculate midrange (signal - (low + high))
        self.m      = self.sdm3 - (self.h + self.l)
        
        # Scale, combine and return signal
        self.l     *= self.lg
        self.m     *= self.mg
        self.h     *= self.hg

        # Shuffle history buffer
        self.sdm3   = self.sdm2
        self.sdm2   = self.sdm1
        self.sdm1   = data

        total_time += time.perf_counter() - start_time

        return self.l + self.lm + self.lh

###############################################################################
# High Pass Image Processor
# Poor Man's
###############################################################################
# Construct poor man's low pass filter y = (1-alpha) * y + alpha * x
# https://dsp.stackexchange.com/questions/54086/single-pole-iir-low-pass-filter-which-is-the-correct-formula-for-the-decay-coe
# f_s sampling frequency in Hz
# f_c cut off frequency in Hz
# w_c radians 0..pi (pi is Niquist fs/2, 2pi is fs)
###############################################################################
# Urs Utzinger 2022

class poormansHighpassProcessor():
    """
    Highpass filter
    y = (1-alpha) * y + alpha * x
    """

    # Initialize 
    def __init__(self, res: tuple = (14,720,540), alpha: float = 0.95 ):

        # Initialize Processor
        self.alpha = alpha
        self.averageData  = np.zeros(res, 'float32')
        self.filteredData  = np.zeros(res, 'float32')

    # After Starting the Thread, this runs continuously
    def highpass(self, data):
        start_time = time.perf_counter()
        self.averageData  = self.movingavg(data, self.averageData, self.alpha)
        self.filteredData = self.highpass(data, self.averageData)
        total_time += time.perf_counter() - start_time
        return self.filteredData

    # Numpy Vectorized Image Processor
    # y = (1-alpha) * y + alpha * x
    @vectorize(['float32(uint16, float32, float32)'], nopython=True, fastmath=True)
    def movingavg(data, average, alpha):
        return np.add(np.multiply(average, 1.-alpha), np.multiply(data, alpha))

    @vectorize(['float32(uint16, float32)'], nopython=True, fastmath=True)
    def highpass(data, average):
        return np.subtract(data, average)

    def computeAlpha(f_s = 50.0, f_c = 5.0):
        w_c = (2.*3.141) * f_c / f_s         # normalized cut off frequency [radians]
        y = 1 - math.cos(w_c);               # compute alpha for 3dB attenuation at cut off frequency
        # y = w_c*w_c / 2.                   # small angle approximation
        return -y + math.sqrt( y*y + 2.*y ); # 


###############################################################################
# Highpass Filter
# Running Summ
#
# Moving Average (D-1 additions per sample)
# y(n) =  Sum(x(n-i))i=1..D * 1/D 
#
# Recursive Running Sum (one addition and one subtraction per sample)
# y(n) = [ x(n) - x(n-D) ] * 1/D + y(n-1)
#
# Cascade Integrator Comb Filter as Moving Average Filter
# y(n) = ( x(n) - x(n-D) ) + y(n-1)
#
# https://en.wikipedia.org/wiki/Cascaded_integrator-comb_filter
# https://dsp.stackexchange.com/questions/12757/a-better-high-order-low-pass-filter
# https://www.dsprelated.com/freebooks/sasp/Running_Sum_Lowpass_Filter.html
# https://www.dsprelated.com/showarticle/1337.php
###############################################################################
# Urs Utzinger 2022

class runningsumHighpassProcessor(QThread):
    """Highpass filter"""

    # Initialize the Processor Thread
    def __init__(self, res: tuple = (14, 720, 540), delay: int = 1 ):

        # Initialize Processor
        self.data_lowpass  = np.zeros(res, 'float32')
        self.data_highpass = np.zeros(res, 'float32')

        self.circular_buffer = self.collections.deque(maxlen=delay)
        # initialize buffer with zeros
        for i in range(delay):
            self.circular_buffer.append(self.data_lowpass)

    @vectorize(['uint8(uint8, uint8, uint8)'], nopython=True, fastmath=True)
    def runsum(data, data_delayed, data_previous):
        # Numpy Vectorized Image Processor
        # y(n) = ( x(n) - x(n-D) ) + y(n-1)
        # x(n), x(n-D) y(n-1)
        return np.add(np.subtract(data, data_delayed), data_previous)

    @vectorize(['uint8(uint8, uint8)'], nopython=True, fastmath=True)
    def highpass(data, data_filtered):
        return np.subtract(data, data_filtered)

    def highpass(self, data):
        start_time = time.perf_counter()
        xn = data                                     # x(n)
        xnd = self.circular_buffer.popleft()          # x(N-D)
        self.circular_buffer.append(data)             # put new data into delay line
        yn1 = self.data_lowpass                       # y(n-1)
        self.data_lowpass = self.runsum(xn, xnd, yn1)      # y(n) = x(n) - x(n-D) + y(n-1)
        self.data_hihgpass = self.highpass(data, self.data_lowpass)
        total_time += time.perf_counter() - start_time
