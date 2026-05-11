import larpix
import larpix.io
# from base import utility_base
import larpix.format.rawhdf5format as rhdf5
import time
import larpix.format.pacman_msg_format as pacman_msg_fmt
import network_5x5
import pickle

from util import data, load_controller

def write_channel_mask(c, keys):
    for i in range(10):
        for key in reversed(keys):
            c.write_configuration(key, 'channel_mask')

def mask(c, keys):
    for i in range(10):
        for key in reversed(keys):
            c[key].config.channel_mask= [1]*64
            c.write_configuration(key, 'channel_mask')


def disable_periodic_reset(c, key):
    c[key].config.enable_periodic_reset=0
    c.write_configuration(key, 'enable_periodic_reset')

    ok, diff = c.enforce_configuration(key, n=3, n_verify=3, timeout=0.1)
    print(key, ' reset disabled:', ok)
    if not ok: print(diff)

def main():
    
    #load controller
    c=load_controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    
    c.io.reset_larpix(length=16)
    all_keys = c.chips.keys()

    mask(c, all_keys)

    for key in all_keys: 
        disable_periodic_reset(c, key)
    
    c = load_controller('controller_self_trigger.pkl')
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    
    write_channel_mask(c, all_keys)
    
    c.io.reset_larpix(length=16)
    c.io.reset_larpix(length=16)
    
    c.io.reset_larpix(length=16)
    data(c,240, tag='threshold-extraction')


if __name__ == '__main__':
    main()        
