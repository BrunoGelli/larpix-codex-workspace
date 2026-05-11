import larpix
import larpix.io
# from base import utility_base
import argparse
import time
from util import save_controller
import pickle
import tqdm

def set_register(c, chip_key, register, value):
    setattr(c[chip_key].config, register, value)
    c.write_configuration(chip_key, register)

	#cm is the father, ck the current chip 
def conf_east(c, cm, ck, cadd, iog, iochan):
    I_TX_DIFF = 7
    TX_SLICE = 15
    R_TERM = 7
    I_RX = 3
    V_CM = 5

    # add second chip
    # set mother transceivers
    c.add_chip(ck, version=3)
    c[cm].config.i_rx3 = I_RX
    c.write_configuration(cm, 'i_rx3')
    c[cm].config.r_term3 = R_TERM
    c.write_configuration(cm, 'r_term3')
    c[cm].config.i_tx_diff2 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff2')
    c[cm].config.tx_slices2 = TX_SLICE
    c.write_configuration(cm, 'tx_slices2')
    c[cm].config.enable_piso_upstream[2] = 1  # [0,0,1,0]
    m_piso = c[cm].config.enable_piso_upstream
    # turn only one upstream port on during config
    c[cm].config.enable_piso_upstream = [0, 0, 1, 0]
    c.write_configuration(cm, 'enable_piso_upstream')
    # add new chip to network
    default_key = larpix.key.Key(iog, iochan, 1)  # '1-5-1'
    c.add_chip(default_key, version=3)  # TODO, create v2c class
    #  - - rename to chip_id = 12
    c[default_key].config.chip_id = cadd
    c.write_configuration(default_key, 'chip_id')
    #  - - remove default chip id from the controller
    c.remove_chip(default_key)
    #  - - and add the new chip id
    #print(ck)

    c[ck].config.chip_id = cadd
    c[ck].config.i_rx1 = I_RX
    c.write_configuration(ck, 'i_rx1')
    c[ck].config.r_term1 = R_TERM
    c.write_configuration(ck, 'r_term1')
    c[ck].config.enable_posi = [0, 1, 0, 0]
    c.write_configuration(ck, 'enable_posi')
    c[ck].config.enable_piso_upstream = [0, 0, 0, 0]
    c.write_configuration(ck, 'enable_piso_upstream')
    c[ck].config.i_tx_diff0 = I_TX_DIFF
    c.write_configuration(ck, 'i_tx_diff0')
    c[ck].config.tx_slices0 = TX_SLICE
    c.write_configuration(ck, 'tx_slices0')
    c.write_configuration(ck, 'enable_piso_downstream')
    c[ck].config.enable_piso_downstream = [
        1, 0, 0, 0]  # only one downstream port
    c.write_configuration(ck, 'enable_piso_downstream')
    # enable mother rx
    c[cm].config.enable_piso_upstream = m_piso
    c.write_configuration(cm, 'enable_piso_upstream')  # allow multi-upstream
    c[cm].config.enable_posi[3] = 1  # [0,1,0,1]
    c.write_configuration(cm, 'enable_posi')
    c[cm].config.v_cm_lvds_tx0 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx0')
    c[cm].config.v_cm_lvds_tx1 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx1')
    c[cm].config.v_cm_lvds_tx2 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx2')
    c[cm].config.v_cm_lvds_tx3 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx3')

    ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
    if not ok:
        ok, diff = c.enforce_configuration(ck, n=2, n_verify=2, timeout=0.05)
    if ok:
        print(ck, 'added to hydra-network!')
    else:
        print(ck, 'unable to configure')


