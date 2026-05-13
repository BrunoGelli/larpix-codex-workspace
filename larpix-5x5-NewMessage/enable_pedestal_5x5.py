import larpix
import larpix.io
# from base import utility_base
import argparse
import time
from util import save_controller
import pickle
import tqdm

def enable_pedestal(c, key, vref_dac=255):

    c[key].config.enable_external_sync = 1
    c.write_configuration(key, 'enable_external_sync')
    c[key].config.mark_first_packet = 0
    c.write_configuration(key, 'mark_first_packet')
    c[key].config.enable_periodic_trigger = 1
    c[key].config.enable_rolling_periodic_trigger = 1
    c[key].config.enable_periodic_reset = 1
    c[key].config.enable_rolling_periodic_reset = 1
    c[key].config.enable_hit_veto = 1
    c[key].config.enable_periodic_trigger_veto = 0

    c[key].config.threshold_global = 255
    c[key].config.periodic_trigger_cycles = 57812
    c[key].config.periodic_reset_cycles = 40

    c[key].config.cds_mode = 0
    c[key].config.enable_data_stats = 0
    c[key].config.vref_dac = vref_dac

    c[key].config.ibias_vcm_buffer = 15
    c.write_configuration(key, 'ibias_vcm_buffer')

    c[key].config.adc_comp_trim = 2
    c.write_configuration(key, 'adc_comp_trim')

    c[key].config.adc_ibias_delay = 7
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
    if not ok:
        print(diff)

def unmask(c, keys):
    for key in reversed(keys):

        c[key].config.csa_enable = [1]*64
        c[key].config.channel_mask = [0]*64
        c[key].config.periodic_trigger_mask = [1]*64
        c.write_configuration(key, 'periodic_trigger_mask')
        c.write_configuration(key, 'csa_enable')
        c.write_configuration(key, 'channel_mask')



def main(vdda, vddd, verbose=True):


    #load controller
    c=None
    with open('controller.pkl', 'rb') as f:
        c = pickle.load(f)

    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    all_keys = c.chips.keys()

    # request internal reset at 0x00100410 and provided tile mask
    c.io.set_reg(0x00100410, 0x3ff, io_group)

    for ChipKey in all_keys:
        enable_pedestal(c, ChipKey,vref_dac=223)

    unmask(c, all_keys)

    # request internal reset at 0x00100410 and provided tile mask
    c.io.set_reg(0x00100410, 0x3ff, io_group)
    
    return

if __name__ == '__main__':
        parser = argparse.ArgumentParser()
        parser.add_argument('--vdda', default=52000, type=int, help='''VDDA dac value''')
        parser.add_argument('--vddd', default=28000, type=int, help='''VDDA dac value''')
        args = parser.parse_args()
        main(**vars(args))

