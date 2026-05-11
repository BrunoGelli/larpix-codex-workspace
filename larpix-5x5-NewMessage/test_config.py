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
from random import randint

def main(save_progress):
    
    #load controller
    c=load_controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)

            #   io_group - io_channel - 
    chip_to_test = '1-5-12'
    total_good=0

    for __ in range(100):
        test_value = randint(0,255)
        c[chip_to_test].config.threshold_global = test_value
        c.write_configuration( chip_to_test, 'threshold_global' )
        c.read_configuration( chip_to_test, 'threshold_global', timeout=0.005 )
        print('setting value:', test_value)
        read_value=None
        for p in c.reads[-1]:
            if p.packet_type==3:
                if p.register_data==test_value: total_good+=1

    print(total_good)

    return c 

if __name__ == '__main__':
        parser = argparse.ArgumentParser()
        parser.add_argument('--save_progress', default=False, action='store_true', help='''Save all intermediate threshold steps''')
        args = parser.parse_args()
        main(**vars(args))

