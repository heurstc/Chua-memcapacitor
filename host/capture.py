"""
USB CDC packet reader for the 5D chaos monitor firmware.

Packet layout (14 bytes):
  [0]    0xAD  sync0
  [1]    0xC0  sync1
  [2]          channel  (uint8,  0–4)
  [3–4]        seq      (uint16 LE, per-channel wrapping counter)
  [5–8]        ts_us    (uint32 LE, µs since boot)
  [9–12]       value    (int32  LE, raw 32-bit ADC reading)
  [13]         checksum (XOR of bytes 2–12)
"""

import struct
import threading
from collections import namedtuple
from queue import Full, Queue

import serial

SYNC       = bytes([0xAD, 0xC0])
PKT_LEN    = 14
_PAYLOAD   = struct.Struct('<BHIiB')   # ch, seq, ts_us, value, checksum
N_CHANNELS = 5
VREF       = 2.5   # ADS1262 internal reference (V)
FULLSCALE  = 2**31

Sample = namedtuple('Sample', ['channel', 'seq', 'timestamp_us', 'voltage'])


def _to_volts(raw: int) -> float:
    return raw / FULLSCALE * VREF


def _checksum_ok(payload: bytes) -> bool:
    # payload[0..10] = bytes after sync; payload[11] = received checksum
    csum = 0
    for b in payload[:11]:
        csum ^= b
    return csum == payload[11]


class PacketParser:
    """
    Background thread: reads the serial port, finds sync, validates
    checksum, and pushes Sample namedtuples to *queue*.

    Stats dict is written by the reader thread and read by the UI thread
    without a lock — small inaccuracies are acceptable in the status bar.
    """

    def __init__(self, port: str, queue: Queue):
        self.port  = port
        self.queue = queue
        self.stats = {
            'received':  [0] * N_CHANNELS,
            'dropped':   [0] * N_CHANNELS,   # detected via seq gaps
            'csum_err':  0,
            'sync_skip': 0,                  # bytes skipped re-syncing
        }
        self._last_seq = [None] * N_CHANNELS
        self._running  = False
        self._thread   = None

    # ── public ────────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True,
                                         name='chaos-reader')
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    # ── internals ─────────────────────────────────────────────────────────────

    def _run(self):
        # baudrate is ignored by the kernel for CDC-ACM devices; USB speed used
        ser = serial.Serial(self.port, baudrate=115200,
                            timeout=0.02, write_timeout=1)
        try:
            self._parse_stream(ser)
        finally:
            ser.close()

    def _parse_stream(self, ser: serial.Serial):
        buf = bytearray()
        while self._running:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                buf.extend(chunk)

            while len(buf) >= PKT_LEN:
                idx = buf.find(SYNC)

                if idx == -1:
                    # No sync found — keep the last byte in case it's 0xAD
                    self.stats['sync_skip'] += len(buf) - 1
                    buf = buf[-1:]
                    break

                if idx > 0:
                    self.stats['sync_skip'] += idx
                    del buf[:idx]

                if len(buf) < PKT_LEN:
                    break  # wait for more bytes

                payload = bytes(buf[2:PKT_LEN])   # 12 bytes

                if not _checksum_ok(payload):
                    self.stats['csum_err'] += 1
                    del buf[:1]    # advance one byte and search for next sync
                    continue

                ch, seq, ts_us, raw, _ = _PAYLOAD.unpack(payload)

                if 0 <= ch < N_CHANNELS:
                    prev = self._last_seq[ch]
                    if prev is not None:
                        gap = (seq - prev - 1) & 0xFFFF
                        self.stats['dropped'][ch] += gap
                    self._last_seq[ch] = seq
                    self.stats['received'][ch] += 1

                    s = Sample(ch, seq, ts_us, _to_volts(raw))
                    try:
                        self.queue.put_nowait(s)
                    except Full:
                        pass   # consumer is behind; drop rather than block

                del buf[:PKT_LEN]
