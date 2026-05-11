import larpix
import larpix.io
# from base import utility_base
import h5py
import time
import numpy as np
import pickle
from tqdm import tqdm
import util
from util import load_controller, save_controller, data

ped_file_name='/data/v3/5x5/may_2025/packets-2025_05_30_13_55_PDT_46.h5'
data_dir = 'data/data_0529/'



def disable_periodic_reset(c, key):
    c[key].config.enable_periodic_reset=0
    c.write_configuration(key, 'enable_periodic_reset')

    periodic_reset_reg = 128
    pixel_trim_reg = range(0, 64)
    ok, diff = c.enforce_registers([ (key, periodic_reset_reg), (key, pixel_trim_reg)], n=5, n_verify=3, timeout=0.1)
    print(key, ' reset disabled:', ok)
    if not ok: print(diff)

def enable_periodic_reset(c, key):
    c[key].config.enable_periodic_reset=1
    c.write_configuration(key, 'enable_periodic_reset')

    periodic_reset_reg = 128
    ok, diff = c.enforce_registers([ (key, periodic_reset_reg)], n=5, n_verify=3, timeout=0.1)
    print(key, ' reset enabled:', ok)
    if not ok: print(diff)

def main():
    
    #load controller
    c=util.load_controller('controller_self_trigger.pkl')
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
  
    runtime=60


    for chip in c.chips: disable_periodic_reset(c, chip)
    
    fname=data(c,runtime)
   
    for chip in c.chips: enable_periodic_reset(c, chip)

    return c 

if __name__ == '__main__':
    c = main()        


