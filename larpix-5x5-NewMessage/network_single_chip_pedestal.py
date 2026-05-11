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
        if not isinstance(msg, larpix.packet.packet_v2.Packet_v2):
            continue
        if msg.packet_type not in [larpix.packet.packet_v2.Packet_v2.CONFIG_READ_PACKET]:
            continue
        print(msg)
        # return msg.chip_id
    return 0


def conf_root(c, cm, cadd, iog, iochan, pacman_version):
    I_TX_DIFF = 7
    TX_SLICE = 7
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
    c[cm].config.enable_posi = [0, 1, 0, 0]  # [0, 1, 0, 0]
    c.write_configuration(cm, 'enable_posi')
    time.sleep(0.01)
    c[cm].config.i_tx_diff0 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff0')
    c[cm].config.i_tx_diff1 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff1')
    c[cm].config.i_tx_diff2 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff2')
    c[cm].config.i_tx_diff3 = I_TX_DIFF
    c.write_configuration(cm, 'i_tx_diff3')
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
    c[cm].config.enable_piso_downstream = [
        1, 1, 1, 1]  # krw adding May 8, 2023
    c.write_configuration(cm, 'enable_piso_downstream')
    time.sleep(0.01)
    c[cm].config.enable_piso_upstream = [0, 0, 0, 0]
    c.write_configuration(cm, 'enable_piso_upstream')
    c[cm].config.enable_piso_downstream = [1, 1, 1, 1]  # [1, 0, 0, 0]  # piso0
    c.write_configuration(cm, 'enable_piso_downstream')
    time.sleep(0.01)

    # enable pacman uart receiver
    c.io.set_reg(0x00100314, iochan-1, iog)

    # enforce asic config
    ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
    if not ok:
        ok, diff = c.enforce_configuration(cm, n=2, n_verify=2, timeout=0.05)
        if not ok:
            print(diff)
    print(cm, ok)


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
    for i in range(10):
        for key in reversed(keys):

            c[key].config.csa_enable = [1]*64
            c[key].config.channel_mask = [1]*64
            c[key].config.periodic_trigger_mask = [0]*64
            c.write_configuration(key, 'periodic_trigger_mask')
            c.write_configuration(key, 'csa_enable')
            c.write_configuration(key, 'channel_mask')


def set_register(c, chip_key, register, value):
    setattr(c[chip_key].config, register, value)
    c.write_configuration(chip_key, register)


def main(io_group=1, pacman_tile='1', verbose=True):

    ###########################################
    IO_GROUP = io_group
    pacman_version = 'v1rev5'
    list_pacman_tiles = pacman_tile.split(',')
    for i in range(len(list_pacman_tiles)):
        list_pacman_tiles[i] = int(list_pacman_tiles[i].strip())

    ###########################################

    # create a larpix controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)

    #Disable all UARTs -> just poke the register 0x001003f0 to disable all (f means all)
    c.io.set_reg(0x001003f0, 0, io_group)


    # request full reset at 0x00100420 and provide tile mask
    c.io.set_reg(0x00100420, 0x3ff, io_group)


    all_keys = []
    for PACMAN_TILE in list_pacman_tiles:
        IO_CHAN = (PACMAN_TILE-1) * 4 + 1

        chip11_key = larpix.key.Key(IO_GROUP, IO_CHAN, 11)

        conf_root(c, chip11_key, 11, IO_GROUP, IO_CHAN, "v1rev5")
        all_keys.append(chip11_key)

        enable_pedestal(c, chip11_key, vref_dac=223)
        unmask(c, all_keys)

    # request internal reset at 0x00100410 and provided tile mask
    c.io.set_reg(0x00100410, 0x3ff, io_group)

    return


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--io_group', default=1, type=int,
                        help='''Which io_group, default 1''')
    parser.add_argument('--pacman_tile', default='1',
                        type=str, help='''Which tile output to use''')
    args = parser.parse_args()
    main(**vars(args))


