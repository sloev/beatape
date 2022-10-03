#!/usr/bin/env python
# encoding: utf-8
''' 9/25/2020
Beat4aBlast v1.0
Based on madmom
Sends averaged beat period out onboard tty port, 1Mbps
Tracks and sends beat phase detects missing beats based on average prior intervals
    To allow receivers to synchronize for half-speed, or for motor direction sync
WebSockets Server to accept IR remote control commands. Forwards to serial port.
'''

import _thread
import threading
import time
from pythonosc import udp_client
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder
from time import perf_counter


def ms_time():
    return perf_counter() * 1000.0



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



def average_q(q):
    sum = 0
    items = 0
    for elem in list(q.queue):
        sum += elem
        items += 1
    if items == 0:
        return 0
    return sum / items

class FuckOff(Exception):
    pass

class BeatCaller:
    def __init__(self):
        self.last_real_T_ms = 0
        self.beat_phase = 0
        self.depth = 5
        self.rxq = queue.Queue(self.depth)  # queue of corrected-if-necessary timing of received beats
        self.max_period = bpm_to_ms_period(MIN_BPM)
        self.min_period = bpm_to_ms_period(MAX_BPM)


    def into_my_q(self, o, q):
        if q.qsize() == self.depth:
            q.get()  # dump one
        q.put(o)

    def beat_callback(self, beats, output=None):
        if self.event.is_set():
            self.bpm_queue.put(None)
            print("got poison")
            raise FuckOff()

        if len(beats) > 0:
            b = beats[0]
            self.this_real_T_ms = ms_time()              # milliseconds since epoch
            interval = (self.this_real_T_ms - self.last_real_T_ms)     # determine milliseconds since last beat
            if interval > 3 * self.max_period:   # no beats for a while clear the queue first to start over
                for elem in list(self.rxq.queue):
                    self.rxq.get()  # dump each
                self.last_real_T_ms = self.this_real_T_ms
                return

            if self.rxq.qsize() > 0:  # if we have at least one entry in the queue
                if interval >= self.min_period and interval <= 3 * self.max_period:  # if this interval looks valid
                    ta = average_q(self.rxq)                  # average over all entries in the queue
        # determine if we have skipped any beats
                    m = round(interval / ta)  # if = 1, no beat skipped if = 2, one beat skipped, etc.
                    if (m < 1):
                        m = 1
                    adjusted_interval = interval / m
                    self.into_my_q(adjusted_interval, self.rxq)                    # add actually-received period to the queue

                    self.beat_phase = (m + self.beat_phase) % 4  # next phase please
                    beat_char = chr(ord('a') + self.beat_phase)
                    s = "T{}{:.0f}\r".format(beat_char, adjusted_interval)
                    bpm = ms_period_to_bpm(adjusted_interval)
                    self.bpm_queue.put(bpm)

                
                    # print("T{}{:.0f} ({:.0f})".format(beat_char, adjusted_interval, bpm))
            else:   # queue just filling
                self.into_my_q(interval, self.rxq)                    # add actually-received period to the queue           
            self.last_real_T_ms = self.this_real_T_ms

    def run(self, bpm_queue, event):
        try:
            self.bpm_queue = bpm_queue
            self.event = event
            in_processor = RNNBeatProcessor(**kwargs)
            beat_processor = DBNBeatTrackingProcessor(**kwargs)
            out_processor = [beat_processor, self.beat_callback]
            processor = IOProcessor(in_processor, out_processor)
            process_online(processor,  **kwargs)
        except FuckOff:
            return

def run(bpm_queue, event):
    bc = BeatCaller()
    bc.run(bpm_queue, event)




   
    