def conf_south(c, cm, ck, cadd, iog, iochan):
    I_TX_DIFF = 7
    TX_SLICE = 15
    R_TERM = 7
    I_RX = 3
    V_CM = 5

    # add second chip
    # set mother transceivers rx2, tx1
    c.add_chip(ck, version=3)
    c[cm].config.i_rx2 = I_RX
    c.write_configuration(cm, 'i_rx2')
    c[cm].config.r_term2 = R_TERM
    c.write_configuration(cm, 'r_term2')
    c[cm].config.i_tx_diff1 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff1')
    c[cm].config.tx_slices1 = TX_SLICE
    c.write_configuration(cm, 'tx_slices1')
    c[cm].config.enable_piso_upstream[1] = 1
    m_piso = c[cm].config.enable_piso_upstream
    c[cm].config.enable_piso_upstream=[0,1,0,0]
    c.write_configuration(cm, 'enable_piso_upstream')

    # add new chip to network
    default_key = larpix.key.Key(iog, iochan, 1)  # '1-5-1'
    c.add_chip(default_key, version=3)  # TODO, create v2c class
    #  - - rename to chip_id = 12
    c[default_key].config.chip_id = cadd
    c.write_configuration(default_key, 'chip_id')
    #  - - remove default chip id from the controller
    c.remove_chip(default_key)

    #print(ck)
    c[ck].config.chip_id = cadd
    c[ck].config.i_rx0 = I_RX  # rx0,tx3
    c.write_configuration(ck, 'i_rx0')
    c[ck].config.r_term0 = R_TERM
    c.write_configuration(ck, 'r_term0')
    c[ck].config.enable_posi = [1, 0, 0, 0]
    c.write_configuration(ck, 'enable_posi')
    c[ck].config.enable_piso_upstream = [0, 0, 0, 0]
    c.write_configuration(ck, 'enable_piso_upstream')
    c[ck].config.i_tx_diff3 = I_TX_DIFF
    c.write_configuration(ck, 'i_tx_diff3')
    c[ck].config.tx_slices3 = TX_SLICE
    c.write_configuration(ck, 'tx_slices3')
    c.write_configuration(ck, 'enable_piso_downstream')

    c[ck].config.enable_piso_downstream = [0, 0, 0, 1]
    c.write_configuration(ck, 'enable_piso_downstream')
    # enable mother rx
    c[cm].config.enable_piso_upstream = m_piso
    c.write_configuration(cm, 'enable_piso_upstream')  # allow multi-upstream
    c[cm].config.enable_posi[2] = 1  
    c.write_configuration(cm, 'enable_posi')
    c[cm].config.v_cm_lvds_tx0 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx0')
    c[cm].config.v_cm_lvds_tx1 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx1')
    c[cm].config.v_cm_lvds_tx2 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx2')
    c[cm].config.v_cm_lvds_tx3 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx3')

    ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
    if not ok:
        ok, diff = c.enforce_configuration(ck, n=2, n_verify=2, timeout=0.05)
    
    if ok:
        print(ck, 'added to hydra-network!')
    else:
        print(ck, 'unable to configure')

def read(c, key, param):
    c.reads = []
    c.read_configuration(key, param, timeout=0.1)
    message = c.reads[-1]
    for msg in message:
        if not isinstance(msg, larpix.packet.packet_v2.Packet_v2):
            continue
        if msg.packet_type not in [larpix.packet.packet_v2.Packet_v2.CONFIG_READ_PACKET]:
            continue
        print(msg)
        # return msg.chip_id
    return 0

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

def enable_SelfTrigger(c, key, vref_dac=255):

    c[key].config.enable_external_sync = 1
    c.write_configuration(key, 'enable_external_sync')
    c[key].config.mark_first_packet = 0
    c.write_configuration(key, 'mark_first_packet')
    c[key].config.enable_periodic_trigger = 0
    c[key].config.enable_rolling_periodic_trigger = 0
    c[key].config.enable_periodic_reset = 1
    c[key].config.enable_rolling_periodic_reset = 1
    c[key].config.enable_hit_veto = 1
    c[key].config.enable_periodic_trigger_veto = 0

    c[key].config.threshold_global = 255
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

    c.write_configuration(key, 'periodic_reset_cycles')

    ok, diff = c.enforce_configuration(key, n=3, n_verify=3, timeout=0.1)
    print(key, ' pedestal enabled:', ok)
    if not ok:
        print(diff)

def unmask(c, keys):
    for i in range(10):
        for key in reversed(keys):

            c[key].config.csa_enable = [1]*64
            c[key].config.channel_mask = [1]*64
            c[key].config.periodic_trigger_mask = [0]*64
            c.write_configuration(key, 'periodic_trigger_mask')
            c.write_configuration(key, 'csa_enable')
            c.write_configuration(key, 'channel_mask')

