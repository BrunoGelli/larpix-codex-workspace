import larpix
import larpix.io
# from base import utility_base
import h5py
import time
import numpy as np
import pickle
from tqdm import tqdm
from util import data, load_controller, save_controller, save_json, load_json, now
import argparse

progress_dir='thresholding'
progress_file_name = progress_dir + '/iterations.json'
def main(save_progress):
    
    #load controller
    c=load_controller('controller_self_trigger.pkl')
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
  

    ########################################################

    toggle_up=0
    toggle_down=0
    disabled=0
    in_range=0

    rate_max=1
    rate_min=0.1
    runtime=10

    fname=data(c,runtime)

    f=h5py.File(fname)
    packets = f['packets'][:]
    packets = packets[ packets['packet_type']==1 ]
    
    for chip in tqdm(c.chips):
        
        chip_packets = packets[packets['chip_id']==chip.chip_id]
        for channel in range(64):
            if c[chip].config.channel_mask[channel]==1:
                continue
            else:
                rate = np.sum(chip_packets['channel_id']==channel)
                tdac=c[chip].config.pixel_trim_dac[channel]
                if rate/runtime < rate_min:
                    #tdac = tdac-1
                    toggle_down+=1
                elif rate/runtime > rate_max:
                    tdac = tdac+1
                    toggle_up+=1
                    if (rate/runtime)/rate_max > 100:
                        tdac = tdac+1

                    if (rate/runtime)/rate_max > 1000:
                        tdac = tdac+2
                else:
                    in_range+=1

                if tdac < 0: tdac = 0
                    
                if tdac > 31:
                    c[chip].config.channel_mask[channel]=1
                    disabled +=1
                    for __ in range(5):
                        c.write_configuration( chip, 'channel_mask'  )
                else:
                    c[chip].config.pixel_trim_dac[channel]=tdac
                    for __ in range(5):
                        c.write_configuration( chip, 'pixel_trim_dac'  )
                
        
        c.write_configuration(chip, 'threshold_global')
    print('in range channels:', in_range)  
    print('disabled:', disabled)
    print('toggled up:', toggle_up)
    print('toggled down:', toggle_down)
    save_controller(c) 

    if save_progress:
        _now = now()
        save_name = progress_dir + '/threshold_iteration-{}.pkl'.format(_now)
        save_controller(save_name)

        d = load_json(progress_file_name)

        d[_now] = {
                'controller' : save_name,
                'data_sample': fname
                }

        save_json(d, progress_file_name)

    return c 

if __name__ == '__main__':
        parser = argparse.ArgumentParser()
        parser.add_argument('--save_progress', default=False, action='store_true', help='''Save all intermediate threshold steps''')
        args = parser.parse_args()
        main(**vars(args))

