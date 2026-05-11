import larpix
import larpix.io
# from base import utility_base
import numpy as np
import time

import pickle

data_dir = 'data/warm_test/'

def save_controller(c):
    with open('controller_self_trigger.pkl', 'wb') as f:
        c.io = None
        pickle.dump(c, f, pickle.HIGHEST_PROTOCOL)

def data(c, runtime, fname=None):
    all_datawords=[]
    if True:
        now=time.strftime("%Y_%m_%d_%H_%M_%Z")
        if fname is None: fname=data_dir+'packets-cooldown-'+now+'.h5'
        c.logger = larpix.logger.HDF5Logger(filename=fname)
        print('filename: ',c.logger.filename)
        c.reads.clear()
        c.logger.enable()
        c.run(runtime,' collecting data')
        c.logger.flush()
        c.logger.disable()
        c.logger=None

    return all_datawords


def unmask(c, key, mask=[0]*64):
    for i in range(10):
        c[key].config.csa_enable= [ 1-i for i in mask ]
        c[key].config.channel_mask= mask
        c[key].config.periodic_trigger_mask=[1]*64
        c.write_configuration(key, 'periodic_trigger_mask')
        c.write_configuration(key, 'csa_enable')
        c.write_configuration(key, 'channel_mask')

def mask_chip(c, key):
    for i in range(10):
        c[key].config.csa_enable= [0]*64
        c[key].config.channel_mask= [1]*64
        c[key].config.periodic_trigger_mask=[1]*64
        c.write_configuration(key, 'periodic_trigger_mask')
        c.write_configuration(key, 'csa_enable')
        c.write_configuration(key, 'channel_mask')

def enable_self_trigger(c, key):

    c[key].config.enable_periodic_trigger=0
    c[key].config.enable_rolling_periodic_trigger=0
    c[key].config.enable_periodic_reset=1
    c[key].config.enable_rolling_periodic_reset=1
    c[key].config.enable_hit_veto=1
    c[key].config.enable_periodic_trigger_veto=1
    c[key].config.pixel_trim_dac=[12]*64

    c[key].config.threshold_global = 55
    c[key].config.periodic_reset_cycles = 8

    c[key].config.cds_mode=0
    c[key].config.enable_data_stats=0
    c[key].config.vref_dac=255
    c[key].config.adc_hold_delay=15

    c[key].config.ibias_vcm_buffer = 15
    c.write_configuration(key, 'ibias_vcm_buffer')

    c[key].config.adc_comp_trim = 3
    c.write_configuration(key, 'adc_comp_trim')

    c[key].config.mark_first_packet = 0
    c[key].config.adc_ibias_delay = 8
    c.write_configuration(key, 'adc_ibias_delay')


    c.write_configuration(key, 'mark_first_packet')
    c.write_configuration(key, 'adc_hold_delay')
    c.write_configuration(key, 'pixel_trim_dac')
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

    #evaluate trigger rate at this threshold and (possibly) lower threshold here

    sample_time=0.5
    
    n_trigs = 0
    glob=18
    mask=[0]*64
    n_chans=0
    all_chans=set()
    max_rate = 100000
    mean_chip_rate=0
    while (mean_chip_rate < 10 or n_chans < 32) or max_rate > 25:
        
        if glob < 10: break
        print(key, 'global threshold:', glob, 'channels masked:', np.sum(mask))

        c[key].config.threshold_global = glob
        c.write_configuration(key, 'threshold_global')

        #enable CSA here!
        unmask(c, key, mask=mask)

        c.multi_read_configuration([key], timeout=sample_time,message='rate check')
        triggered_channels = c.reads[-1].extract('channel_id',packet_type=1)
        
        chans, counts =  np.unique(triggered_channels, return_counts=True) 
        if np.sum(counts)>0:
            max_rate = np.max(counts)/sample_time

        if True:
            print('channs:', len(chans))
            print('counts:', sum(counts))
            
            print('max:', max_rate)
            #print(c[key].config.pixel_trim_dac)

        mean_rate = len(triggered_channels)/sample_time/64
        mean_chip_rate = n_trigs/sample_time 
        toggled_glob=False
        
        if mean_rate < 0.1: 
            glob=glob-1
            toggled_glob=True

        if len(chans)>10 and mean_rate>200:
            glob=glob+1
            toggled_glob=True
        
        for chan in range(64):
            
            if mean_rate==0: continue
            n_trigs_chan = triggered_channels.count(chan)

            if n_trigs_chan > 0:
                all_chans.add(chan)

            tdac = c[key].config.pixel_trim_dac[chan]
            
            this_chan_rate = n_trigs_chan / sample_time
            
            #if this_chan_rate / mean_rate > 100:
            #    tdac += 3
            #elif this_chan_rate / mean_rate > 10:
            #    tdac += 2
            #elif this_chan_rate / mean_rate > 1:
            #    tdac +=1
            #elif this_chan_rate / mean_rate > 1:
            #    tdac += 1
            
            #if this_chan_rate==0 and not toggled_glob:
            #    tdac-=1
        
            
            if n_trigs_chan/sample_time > 10000:
                tdac = tdac  + 4
            elif n_trigs_chan/sample_time > 1000:
                tdac = tdac + 3
            elif n_trigs_chan/sample_time > 100:
                tdac = tdac + 2
            elif n_trigs_chan/sample_time > 10:
                tdac = tdac + 1

            if not toggled_glob and n_trigs_chan==0:
                tdac-=1

           # if n_trigs_chan/sample_time > mean_rate:
           #     tdac = tdac+1
            
            if  tdac > 31: 
                tdac=31
                mask[chan]=1

            if tdac<0: tdac=0

            c[key].config.pixel_trim_dac[chan]=tdac
            c.write_configuration(key, 'pixel_trim_dac')
        n_chans=len(chans)
        n_trigs = len(triggered_channels)

        mask_chip(c,key)
        #print

    ok, diff = c.enforce_configuration(key, n=3, n_verify=3, timeout=0.1)
    print(key, 'self-trigger enabled:', ok, 'nchans:', n_chans, 'n_trigs', n_trigs, 'masked', sum(mask) )
    c[key].config.channel_mask = mask

    if not ok: print(diff)




def main():
    
    #load controller
    c=None
    with open('controller.pkl', 'rb') as f:
        c = pickle.load(f)

    c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
   
    if True:
        c.io.reset_larpix(length=16)
        all_keys = c.chips.keys()
        for key in all_keys: enable_self_trigger(c, key)
        for key in all_keys: unmask(c, key, mask=c[key].config.channel_mask)
        save_controller(c)
        c.io = larpix.io.PACMAN_IO(relaxed=True, asic_version=3)
        c.io.reset_larpix(length=16)


if __name__ == '__main__':
    main()        