def conf_root(c, cm, cadd, iog, iochan, pacman_version):
    I_TX_DIFF = 7
    TX_SLICE = 15
    R_TERM = 7
    I_RX = 3
    V_CM = 5
    c.add_chip(cm, version=3)
    #  - - default larpix chip_id is '1'
    default_key = larpix.key.Key(iog, iochan, 1)  # '1-5-1'
    c.add_chip(default_key, version=3)  
    #  - - rename to chip_id = cm
    c[default_key].config.chip_id = cadd
    c.write_configuration(default_key, 'chip_id')
    #  - - remove default chip id from the controller
    c.remove_chip(default_key)
    #  - - and add the new chip id
    c[cm].config.chip_id = cadd
    #c[cm].config.enable_external_sync = 1
    #c.write_configuration(cm, 'enable_external_sync')
    c[cm].config.i_rx1 = I_RX
    c.write_configuration(cm, 'i_rx1')
    c[cm].config.r_term1 = R_TERM
    c.write_configuration(cm, 'r_term1')
    c[cm].config.enable_posi = [0, 1, 0, 0] #[0, 1, 0, 0]
    c.write_configuration(cm, 'enable_posi')
    time.sleep(0.01)
    c[cm].config.i_tx_diff0 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff0')
    c[cm].config.tx_slices0 = TX_SLICE
    c.write_configuration(cm, 'tx_slices0')
    c[cm].config.i_tx_diff3 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff3')
    c[cm].config.tx_slices3 = TX_SLICE
    c.write_configuration(cm, 'tx_slices3')
    c[cm].config.i_tx_diff1 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff1')
    c[cm].config.tx_slices1 = TX_SLICE
    c.write_configuration(cm, 'tx_slices1')
    c[cm].config.i_tx_diff2 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff2')
    c[cm].config.tx_slices2 = TX_SLICE
    c.write_configuration(cm, 'tx_slices2')
    c[cm].config.v_cm_lvds_tx0 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx0')
    c[cm].config.v_cm_lvds_tx1 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx1')
    c[cm].config.v_cm_lvds_tx2 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx2')
    c[cm].config.v_cm_lvds_tx3 = V_CM
    c.write_configuration(cm, 'v_cm_lvds_tx3')

    c[cm].config.enable_piso_upstream = [0,0,0,0]
    c.write_configuration(cm, 'enable_piso_upstream')
    c[cm].config.enable_piso_downstream = [1, 0, 0, 0] #[1, 0, 0, 0]  # piso0
    c.write_configuration(cm, 'enable_piso_downstream')
    time.sleep(0.01)

    # enable pacman uart receiver (old version)
    # ch_set = pow(2, iochan-1)
    # if pacman_version == 'v1rev5':
    #     rx_en = c.io.get_reg(0x201c, iog)
    #     c.io.set_reg(0x201c, rx_en ^ ch_set, iog)
    # else:
    #     rx_en = c.io.get_reg(0x18, iog)
    #     c.io.set_reg(0x18, rx_en | ch_set, iog)
    c.io.set_reg(0x00100314, iochan-1, iog)

    ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
    if not ok:
        ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
    if ok:
        print('Root-chip added:', cm)
    else:
        print('Unable to configure:', cm)

