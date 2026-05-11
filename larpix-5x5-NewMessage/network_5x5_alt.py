import larpix
import larpix.io
# from base import utility_base
import argparse
import time
from util import save_controller
import pickle


def set_register(c, chip_key, register, value):
    setattr(c[chip_key].config, register, value)
    c.write_configuration(chip_key, register)

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

    # c.io.set_reg(0x18, 1, io_group=1)
    c[cm].config.enable_piso_upstream = [0,0,0,0]
    c.write_configuration(cm, 'enable_piso_upstream')
    c[cm].config.enable_piso_downstream = [1, 0, 0, 0] #[1, 0, 0, 0]  # piso0
    c.write_configuration(cm, 'enable_piso_downstream')
    time.sleep(0.01)

    # enable pacman uart receiver
    ch_set = pow(2, iochan-1)
    if pacman_version == 'v1rev5':
        rx_en = c.io.get_reg(0x201c, iog)
        c.io.set_reg(0x201c, rx_en ^ ch_set, iog)
    else:
        rx_en = c.io.get_reg(0x18, iog)
        c.io.set_reg(0x18, rx_en | ch_set, iog)
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
    PACMAN_TILE = 2  # 1IO_CHAN = 25 # 1
    IO_CHAN = 5 # 1
    RESET_CYCLES = 300000  # 5000000

    REF_CURRENT_TRIM = 0
    ###########################################

    # create a larpix controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    io_group = IO_GROUP
    pacman_version = 'v1rev4'
    pacman_tile = [PACMAN_TILE]

    if pacman_version == 'v1rev5':
        RX_REG = 0x201c
        RX_VAL = 0xffffffff
    else:
        RX_REG = 0x18
        RX_VAL = 0
    c.io.set_reg(RX_REG, RX_VAL, io_group)

    c.io.reset_larpix(length=1024)
    chip11_key = larpix.key.Key(IO_GROUP, IO_CHAN, 11)

    all_keys=[]

    conf_root(c, chip11_key, 11, IO_GROUP, IO_CHAN, pacman_version)
    all_keys.append(chip11_key)
    # add second chip
    chip12_key = larpix.key.Key(IO_GROUP, IO_CHAN, 12)
    conf_east(c, chip11_key, chip12_key, 12, IO_GROUP, IO_CHAN)
    all_keys.append(chip12_key)


    # add third chip
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
     
    # add second chip
    chip42_key = larpix.key.Key(IO_GROUP, IO_CHAN, 42)
    conf_south(c, chip32_key, chip42_key, 42, IO_GROUP, IO_CHAN)
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

    # add 52 south
    chip52_key=larpix.key.Key(IO_GROUP,IO_CHAN,52)
    conf_south(c,chip42_key,chip52_key,52,IO_GROUP,IO_CHAN)
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
    ##
    # Write some registers to all of the chips
    
    c.io.reset_larpix(length=16)
    c.reads.clear()
    for key in all_keys:
        set_register(c, key, 'csa_enable', [0]*64)
        ok, diff = c.enforce_configuration(key, timeout=0.1, n=2, n_verify=2)
        if ok:
            print('Configured chip:', key)
        else:
            print('Unable to configure', key)

    save_controller(c)

    return

if __name__ == '__main__':
        parser = argparse.ArgumentParser()
        parser.add_argument('--vdda', default=52000, type=int, help='''VDDA dac value''')
        parser.add_argument('--vddd', default=28000, type=int, help='''VDDA dac value''')
        args = parser.parse_args()
        main(**vars(args))

