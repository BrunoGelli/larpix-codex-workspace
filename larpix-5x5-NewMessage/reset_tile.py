import larpix
import larpix.io
import argparse
import time
import tqdm


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


    # request internal reset at 0x00100410 and provided tile mask
    c.io.set_reg(0x00100410, 0x3ff, io_group)

    return

if __name__ == '__main__':
        parser = argparse.ArgumentParser()
        parser.add_argument('--vdda', default=52000, type=int, help='''VDDA dac value''')
        parser.add_argument('--vddd', default=28000, type=int, help='''VDDA dac value''')
        args = parser.parse_args()
        main(**vars(args))

