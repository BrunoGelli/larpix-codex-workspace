from matplotlib import pyplot as plt
import numpy as np
import h5py 
import yaml
import datetime
import os
import h5py
from tqdm import tqdm
import scipy.stats
import time
import pickle
import json
import larpix
import larpix.logger
_default_data_dir='data/'

N_CHIPS=100
N_CHANNELS=64
 
def chip_channel_to_index(chip, channel):
        return (chip-11)*N_CHANNELS + channel

def index_to_chip_channel(index):
    return (index//N_CHANNELS + 11), index % N_CHANNELS

def construct_geometry():
    # CONSTRUCT Geometry Information for Charge

    nonrouted_channels=[]
    routed_channels=[i for i in range(64) if i not in nonrouted_channels]

    geo=None
    geometrypath = 'layout-2.5.1.yaml'
    with open(geometrypath) as fi:
        geo=yaml.full_load(fi)

    chip_pix=dict([(chip_id, pix) for chip_id,pix in geo['chips']])

    all_uniques = np.zeros( N_CHIPS*N_CHANNELS )
    pixel_x     = np.zeros( N_CHIPS*N_CHANNELS )
    pixel_y     = np.zeros( N_CHIPS*N_CHANNELS )

    x_shift=-76.0
    y_shift= 76.0
    counter_used = set()
    for chip in range(11, 56):
        if chip % 10 > 5: continue
        for channel in range(64):
            pix=chip_pix[chip][channel]
            counter = chip_channel_to_index(chip, channel)
            if not pix is None:
                pixel_x[counter] = geo['pixels'][pix][1]-x_shift
                pixel_y[counter] = geo['pixels'][pix][2]-y_shift

    return pixel_x, pixel_y


def construct_pedestal(ped_file_name):
    ped_file=h5py.File(ped_file_name)
    ped_packs = ped_file['packets']
    ped_data = ped_packs[ped_packs['packet_type']==1]
    peds = np.zeros( N_CHIPS*N_CHANNELS )

    for chip in range(11, 56):
        if chip % 10 > 5: continue
        chip_mask = ped_data['chip_id']==chip
        for channel in range(64):
            counter = chip_channel_to_index(chip, channel)
            mask = np.logical_and(chip_mask, ped_data['channel_id'].astype(int)==channel)
            d=ped_data['dataword'][mask].astype(int)
            peds[counter] = scipy.stats.trim_mean(d[d>0], 0.05)

    return peds


def extract_thresholds(threshold_file_name, pedestal_file_name):
    thresholds = construct_pedestal(threshold_file_name)
    peds = construct_pedestal(pedestal_file_name)
    return thresholds-peds

def now():
    return time.strftime("%Y_%m_%d_%H_%M_%S_%Z")

def data(c, runtime, io_group, data_dir=_default_data_dir, fname=None, tag=None):
    if True:
        if fname is None: 
            if not tag is None:
                fname=data_dir+'/{}-packet-'.format(tag)+now()+'.h5'
            else:

                fname=data_dir+'/packet-'+now()+'.h5'

        c.logger = larpix.logger.HDF5Logger(filename=fname)
        print('filename: ',c.logger.filename)
        c.reads.clear() 
        # request internal reset of asics for the provided tile mask
        c.io.set_reg(0x00100410, 0x3ff, io_group) 
        c.logger.enable()
        c.run(runtime,' collecting data')
        c.logger.flush()
        c.logger.disable()
    return fname


def load_controller(name='controller.pkl'):
    c=None
    with open(name, 'rb') as f:
        c = pickle.load(f)
    return c

def save_controller(c, name='controller.pkl'):
    with open(name, 'wb') as f:
        c.io = None
        c.reads.clear()
        c.logger = None
        pickle.dump(c, f, pickle.HIGHEST_PROTOCOL)
    return

def save_json(d, filename):
    with open(filename, 'wb') as f:
        json.dump(d, f, indent=4)
    return

def load_json(filename):
    d={}
    with open(filename, 'rb') as f:
        d=json.load(f)
    return d


