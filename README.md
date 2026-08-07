# Chua-memcapacitor — 5D Chaos Monitor

Real-time acquisition and visualisation of a 5-dimensional chaotic attractor using a **Seeed Studio XIAO RP2350** and two **ADS1262 32-bit ADCs**, streaming to Linux at **12 kHz per channel** over USB CDC.

---

## System Overview

```
Chua Circuit (±8 V)
  │
  ▼
Signal Conditioning Board  (×5 channels)
  │  R_IN 1kΩ → ±9V clamp → TL072-A input buffer
  │  → ÷4 attenuator (30k/10k) → TL072-B divider buffer
  │  → Sallen-Key 2nd-order Butterworth LPF @ 4.95 kHz
  │  → ±2.5V clamp → ADS_CHn
  ▼
XIAO RP2350
  │  Core 1: tight-poll SPI sampling (ADS1262 × 2)
  │  Core 0: USB CDC packetiser (14-byte frames, XOR checksum)
  ▼
Linux Host  /dev/ttyACM0
  │  capture.py  — packet parser, drop/error stats
  │  buffer.py   — lock-free circular numpy buffers
  │  plotter.py  — real-time 3D attractor + 2D projections
  ▼
matplotlib FuncAnimation @ 30 Hz
```

---

## Hardware

| Part | Role |
|---|---|
| Seeed XIAO RP2350 | Dual-core Cortex-M33 MCU, USB FS CDC |
| ADS1262 × 2 | 32-bit delta-sigma ADC, 38,400 SPS max |
| TL072 × 8 | Signal conditioning op-amps (SOIC-8) |
| BAT54 Schottky × 20 | Input (±9V) and output (±2.5V) clamps |
| R 0402, C 0402 C0G | Divider and Sallen-Key filter passives |

**Channel mapping:**

| Channel | Chua variable | ADC |
|---|---|---|
| CH0 | x | ADS1262-0 AIN0 |
| CH1 | y | ADS1262-0 AIN1 |
| CH2 | z | ADS1262-0 AIN2 |
| CH3 | w | ADS1262-1 AIN0 |
| CH4 | v | ADS1262-1 AIN1 |

**SPI0 pin assignments (RP2350):**

| Signal | GPIO |
|---|---|
| SCK | GP6 |
| MOSI | GP7 |
| MISO | GP4 |
| ADC0 CS / DRDY / RST | GP5 / GP0 / GP1 |
| ADC1 CS / DRDY / RST | GP3 / GP2 / GP28 |

---

## Signal Conditioning (Rev 2)

Each of the 5 channels uses a **3-op-amp topology**:

```
Chua ──[R_IN 1kΩ]──[±9V clamp]──[TL072-A]──[÷4]──[TL072-B]──[SK LPF]──[TL072-C]──[±2.5V clamp]──► ADS1262
```

- **TL072-A** — unity-gain input buffer; isolates Chua source impedance
- **÷4 attenuator** — 30kΩ/10kΩ voltage divider; maps ±8V Chua → ±2V
- **TL072-B** — unity-gain divider buffer; eliminates 7.5kΩ Thevenin source loading that would shift the filter cutoff from 4.95 kHz to 3.74 kHz
- **Sallen-Key LPF** — 2nd-order Butterworth, fn = 4.95 kHz, Q = 0.731; R1=R2=10kΩ, C_FB=2.2nF C0G, C_SH=4.7nF C0G
- **TL072-C** — SK active element / output buffer
- **±2.5V clamp** — BAT54 Schottky protecting ADS1262 AVDD/AVSS rails

IC count: 15 TL072 units → 8 SOIC-8 packages (U1–U8, U8B spare).

---

## Firmware

Built with the **Pico SDK** and **TinyUSB**.

```
firmware/
├── CMakeLists.txt
└── src/
    ├── ads1262.h / .c      ADS1262 SPI driver
    ├── ring_buffer.h       Lock-free SPSC ring buffer (4096 samples, ARM DMB)
    ├── sampler.h / .c      Core 1 entry — tight-poll sampling loop
    ├── main.c              Core 0 — USB CDC packetiser
    ├── tusb_config.h       TinyUSB configuration
    └── usb_descriptors.c   CDC descriptor
```

**ADS1262 configuration:**
- Data rate: 38,400 SPS, filter: SINC1 (mandatory for single-cycle mux settling)
- PGA bypassed; internal 2.5V reference

**USB packet format (14 bytes):**

```
[0xAD][0xC0][ch][seq_lo][seq_hi][ts0][ts1][ts2][ts3][val0][val1][val2][val3][XOR]
  sync         chan  seq (LE16)    timestamp µs (LE32)  value (LE32)   checksum
```

**Build:**
```bash
mkdir firmware/build && cd firmware/build
cmake .. -DPICO_BOARD=seeed_xiao_rp2350
make -j$(nproc)
# flash: hold BOOT, connect USB, copy .uf2 to RPI-RP2 drive
```

---

## Host Software

```
host/
├── capture.py    PacketParser — serial reader thread, sync/checksum/drop detection
├── buffer.py     ChannelBuffer — circular numpy arrays; SampleStore for 5 channels
├── plotter.py    FuncAnimation plots: 3D attractor, xy/xz projections, time series
└── main.py       Entry point — fanout thread, optional CSV logging
```

**Install dependencies:**
```bash
pip install -r host/requirements.txt
```

**Run:**
```bash
python3 host/main.py /dev/ttyACM0
# options:
#   --fps 30        animation frame rate
#   --trail 10000   number of points in attractor trail
#   --save FILE     log raw samples to CSV
```

The plotter opens a live window showing:
- **Left:** 3D x/y/z attractor trajectory
- **Top centre:** x–y phase portrait
- **Top right:** x–z phase portrait
- **Bottom centre:** w–v projection
- **Bottom right:** per-channel time series + sample rate / error stats

---

## SPICE Simulation

```
spice/
├── signal_cond.spice    ngspice netlist (BAT54 + TL072 behavioral models)
├── plot_response.py     scipy Bode / step / pole-zero plots
└── run_ngspice.sh       run simulation + plot (falls back to scipy-only if no ngspice)
```

```bash
cd spice
./run_ngspice.sh
```

Produces `ac_bode.dat`, `tran_1k.dat`, `tran_8k.dat`, `tran_step.dat` and a Bode plot PNG.

---

## KiCad Schematic

```
kicad/
├── gen_schematic.py              Python generator — run to rebuild .kicad_sch
├── signal_conditioning.kicad_sch KiCad 7 schematic (A2, 5 channels)
├── signal_conditioning.kicad_pro KiCad project file
└── bom.csv                       Bill of materials
```

To regenerate the schematic after editing the generator:
```bash
python3 kicad/gen_schematic.py
```

Open `signal_conditioning.kicad_sch` directly in KiCad 7.

---

## Throughput Budget

| Parameter | Value |
|---|---|
| Channels | 5 |
| Effective SPS per channel | ~12,800 (CH0–2) / ~19,200 (CH3–4) |
| Packet size | 14 bytes |
| Raw USB data rate | ~840 kB/s |
| USB FS CDC practical limit | ~1 MB/s |

---

## License

MIT
