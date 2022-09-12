#!/usr/bin/env python
# encoding: utf-8
''' 9/25/2020
Beat4aBlast v1.0
Based on madmom
Sends averaged beat period out onboard tty port, 1Mbps
Tracks and sends beat phase; detects missing beats based on average prior intervals
    To allow receivers to synchronize for half-speed, or for motor direction sync
WebSockets Server to accept IR remote control commands. Forwards to serial port.
'''

import _thread
import threading
import time
from pythonosc import udp_client
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder
client = udp_client.SimpleUDPClient('127.0.0.1', 12345)

def ms_time():
    return time.time() * 1000.0


start = ms_time()

import numpy as np
from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor
from madmom.models import BEATS_LSTM
from madmom.processors import IOProcessor, process_online
from numpy_ringbuffer import RingBuffer
import psutil, os
import time
from multiprocessing import Manager, Queue
import queue



TWOPI = 2*np.pi
RADPERDEGREE = 45/np.pi
DAMP = 0.5
MAX_BPM = 155
MIN_BPM = 55

# GLOBALS
last_real_T_ms = 0
beat_phase = 0;

kwargs = dict(
    fps = 100,
    correct = True,
    infile = None,
    outfile = None,
    max_bpm = MAX_BPM,
    min_bpm = MIN_BPM,
    nn_files = [BEATS_LSTM[1], ],  # , BEATS_LSTM[1]
    num_frames = 1,
    list_stream_input_device = 0,
#    stream_input_device = 2,
    online = True,
    #verbose = 1
)


def bpm_to_ms_period(bpm):
    return 60000 / bpm

def ms_period_to_bpm(msp):
    return 60000 / msp

depth = 5
rxq = queue.Queue(depth)  # queue of corrected-if-necessary timing of received beats
max_period = bpm_to_ms_period(MIN_BPM)
min_period = bpm_to_ms_period(MAX_BPM)

def into_my_q(o, q):
    global depth
    if q.qsize() == depth:
        q.get()  # dump one
    q.put(o)

def average_q(q):
    sum = 0
    items = 0
    for elem in list(q.queue):
        sum += elem
        items += 1
    if items == 0:
        return 0
    return sum / items


def beat_callback(beats, output=None):
    global last_real_T_ms, beat_phase
    if len(beats) > 0:
        b = beats[0]
        this_real_T_ms = time.time() * 1000              # milliseconds since epoch
        interval = (this_real_T_ms - last_real_T_ms)     # determine milliseconds since last beat
        if interval > 3 * max_period:   # no beats for a while; clear the queue first to start over
            for elem in list(rxq.queue):
                rxq.get()  # dump each
            last_real_T_ms = this_real_T_ms
            return

        if rxq.qsize() > 0:  # if we have at least one entry in the queue
            if interval >= min_period and interval <= 3 * max_period:  # if this interval looks valid
                ta = average_q(rxq)                  # average over all entries in the queue
    # determine if we have skipped any beats
                m = round(interval / ta);  # if = 1, no beat skipped; if = 2, one beat skipped, etc.
                if (m < 1):
                    m = 1;
                adjusted_interval = interval / m;
                into_my_q(adjusted_interval, rxq)                    # add actually-received period to the queue

                beat_phase = (m + beat_phase) % 4;  # next phase please
                beat_char = chr(ord('a') + beat_phase)
                s = "T{}{:.0f}\r".format(beat_char, adjusted_interval)
                bpm = ms_period_to_bpm(adjusted_interval)
                next_beat_ms = int(ms_time() + (bpm/60.0))
                bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
                msg = osc_message_builder.OscMessageBuilder(address='/beatape')
                msg.add_arg(bpm, "f")
                msg.add_arg(int(next_beat_ms))
                bundle.add_content(msg.build())
            
                bundle = bundle.build()
                client.send(bundle)
                print("T{}{:.0f} ({:.0f})".format(beat_char, adjusted_interval, bpm))
        else:   # queue just filling
            into_my_q(interval, rxq)                    # add actually-received period to the queue           
        last_real_T_ms = this_real_T_ms


if __name__ == '__main__':
    start = ms_time()


    in_processor = RNNBeatProcessor(**kwargs)
    beat_processor = DBNBeatTrackingProcessor(**kwargs)
    out_processor = [beat_processor, beat_callback]
    processor = IOProcessor(in_processor, out_processor)
    process_online(processor,  **kwargs)
    
