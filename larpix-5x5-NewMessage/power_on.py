import larpix
import larpix.io
# from base import utility_base
import argparse
import time

import pickle


def power_readback(io, io_group, pacman_version, tile):
    readback = {}
    for i in tile:
        readback[i]=[]
        vdda=io.get_reg(0x00200030+(i-1), io_group=io_group)
        vddd=io.get_reg(0x00200040+(i-1), io_group=io_group)
        idda=io.get_reg(0x00200050+(i-1), io_group=io_group)
        iddd=io.get_reg(0x00200060+(i-1), io_group=io_group)
        print('Tile ',i,'  VDDA: ',vdda,' mV  IDDA: ', idda/4,' mA  ',
                  'VDDD: ',vddd,' mV  IDDD: ',iddd/4,' mA')
        readback[i]=[vdda, idda/4, vddd, iddd/4]
    return readback


def main(vdda, vddd, io_group=1, pacman_tile='1', verbose=True):

    ###########################################
    IO_GROUP = io_group
    # VDDA_DAC = vdda  # VDDA_DAC = 52000 #48000 cold
    # VDDD_DAC = vddd  # VDDD_DAC = 28000 # 32000# 28500 # ~1.1 V #42000 cold
    RESET_CYCLES = 300000  # 5000000

    list_pacman_tiles = pacman_tile.split(',')
    for i in range(len(list_pacman_tiles)):
        list_pacman_tiles[i] = int(list_pacman_tiles[i].strip())
    list_vdda = vdda.split(',')
    for i in range(len(list_vdda)):
        list_vdda[i] = int(list_vdda[i].strip())
    if len(list_vdda) == 1:
        list_vdda = list_vdda * len(list_pacman_tiles)
    if len(list_vdda) != len(list_pacman_tiles):
        print('ERROR: number of VDDA values must be 1 or equal to number of tiles')
        return
    list_vddd = vddd.split(',')
    for i in range(len(list_vddd)):
        list_vddd[i] = int(list_vddd[i].strip())
    if len(list_vddd) == 1:
        list_vddd = list_vddd * len(list_pacman_tiles)
    if len(list_vddd) != len(list_pacman_tiles):
        print('ERROR: number of VDDD values must be 1 or equal to number of tiles')
        return

    VDDA_DAC = {}
    VDDD_DAC = {}
    for idx, PACMAN_TILE in enumerate(list_pacman_tiles):
        VDDA_DAC[PACMAN_TILE] = list_vdda[idx]
        VDDD_DAC[PACMAN_TILE] = list_vddd[idx]

    ###########################################
    print('Powering on PACMAN tiles with the following VDDA and VDDD values:')
    for PACMAN_TILE in list_pacman_tiles:
        print('  Tile ', PACMAN_TILE, '  VDDA DAC: ', VDDA_DAC[PACMAN_TILE],
              '  VDDD DAC: ', VDDD_DAC[PACMAN_TILE])
    ###########################################

    # create a larpix controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    io_group = IO_GROUP
    pacman_version = 'v1rev5'
    pacman_tile = [PACMAN_TILE]

    #Disable all UARTs -> just poke the register 0x001003f0 to disable all (f means all)
    c.io.set_reg(0x001003f0, 0, io_group)

    print('enable pacman power')

    #Enable_Global_Tile_Power -> just poke the register. 0x00100114 to disable.
    c.io.set_reg(0x00100114, 0, io_group)

    # set uart clock ratio and power for all tiles
    for PACMAN_TILE in list_pacman_tiles:
        IO_CHAN = (PACMAN_TILE-1) * 4 + 1

        # set voltage dacs  VDDD first
        c.io.set_reg(0x00200020+(PACMAN_TILE-1), VDDD_DAC[PACMAN_TILE], io_group)
        c.io.set_reg(0x00200010+(PACMAN_TILE-1), VDDA_DAC[PACMAN_TILE], io_group)

    # enable tile power
    tile_enable_sum = 0
    tile_enable_val = 0
    for PACMAN_TILE in list_pacman_tiles:
        c.io.set_reg(0x00100214, PACMAN_TILE-1, io_group) # poke register 0x00100214 with the tile number to
							  # enable power to that specific tile (HW starts at 0)
        time.sleep(0.05)

    print('Power readback after power on:')

    readback = power_readback(
        c.io, io_group, pacman_version, list_pacman_tiles)

    # sending reset and waiting for it to be completed
    c.io.set_reg(0x00100420, 0x3ff, io_group)
    time.sleep(0.001) # factor of 10 longer than 1024*100ns

    with open('controller.pkl', 'wb') as f:
        c.io = None
        pickle.dump(c, f, pickle.HIGHEST_PROTOCOL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--io_group', default=1, type=int,
                        help='''Which io_group, default 1''')
    parser.add_argument('--pacman_tile', default='1', type=str,
                        help='''Which tile to enable power on''')
    parser.add_argument('--vdda', default='0', type=str,
                        help='''VDDA dac value''')
    parser.add_argument('--vddd', default='0', type=str,
                        help='''VDDD dac value''')
    args = parser.parse_args()
    main(**vars(args))
