import larpix
import larpix.io
# from base import utility_base
import h5py
import time
import numpy as np
import pickle
from tqdm import tqdm

from util import load_controller, save_controller


registers_to_write = {

    'periodic_reset_cycles' : 0
    
        }

def main():
    
    #load controller
    c=load_controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
  
    for chip in tqdm(c.chips):

        for register in registers_to_write.keys():
            setattr(c[chip].config, register, registers_to_write[register])
            for __ in range(3): c.write_configuration( chip, register )

        ok, diff = c.enforce_configuration( chip, n=3, n_verify=3, timeout=0.1  )
        print(chip, ok, diff)
    save_controller(c) 

    return c 

if __name__ == '__main__':
    c = main()        


