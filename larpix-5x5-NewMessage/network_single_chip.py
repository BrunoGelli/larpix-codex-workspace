import larpix
import larpix.io
# from base import utility_base
import argparse
import time

import pickle


def read(c, key, param):
    c.reads = []
    c.read_configuration(key, param, timeout=0.1)
    message = c.reads[-1]
    for msg in message:
        print("read loop")
        if not isinstance(msg, larpix.packet.packet_v2.Packet_v2):
            continue
        if msg.packet_type not in [larpix.packet.packet_v2.Packet_v2.CONFIG_READ_PACKET]:
            continue
        print(msg)
        # return msg.chip_id
    return 0


def conf_root(c, cm, cadd, iog, iochan, pacman_version):
    I_TX_DIFF = 7
    TX_SLICE =7
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
    c[cm].config.enable_external_sync = 1
    c.write_configuration(cm, 'enable_external_sync')
    c[cm].config.i_rx1 = I_RX
    c.write_configuration(cm, 'i_rx1')
    c[cm].config.r_term1 = R_TERM
    c.write_configuration(cm, 'r_term1')
    c[cm].config.enable_posi = [0, 1, 0, 0] #[1, 0, 0, 0] for charge injection board
    c.write_configuration(cm, 'enable_posi')
    print("first delay - 0.01s")
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
    print("second delay - 0.01s again")
    time.sleep(0.01)
    c[cm].config.enable_piso_upstream = [0, 0, 0, 0]
    c.write_configuration(cm, 'enable_piso_upstream')
    c[cm].config.enable_piso_downstream = [1, 1, 1, 1]
    c.write_configuration(cm, 'enable_piso_downstream')


    # enable pacman uart receiver
    ch_set = pow(2, iochan-1)
    if pacman_version == 'v1rev5':
        rx_en = c.io.get_reg(0x0010201c, iog)
        c.io.set_reg(0x0010201c, rx_en ^ ch_set, iog)
        c.io.set_reg(0x00102020, 0x000000FF, iog)
    else:
        rx_en = c.io.get_reg(0x00100018, iog)
        c.io.set_reg(0x00100018, rx_en | ch_set, iog)
    ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
    if not ok:
        ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
    print(cm, ok)


def set_register(c, chip_key, register, value):
    setattr(c[chip_key].config, register, value)
    c.write_configuration(chip_key, register)

def main(vdda, vddd, io_group=1, pacman_tile=1, verbose=True):

    ###########################################
    IO_GROUP = io_group
    PACMAN_TILE = pacman_tile  # 1IO_CHAN = 25 # 1
    IO_CHAN = (pacman_tile-1) * 4 + 1
    VDDA_DAC = vdda #VDDA_DAC = 52000 #48000 cold
    VDDD_DAC = vddd #VDDD_DAC = 28000 # 32000# 28500 # ~1.1 V #42000 cold
    RESET_CYCLES = 300000  # 5000000

    REF_CURRENT_TRIM = 0
    ###########################################

    # create a larpix controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    io_group = IO_GROUP
    pacman_version = 'v1rev5'
    pacman_tile = [PACMAN_TILE]
    
    if pacman_version == 'v1rev5':
        RX_REG = 0x0010201c
        RX_VAL = 0xffffffff
    else:
        RX_REG = 0x00100018
        RX_VAL = 0
    rx_en = c.io.get_reg(RX_REG, io_group)
    print(rx_en)
    c.io.set_reg(RX_REG, RX_VAL, io_group)
    
    c.io.reset_larpix(length=1024)
    c.io.reset_larpix(length=1024)

    chip11_key = larpix.key.Key(IO_GROUP, IO_CHAN, 11)

    all_keys=[]
     
    conf_root(c, chip11_key, 11, IO_GROUP, IO_CHAN, pacman_version)
    print("we exited the function - conf_root")
    all_keys.append(chip11_key)
  


    # ADD CODE HERE TO SET SPECIFIC REGISTERS

    set_register(c, chip11_key, 'channel_mask', [0]*64)
    set_register(c, chip11_key, 'csa_enable', [1]*64)
    set_register(c, chip11_key, 'enable_periodic_reset', 1)
    set_register(c, chip11_key, 'periodic_reset_cycles', 4)
    set_register(c, chip11_key, 'threshold_global', 255)

    # Check that all of the registers were successfully written!

    ok, diff = c.enforce_configuration(chip11_key, n=3, n_verify=3)
#    ok = False
#    diff = "bla"
    if ok:
        print('Enforced successfully!')
    else:
        print('Not enforced correctly:', diff)

    

    return
if __name__ == '__main__':
        parser = argparse.ArgumentParser()
        parser.add_argument('--io_group', default=1, type=int, help='''Which io_group, default 1''')
        parser.add_argument('--pacman_tile', default=1, type=int, help='''Which tile output to use''') 
        parser.add_argument('--vdda', default=46000, type=int, help='''VDDA dac value''')
        parser.add_argument('--vddd', default=22000, type=int, help='''VDDA dac value''')
        args = parser.parse_args()
        main(**vars(args))
