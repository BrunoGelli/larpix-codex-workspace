import larpix
import larpix.io
# from base import utility_base
import larpix.format.rawhdf5format as rhdf5
import time
import larpix.format.pacman_msg_format as pacman_msg_fmt
import network_5x5
import pickle
from util import data, save_controller, load_controller

def unmask(c, keys):
    for i in range(10):
        for key in reversed(keys):

            c[key].config.csa_enable= [1]*64
            c[key].config.channel_mask= [0]*64
            c[key].config.periodic_trigger_mask=[0]*64
            c.write_configuration(key, 'periodic_trigger_mask')
            c.write_configuration(key, 'csa_enable')
            c.write_configuration(key, 'channel_mask')


def enable_pedestal(c, key, vref_dac=255):

    c[key].config.enable_external_sync=1
    c.write_configuration(key, 'enable_external_sync')
    c[key].config.mark_first_packet = 0
    c.write_configuration(key, 'mark_first_packet')
    c[key].config.enable_periodic_trigger=1
    c[key].config.enable_rolling_periodic_trigger=1
    c[key].config.enable_periodic_reset=1
    c[key].config.enable_rolling_periodic_reset=1
    c[key].config.enable_hit_veto=1
    c[key].config.enable_periodic_trigger_veto=0

    c[key].config.threshold_global = 50 #255
    c[key].config.periodic_trigger_cycles = 578121
    c[key].config.periodic_reset_cycles = 4

    c[key].config.cds_mode=0
    c[key].config.enable_data_stats=0
    c[key].config.vref_dac=vref_dac

    c[key].config.ibias_vcm_buffer = 15
    c.write_configuration(key, 'ibias_vcm_buffer')

    c[key].config.adc_comp_trim = 2
    c.write_configuration(key, 'adc_comp_trim')

    c[key].config.adc_ibias_delay = 15
    c.write_configuration(key, 'adc_ibias_delay')

    c.write_configuration(key, 'vref_dac')

    c.write_configuration(key, 'enable_data_stats')
    c.write_configuration(key, 'enable_periodic_trigger')
    c.write_configuration(key, 'cds_mode')
    c.write_configuration(key, 'enable_rolling_periodic_trigger')
    c.write_configuration(key, 'enable_periodic_reset')
    c.write_configuration(key, 'enable_rolling_periodic_reset')
    c.write_configuration(key, 'enable_hit_veto')
    c.write_configuration(key, 'enable_periodic_trigger_veto')
    c.write_configuration(key, 'threshold_global')
    c.write_configuration(key, 'periodic_trigger_cycles')
    c.write_configuration(key, 'periodic_reset_cycles')

    ok, diff = c.enforce_configuration(key, n=3, n_verify=3, timeout=0.1)
    print(key, ' pedestal enabled:', ok)
    if not ok: print(diff)
    #c[key].config.chip_id=11
    #c.write_configuration(key, 'chip_id')

def main():
    
    #load controller
    c=load_controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    
    c.io.reset_larpix(length=16)
    chip11_key = larpix.key.Key(1, 1, 11)

    all_keys=[]
    all_keys.append(chip11_key)
#    all_keys = c.chips.keys()
    print("entering key loop")
    for key in all_keys:
        print(key)
        enable_pedestal(c, key, vref_dac=223)
    unmask(c, all_keys)

    c.io.reset_larpix(length=16)
    c.io.reset_larpix(length=16)
        
    data(c, 60, tag='pedestal')


if __name__ == '__main__':
    main()        
