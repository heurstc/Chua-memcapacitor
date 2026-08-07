#!/usr/bin/env python3
"""
5D Chaos Monitor — Linux host capture + real-time attractor plot.

Usage:
    python main.py [PORT] [--fps N] [--trail N] [--save FILE]

    PORT   serial device (default /dev/ttyACM0)
    --fps  plot refresh rate in Hz (default 30)
    --trail  attractor trail length in samples (default 10000)
    --save  path to write a raw CSV log (ch,seq,ts_us,voltage)

The firmware streams 14-byte framed packets at ~60 kSPS aggregate
(5 channels × ~12 kSPS).  This process runs two threads:
  reader thread  — serial port → packet queue
  fanout thread  — packet queue → per-channel rolling buffers
The main thread runs the matplotlib animation loop.
"""

import argparse
import io
import signal
import sys
import threading
from queue import Queue

from capture import PacketParser, N_CHANNELS
from buffer  import SampleStore
from plotter import AttractorPlotter

QUEUE_DEPTH   = 131_072
BUFFER_DEPTH  = 32_768   # samples per channel (~2.7 s at 12 kSPS)


def main():
    ap = argparse.ArgumentParser(description='5D Chaos Monitor')
    ap.add_argument('port',    nargs='?', default='/dev/ttyACM0',
                    help='CDC-ACM serial device (default: /dev/ttyACM0)')
    ap.add_argument('--fps',   type=int,  default=30,
                    help='Plot refresh rate Hz (default: 30)')
    ap.add_argument('--trail', type=int,  default=10_000,
                    help='Attractor trail length in samples (default: 10000)')
    ap.add_argument('--save',  metavar='FILE', default=None,
                    help='Write raw CSV log to FILE')
    args = ap.parse_args()

    queue = Queue(maxsize=QUEUE_DEPTH)
    store = SampleStore(N_CHANNELS, capacity=BUFFER_DEPTH)
    reader = PacketParser(args.port, queue=queue)

    save_fh: io.TextIOWrapper | None = None
    if args.save:
        save_fh = open(args.save, 'w', buffering=1)
        save_fh.write('channel,seq,timestamp_us,voltage_V\n')
        print(f'Logging raw samples to {args.save}')

    stop = threading.Event()

    def fanout():
        while not stop.is_set():
            try:
                s = queue.get(timeout=0.02)
            except Exception:
                continue
            store.push(s)
            if save_fh:
                save_fh.write(
                    f'{s.channel},{s.seq},{s.timestamp_us},{s.voltage:.9f}\n'
                )

    reader.start()
    fan = threading.Thread(target=fanout, daemon=True, name='fanout')
    fan.start()

    print(f'Reading from {args.port}  —  Ctrl-C or close the window to stop')

    def _shutdown(*_):
        stop.set()
        reader.stop()
        if save_fh:
            save_fh.close()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    plotter = AttractorPlotter(store, reader, fps=args.fps)
    # Override trail length from CLI
    import plotter as _plt_mod
    _plt_mod.TRAIL      = args.trail

    plotter.run()   # blocks until window closed
    _shutdown()


if __name__ == '__main__':
    main()
