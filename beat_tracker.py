#!/usr/bin/env python
# encoding: utf-8
""" 9/25/2020
Beat4aBlast v1.0
Based on madmom
Sends averaged beat period out onboard tty port, 1Mbps
Tracks and sends beat phase detects missing beats based on average prior intervals
    To allow receivers to synchronize for half-speed, or for motor direction sync
WebSockets Server to accept IR remote control commands. Forwards to serial port.
"""
import logging
import time
import asyncio
import threading

from time import perf_counter
def ms_time():
    return time.time() * 1000.0


import numpy as np
from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor
from madmom.models import BEATS_LSTM
from madmom.processors import IOProcessor, process_online
import time
from collections import deque

_END = object()

TWOPI = 2 * np.pi
RADPERDEGREE = 45 / np.pi
DAMP = 0.5
MAX_BPM = 250
MIN_BPM = 55

# GLOBALS


kwargs = dict(
    num_threads=2,
    fps=100,
    correct=True,
    infile=None,
    outfile=None,
    max_bpm=MAX_BPM,
    min_bpm=MIN_BPM,
    nn_files=[
        BEATS_LSTM[1],
    ],  # , BEATS_LSTM[1]
    num_frames=1,
    list_stream_input_device=0,
    #    stream_input_device = 2,
    online=True,
    # verbose = 1
)



class BeatCaller:
    def __init__(self, async_queue,  loop=None, max_intervals_in_average=5, min_bpm=70, max_bpm=250):
        self.last_beat_s_since_program_start = 0
        self.beat_phase = 0
        self.depth = 5
        self.delta = 0


        self.next_beat_epoch_seconds = 0

        self.adjusted_intervals = deque(maxlen=max_intervals_in_average)

        self.max_period = 60.0 / min_bpm
        self.min_period = 60.0 / max_bpm
        self.exception = None

        self.async_queue = async_queue
        self.loop = loop or asyncio.get_event_loop()


    def beat_callback(self, beats, output=None):
        now_seconds_epoch = time.time()

        if len(beats)==0:
            return 

        beat_s_since_program_start = perf_counter()
        interval = beat_s_since_program_start - self.last_beat_s_since_program_start

        if (
            interval > 3 * self.max_period
        ):  # no beats for a while clear the queue first to start over
            self.adjusted_intervals.clear()
            self.last_beat_s_since_program_start = beat_s_since_program_start
            self.delta = 0
            return        

        if len(self.adjusted_intervals)>0 and interval >= self.min_period:
            average_interval = np.mean(self.adjusted_intervals)

            bpm = 60.0 / average_interval

            if self.next_beat_epoch_seconds>0:
                self.delta = self.next_beat_epoch_seconds - now_seconds_epoch
            self.next_beat_epoch_seconds = now_seconds_epoch + interval + (self.delta*0.5)
        
            self.output_handler(self.delta, self.next_beat_epoch_seconds, bpm)
           

        self.adjusted_intervals.appendleft(interval)
        self.last_beat_s_since_program_start = beat_s_since_program_start
    
    def output_handler(self, delta, next_beat_epoch_seconds, bpm):
        item = "{:.3f} {:.3f}".format(bpm, next_beat_epoch_seconds)
        # This runs outside the event loop thread, so we
        # must use thread-safe API to talk to the queue.
        e = asyncio.run_coroutine_threadsafe(self.async_queue.put(item), self.loop).result()


    def run(self):
        try:
            in_processor = RNNBeatProcessor(**kwargs)
            beat_processor = DBNBeatTrackingProcessor(**kwargs)
            out_processor = [beat_processor, self.beat_callback]
            processor = IOProcessor(in_processor, out_processor)
            process_online(processor, **kwargs)
        except Exception as e:
            logging.exception("output_handler_error")
            self.exception = e
        finally:
            asyncio.run_coroutine_threadsafe(self.async_queue.put(_END), self.loop).result()



    async def async_iter(self):
        """Wrap blocking iterator into an asynchronous one"""
        _END = object()

        self.t = threading.Thread(target=self.run)
        self.t.start()
        try:
            while True:
                next_item = await self.async_queue.get()
                if next_item is _END:
                    break
                yield next_item
        except:
            logging.exception("error")
    
        if self.exception is not None:
            # the iterator has raised, propagate the exception
            raise self.exception

if __name__ == "__main__":
    q = asyncio.Queue()

    bc = BeatCaller(q)

    async def main():
        async for item in bc.async_iter():
            print("received from async_iter:", item)
        

    asyncio.get_event_loop().run_until_complete(main())
