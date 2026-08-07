"""
Thread-safe rolling buffers for five ADC channels.

ChannelBuffer: lock-protected circular numpy array.
               latest(n) always returns data oldest→newest.

SampleStore:   one ChannelBuffer per channel + per-channel rate estimator.
"""

import threading
import time

import numpy as np


class ChannelBuffer:
    def __init__(self, capacity: int = 32768):
        self._cap  = capacity
        self._ts   = np.zeros(capacity, dtype=np.float64)   # µs
        self._volt = np.zeros(capacity, dtype=np.float32)   # V
        self._ptr  = 0      # index of next write slot
        self._full = False
        self._lock = threading.Lock()

    def push(self, ts_us: float, voltage: float):
        with self._lock:
            self._ts  [self._ptr] = ts_us
            self._volt[self._ptr] = voltage
            self._ptr = (self._ptr + 1) % self._cap
            if self._ptr == 0:
                self._full = True

    def latest(self, n: int):
        """Return (timestamps_us, voltages) for the last *n* samples,
        ordered oldest → newest.  May return fewer than *n* if the
        buffer has not filled yet."""
        with self._lock:
            size = self._cap if self._full else self._ptr
            n = min(n, size)
            if n == 0:
                return np.empty(0, np.float64), np.empty(0, np.float32)

            end   = self._ptr
            start = (end - n) % self._cap

            if start < end:
                return (self._ts  [start:end].copy(),
                        self._volt[start:end].copy())
            else:
                ts   = np.concatenate([self._ts  [start:], self._ts  [:end]])
                volt = np.concatenate([self._volt[start:], self._volt[:end]])
                return ts, volt

    def __len__(self):
        with self._lock:
            return self._cap if self._full else self._ptr


class SampleStore:
    """Fan-out from the packet queue into per-channel buffers."""

    def __init__(self, n_channels: int, capacity: int = 32768):
        self.channels = [ChannelBuffer(capacity) for _ in range(n_channels)]
        self._n       = n_channels
        self._count   = [0]   * n_channels   # samples since last rate update
        self._rate    = [0.0] * n_channels   # Hz, updated every second
        self._t_rate  = [time.monotonic()] * n_channels

    def push(self, sample) -> None:
        ch = sample.channel
        self.channels[ch].push(sample.timestamp_us, sample.voltage)

        self._count[ch] += 1
        now = time.monotonic()
        dt  = now - self._t_rate[ch]
        if dt >= 1.0:
            self._rate   [ch] = self._count[ch] / dt
            self._count  [ch] = 0
            self._t_rate [ch] = now

    def rate(self, ch: int) -> float:
        return self._rate[ch]
