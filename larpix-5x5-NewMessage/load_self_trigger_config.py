import larpix
import larpix.io
# from base import utility_base
import larpix.format.rawhdf5format as rhdf5
import time
import larpix.format.pacman_msg_format as pacman_msg_fmt
import network_5x5
import pickle

data_dir = 'data/'

def data(c, runtime, fname=None, tag=''):
    all_datawords=[]
    now=time.strftime("%Y_%m_%d_%H_%M_%Z")
    if True:
        if fname is None: fname=data_dir+tag+'packets-cooldown-'+now+'.h5'
        c.logger = larpix.logger.HDF5Logger(filename=fname)
        print('filename: ',c.logger.filename)
        c.reads.clear() 
        c.io.reset_larpix(length=16)
        c.logger.enable()
        c.run(runtime,' collecting data')
        c.logger.flush()
        c.logger.disable()

    else:
        c.io.disable_packet_parsing = True
        c.io.enable_raw_file_writing = True
        if fname is None: fname='binary-'+now+'.h5'
        c.io.raw_filename=fname
        c.io.join()
        rhdf5.to_rawfile(filename=c.io.raw_filename, \
                         io_version=pacman_msg_fmt.latest_version)
        
        print('filename: ',c.io.raw_filename)
        run_start=time.time()
        c.start_listening()
        last_counter = 0
        oldfilename=c.io.raw_filename
        while True:
            c.read()
            time.sleep(0.1)
            now=time.time()
            if now>(run_start+runtime): break
        c.stop_listening()
        c.read()
        c.io.join()
    return


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
    c=None
    with open('controller_self_trigger.pkl', 'rb') as f:
        c = pickle.load(f)
   
    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    
    c.io.reset_larpix(length=16)
    all_keys = c.chips.keys()

    mask(c, all_keys)

    for key in all_keys: 
        ok, diff = c.enforce_configuration( key, n=3, n_verify=3, timeout=0.1 )
        print(key, ok)

    with open('controller_self_trigger.pkl', 'rb') as f:
        c = pickle.load(f)
    


    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
    write_channel_mask(c, all_keys)
    
    c.io.reset_larpix(length=16)
 
if __name__ == '__main__':
    main()        
