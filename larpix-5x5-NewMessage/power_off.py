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


def main(vdda, vddd, io_group=1, pacman_tile=1, verbose=True):

    ###########################################
    IO_GROUP = io_group
    PACMAN_TILE = pacman_tile  # 1IO_CHAN = 25 # 1
    IO_CHAN = (pacman_tile-1) * 4 + 1
    VDDA_DAC = vdda  # VDDA_DAC = 52000 #48000 cold
    VDDD_DAC = vddd  # VDDD_DAC = 28000 # 32000# 28500 # ~1.1 V #42000 cold
    RESET_CYCLES = 300000  # 5000000

    # create a larpix controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    io_group = IO_GROUP
    pacman_version = 'v1rev5'
    pacman_tile = [PACMAN_TILE]


    #Disable all UARTs -> just poke the register 0x001003f0 to disable all (f means all)
    c.io.set_reg(0x001003f0, 0, io_group)

    if True:
        print('disable pacman power')
        # disable tile power, LARPIX clock
        c.io.set_reg(0x001002f0, 0, io_group) # Disable Tile Power (f means all of them)
        c.io.set_reg(0x00100110, 0, io_group) # Disable Global Tile Power

        readback = power_readback(
            c.io, io_group, pacman_version, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        time.sleep(0.015)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--io_group', default=1, type=int,
                        help='''Which io_group, default 1''')
    parser.add_argument('--pacman_tile', default=1, type=int,
                        help='''Which tile to enable power on''')
    parser.add_argument('--vdda', default=46000, type=int,
                        help='''VDDA dac value''')
    parser.add_argument('--vddd', default=22000, type=int,
                        help='''VDDA dac value''')
    args = parser.parse_args()
    main(**vars(args))
