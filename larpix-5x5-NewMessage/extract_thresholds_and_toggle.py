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
  
    toggle_up=0
    toggle_down=0
    disabled=0
    in_range=0

    rate_max=1
    rate_min=0.1
    runtime=60


    for chip in c.chips: disable_periodic_reset(c, chip)
    
    fname=data(c,runtime)
    
    target_threshold = 4.0
    tol = 0.5
    lsb_per_tdac = 1.0

    thresholds = util.extract_thresholds( fname, ped_file_name )
    
    for chip in tqdm(c.chips):
        c.write_configuration(chip, 'enable_tally')
        for channel in range(64):
            if c[chip].config.channel_mask[channel]==1:
                continue
            else:
                index = util.chip_channel_to_index(chip.chip_id, channel)
                threshold = thresholds[index]
                tdac=c[chip].config.pixel_trim_dac[channel]
                if threshold > target_threshold+tol:
                    tdac = tdac-1
                    toggle_down+=1
                elif threshold < target_threshold-tol:
                    tdac = tdac+1
                    toggle_up+=1
                else:
                    in_range+=1

                if tdac < 0: tdac = 0
                    
                if tdac > 31:
                    tdac = 31
                c[chip].config.pixel_trim_dac[channel]=tdac
        for __ in range(5):
            c.write_configuration( chip, 'pixel_trim_dac'  )
                
    print('in range channels:', in_range)  
    print('toggled up:', toggle_up)
    print('toggled down:', toggle_down)
   
    for chip in c.chips: enable_periodic_reset(c, chip)
    save_controller(c, 'controller_self_trigger.pkl') 

    return c 

if __name__ == '__main__':
    c = main()        