def main(vdda, vddd, verbose=True):

    ###########################################
    IO_GROUP = 1
    PACMAN_TILE = 1  # 1IO_CHAN = 25 # 1
    IO_CHAN = 1 # 1
    RESET_CYCLES = 300000  # 5000000

    REF_CURRENT_TRIM = 0
    ###########################################

    # create a larpix controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    io_group = IO_GROUP
    pacman_version = 'v1rev5'
    pacman_tile = [PACMAN_TILE]

      #Disable all UARTs -> just poke the register 0x001003f0 to disable all (f means all)
    c.io.set_reg(0x001003f0, 0, io_group)


    # request full reset at 0x00100420 and provide tile mask
    c.io.set_reg(0x00100420, 0x3ff, io_group)


    chip11_key = larpix.key.Key(IO_GROUP, IO_CHAN, 11)

    all_keys=[]

    conf_root(c, chip11_key, 11, IO_GROUP, IO_CHAN, pacman_version)
    all_keys.append(chip11_key)

    chip12_key = larpix.key.Key(IO_GROUP, IO_CHAN, 12)
    conf_east(c, chip11_key, chip12_key, 12, IO_GROUP, IO_CHAN)
    all_keys.append(chip12_key)

    chip13_key = larpix.key.Key(IO_GROUP, IO_CHAN, 13)
    conf_east(c, chip12_key, chip13_key, 13, IO_GROUP, IO_CHAN)
    all_keys.append(chip13_key)

    # add fourth chip
    chip14_key = larpix.key.Key(IO_GROUP, IO_CHAN, 14)
    conf_east(c, chip13_key, chip14_key, 14, IO_GROUP, IO_CHAN)
    all_keys.append(chip14_key)

    # add fifth chip
    chip15_key = larpix.key.Key(IO_GROUP, IO_CHAN, 15)
    conf_east(c, chip14_key, chip15_key, 15, IO_GROUP, IO_CHAN)
    all_keys.append(chip15_key)
     

    # add second root chain
    IO_CHAN = IO_CHAN + 1
    
    #print('IO_CHAN')
    chip21_key = larpix.key.Key(IO_GROUP, IO_CHAN, 21)
    conf_root(c, chip21_key, 21, IO_GROUP, IO_CHAN, pacman_version)
    all_keys.append(chip21_key)
    
    # add second chip
    chip22_key = larpix.key.Key(IO_GROUP, IO_CHAN, 22)
    conf_east(c, chip21_key, chip22_key, 22, IO_GROUP, IO_CHAN)
    all_keys.append(chip22_key)

    # # add third chip
    chip23_key = larpix.key.Key(IO_GROUP, IO_CHAN, 23)
    conf_east(c, chip22_key, chip23_key, 23, IO_GROUP, IO_CHAN)
    all_keys.append(chip23_key)

    # add fourth chip
    chip24_key = larpix.key.Key(IO_GROUP, IO_CHAN, 24)
    conf_east(c, chip23_key, chip24_key, 24, IO_GROUP, IO_CHAN)
    all_keys.append(chip24_key)

    # add fifth chip
    chip25_key = larpix.key.Key(IO_GROUP, IO_CHAN, 25)
    conf_east(c, chip24_key, chip25_key, 25, IO_GROUP, IO_CHAN)
    all_keys.append(chip25_key)

    # add third root chain
    IO_CHAN = IO_CHAN + 1
    
    chip31_key = larpix.key.Key(IO_GROUP, IO_CHAN, 31)
    conf_root(c, chip31_key, 31, IO_GROUP, IO_CHAN, pacman_version)
    all_keys.append(chip31_key)
    
    # add second chip
    chip32_key = larpix.key.Key(IO_GROUP, IO_CHAN, 32)
    conf_east(c, chip31_key, chip32_key, 32, IO_GROUP, IO_CHAN)
    all_keys.append(chip32_key)

    # add third chip
    chip33_key = larpix.key.Key(IO_GROUP, IO_CHAN, 33)
    conf_east(c, chip32_key, chip33_key, 33, IO_GROUP, IO_CHAN)
    all_keys.append(chip33_key)
    # add fourth chip
    chip34_key = larpix.key.Key(IO_GROUP, IO_CHAN, 34)
    conf_east(c, chip33_key, chip34_key, 34, IO_GROUP, IO_CHAN)
    all_keys.append(chip34_key)

    # add fifth chip
    chip35_key = larpix.key.Key(IO_GROUP, IO_CHAN, 35)
    conf_east(c, chip34_key, chip35_key, 35, IO_GROUP, IO_CHAN)
    all_keys.append(chip35_key)

    # add fourth root chain
     
    IO_CHAN = IO_CHAN + 1

    chip41_key = larpix.key.Key(IO_GROUP, IO_CHAN, 41)
    
    conf_root(c, chip41_key, 41, IO_GROUP, IO_CHAN, pacman_version)
    all_keys.append(chip41_key)
    
    # add second chip
    chip42_key = larpix.key.Key(IO_GROUP, IO_CHAN, 42)
    conf_east(c, chip41_key, chip42_key, 42, IO_GROUP, IO_CHAN)
    all_keys.append(chip42_key)

    # add third chip
    chip43_key = larpix.key.Key(IO_GROUP, IO_CHAN, 43)
    conf_east(c, chip42_key, chip43_key, 43, IO_GROUP, IO_CHAN)
    all_keys.append(chip43_key)
    
    # add fourth chip
    chip44_key = larpix.key.Key(IO_GROUP, IO_CHAN, 44)
    conf_east(c, chip43_key, chip44_key, 44, IO_GROUP, IO_CHAN)
    all_keys.append(chip44_key)

    # add fifth chip
    chip45_key = larpix.key.Key(IO_GROUP, IO_CHAN, 45)
    conf_east(c, chip44_key, chip45_key, 45, IO_GROUP, IO_CHAN)
    all_keys.append(chip45_key)

    # add 51 south
    chip51_key=larpix.key.Key(IO_GROUP,IO_CHAN,51)
    conf_south(c,chip41_key,chip51_key,51,IO_GROUP,IO_CHAN)
    all_keys.append(chip51_key)

    # add 52 south
    chip52_key=larpix.key.Key(IO_GROUP,IO_CHAN,52)
    conf_east(c,chip51_key,chip52_key,52,IO_GROUP,IO_CHAN)
    all_keys.append(chip52_key)

    # add 53 south
    chip53_key=larpix.key.Key(IO_GROUP,IO_CHAN,53)
    conf_east(c,chip52_key,chip53_key,53,IO_GROUP,IO_CHAN)
    all_keys.append(chip53_key)

    # add 54 south
    chip54_key=larpix.key.Key(IO_GROUP,IO_CHAN,54)
    conf_east(c,chip53_key,chip54_key,54,IO_GROUP,IO_CHAN)
    all_keys.append(chip54_key)

    # add 54 south
    chip55_key=larpix.key.Key(IO_GROUP,IO_CHAN,55)
    conf_east(c,chip54_key,chip55_key,55,IO_GROUP,IO_CHAN)
    all_keys.append(chip55_key)

    for ChipKey in all_keys:
        # enable_pedestal(c, ChipKey,vref_dac=223)
        enable_SelfTrigger(c, ChipKey,vref_dac=223)
        

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

