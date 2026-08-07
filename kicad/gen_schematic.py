#!/usr/bin/env python3
"""
Generate signal_conditioning.kicad_sch  (KiCad 7 format)

Signal path per channel (×5):
  Chua output
    → R_IN 1kΩ          (current-limit / ESD)
    → BAT54 ±9V clamps
    → TL072-A            (unity-gain input buffer)
    → R_DIV_HI 30kΩ / R_DIV_LO 10kΩ   (÷4 attenuator → ±2V max)
    → TL072-B            (unity-gain divider buffer — ELIMINATES source loading
                          on SK filter, restoring fn to ideal 4.95 kHz)
    → 2nd-order Sallen-Key Butterworth LPF @ 4.95 kHz
        R_SK1 = R_SK2 = 10kΩ
        C_FB  = 2.2 nF  (node-A to output, feedback cap)
        C_SH  = 4.7 nF  (non-inv input to GND, shunt cap)
        Q = √(4.7/2.2)/2 ≈ 0.73 ≈ 0.707  (Butterworth) ✓
        fn = 1/(2π·10k·√(2.2n·4.7n)) ≈ 4.95 kHz ✓
        (source loading → Rth = 0 with TL072-B buffer: fn is ideal) ✓
    → TL072-C            (SK active element / unity-gain output buffer)
    → BAT54 ±2.5V clamps (ADS1262 AVDD/AVSS protection)
    → ADS_CHn label → ADS1262

IC count: 3 op-amps per channel × 5 channels = 15 units
          TL072 is dual → 8 ICs total (U1–U8), U8B spare.
          Upgrade to TL074 (quad) to reduce to 4 ICs.

Run:   python3 gen_schematic.py
Output: signal_conditioning.kicad_sch  (open directly in KiCad 7)
"""

import uuid

GRID      = 1.27    # mm, standard KiCad schematic grid
CH_STRIDE = 60.0    # mm vertical spacing between channels (extra room for 3 op-amps)
X0        = 10.0    # mm left margin

def uid():
    return str(uuid.uuid4())


# ── S-expression primitives ────────────────────────────────────────────────────

def wire(x1, y1, x2, y2):
    return (f'  (wire (pts (xy {x1} {y1}) (xy {x2} {y2}))\n'
            f'    (stroke (width 0) (type solid))\n'
            f'    (uuid {uid()})\n'
            f'  )')

def net_label(name, x, y, angle=0):
    return (f'  (label "{name}" (at {x} {y} {angle}) (fields_autoplaced)\n'
            f'    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'    (uuid {uid()})\n'
            f'  )')

def power_sym(lib_name, value, x, y, angle=0, ref_suffix="01"):
    return (f'  (symbol (lib_id "power:{lib_name}") (at {x} {y} {angle}) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid {uid()})\n'
            f'    (property "Reference" "#PWR{ref_suffix}" (at {x} {y+2.54} 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Value" "{value}" (at {x} {y-2.54} 0)\n'
            f'      (effects (font (size 1.27 1.27)))))')

def resistor(ref, value, x, y, angle=0, fp="Resistor_SMD:R_0402_1005Metric"):
    return (f'  (symbol (lib_id "Device:R") (at {x} {y} {angle}) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid {uid()})\n'
            f'    (property "Reference" "{ref}" (at {x+1.016} {y-1.27} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Value" "{value}" (at {x-1.016} {y-1.27} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Footprint" "{fp}" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Datasheet" "~" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide)))')

def capacitor(ref, value, x, y, angle=0, fp="Capacitor_SMD:C_0402_1005Metric"):
    return (f'  (symbol (lib_id "Device:C") (at {x} {y} {angle}) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid {uid()})\n'
            f'    (property "Reference" "{ref}" (at {x+1.524} {y-1.27} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Value" "{value}" (at {x-1.524} {y-1.27} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Footprint" "{fp}" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Datasheet" "~" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide)))')

def diode(ref, value, x, y, angle=0, fp="Diode_SMD:D_SOD-323"):
    return (f'  (symbol (lib_id "Device:D_Schottky") (at {x} {y} {angle}) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid {uid()})\n'
            f'    (property "Reference" "{ref}" (at {x} {y-2.54} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Value" "{value}" (at {x} {y+2.54} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Footprint" "{fp}" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Datasheet" "~" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide)))')

def opamp_unit(ref, unit_int, x, y, value="TL072"):
    """Place one unit of a TL072 dual op-amp.
    unit_int=1 → unit A (pins 3,2,1),  unit_int=2 → unit B (pins 5,6,7)."""
    return (f'  (symbol (lib_id "Amplifier_Operational:TL072")'
            f' (at {x} {y} 0) (unit {unit_int})\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid {uid()})\n'
            f'    (property "Reference" "{ref}" (at {x+5.08} {y-5.08} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Value" "{value}" (at {x+5.08} {y-6.35} 0)\n'
            f'      (effects (font (size 1.016 1.016))))\n'
            f'    (property "Footprint" "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Datasheet"'
            f' "https://www.ti.com/lit/ds/symlink/tl072.pdf" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide)))')

def text(s, x, y, size=1.27, bold=False):
    bold_token = " bold" if bold else ""
    return (f'  (text "{s}" (at {x} {y} 0)\n'
            f'    (effects (font (size {size} {size}){bold_token})))')


# ── Op-amp slot → IC/unit reference ───────────────────────────────────────────
# 15 op-amp units total (5 ch × 3).  TL072 packs 2 per SOIC-8 → 8 ICs (U1–U8).
# oa_idx is 1-based and increments across all channels.

def oa_ref(oa_idx):
    """Return (IC_str, unit_int, full_ref_str) for op-amp slot oa_idx."""
    ic   = (oa_idx - 1) // 2 + 1
    unit = 1 if (oa_idx % 2 == 1) else 2
    ltr  = 'A' if unit == 1 else 'B'
    return f"U{ic}", unit, f"U{ic}{ltr}"


# ── Channel builder ────────────────────────────────────────────────────────────
#
# X layout (mm from X0):
#   x+0   : CHUA input label
#   x+8   : R_IN (1kΩ)
#   x+22  : Input clamp diodes D_hi / D_lo
#   x+38  : TL072-A  (input buffer)           [op-amp slot oi+0]
#   x+52  : R_DIV_HI (30kΩ) / R_DIV_LO (10kΩ)  divider
#   x+68  : TL072-B  (divider buffer) ← NEW   [op-amp slot oi+1]
#   x+88  : R_SK1 (10kΩ)
#   x+98  : Node A  (C_FB hangs here)
#   x+108 : R_SK2 (10kΩ)  →  SK +in node (C_SH to GND)
#   x+120 : TL072-C  (SK active element)       [op-amp slot oi+2]
#   x+135 : Output clamp diodes D_hi / D_lo
#   x+148 : ADS label

def build_channel(ch, y0, ro, oi):
    """Build one signal-conditioning channel.

    ch  : channel index 0–4
    y0  : Y coordinate of the signal rail (mm)
    ro  : next passive reference designator index
    oi  : next op-amp slot index (1-based, shared across channels)

    Returns (parts_list, new_ro, new_oi).
    """
    parts = []
    x = X0

    CH_NAMES  = ['x', 'y', 'z', 'w', 'v']
    name      = CH_NAMES[ch]
    chua_lbl  = f"CHUA_{name.upper()}"
    adc_lbl   = f"ADS_CH{ch}"
    div_lbl   = f"DIV{ch}"       # voltage divider output node
    buf2_lbl  = f"B2_CH{ch}"    # divider buffer output (feeds SK filter)
    ska_lbl   = f"SK_A{ch}"     # node A of SK filter
    skout_lbl = f"SK_OUT{ch}"   # SK output (before output clamp)

    # ── channel title ──────────────────────────────────────────────────────────
    parts.append(text(f"CH{ch}  ({name})  —  3-op-amp topology",
                      x, y0 - 9, size=1.5, bold=True))

    # ── Chua input label ───────────────────────────────────────────────────────
    parts.append(net_label(chua_lbl, x, y0, angle=180))

    # ── R_IN (1kΩ series protection) ──────────────────────────────────────────
    xr = x + 8
    parts.append(resistor(f"R{ro}", "1k", xr, y0, angle=90))
    parts.append(wire(x, y0, xr - 1.524, y0))
    ro += 1

    # ── Input clamp diodes D_hi / D_lo to ±9V ─────────────────────────────────
    x_clamp = x + 22
    parts.append(wire(xr + 1.524, y0, x_clamp, y0))

    xd1, yd1 = x_clamp, y0 - 7.62
    parts.append(diode(f"D{ro}", "BAT54", xd1, yd1, angle=270))
    parts.append(wire(x_clamp, y0, xd1, yd1 + 1.524))
    parts.append(power_sym("VCC", "+9V", xd1, yd1 - 4.064,
                            angle=0, ref_suffix=f"{ro:02d}"))
    ro += 1

    xd2, yd2 = x_clamp, y0 + 7.62
    parts.append(diode(f"D{ro}", "BAT54", xd2, yd2, angle=90))
    parts.append(wire(x_clamp, y0, xd2, yd2 - 1.524))
    parts.append(power_sym("VEE", "-9V", xd2, yd2 + 4.064,
                            angle=180, ref_suffix=f"{ro:02d}"))
    ro += 1

    # ── TL072-A: unity-gain input buffer ──────────────────────────────────────
    x_oa = x + 38
    _, unit_a, ref_a = oa_ref(oi);  oi += 1
    parts.append(opamp_unit(ref_a, unit_a, x_oa, y0))
    parts.append(wire(x_clamp, y0, x_oa - 7.62, y0))   # clamp → +in
    x_out_a = x_oa + 7.62

    # ── Voltage divider ÷4  (30kΩ / 10kΩ) ────────────────────────────────────
    x_div = x + 52
    parts.append(resistor(f"R{ro}", "30k", x_div, y0, angle=90))
    parts.append(wire(x_out_a, y0, x_div - 1.524, y0))
    ro += 1

    x_divnode = x_div + 1.524                   # right pin of R_DIV_HI = junction
    xrl = x_divnode + 5.08
    parts.append(resistor(f"R{ro}", "10k", xrl, y0 + 5.08, angle=0))
    parts.append(wire(x_divnode, y0, xrl - 1.524, y0))
    parts.append(power_sym("GND", "GND", xrl + 4.064, y0,
                            angle=270, ref_suffix=f"{ro:02d}"))
    ro += 1
    parts.append(net_label(div_lbl, x_divnode, y0))

    # ── TL072-B: divider unity-gain buffer  ← NEW ─────────────────────────────
    # Eliminates Rth = 7.5 kΩ source loading on the SK filter.
    # With this buffer: R1_eff = R_SK1 = 10 kΩ → fn = ideal 4.95 kHz.
    x_ob_div = x + 68
    _, unit_b, ref_b = oa_ref(oi);  oi += 1
    parts.append(opamp_unit(ref_b, unit_b, x_ob_div, y0))
    # Route divider node label → +in of TL072-B
    parts.append(net_label(div_lbl, x_ob_div - 9.0, y0, angle=180))
    parts.append(wire(x_ob_div - 9.0, y0, x_ob_div - 7.62, y0))
    x_out_db = x_ob_div + 7.62
    parts.append(wire(x_out_db, y0, x_out_db + 2.54, y0))
    parts.append(net_label(buf2_lbl, x_out_db + 2.54, y0))

    # ── Sallen-Key 2nd-order Butterworth LPF (source is TL072-B output = 0Ω) ──
    #
    #   buf2_lbl ──[RSK1 10k]── NA ──[RSK2 10k]── NSKPLUS ──(+)TL072-C── NSKOUT
    #                            |                    |                      |
    #                          [CFB 2.2n]          [CSH 4.7n]          (−) tied
    #                            |                    |                 to NSKOUT
    #                          NSKOUT               GND                (unity gain)
    #
    #   fn = 1/(2π·10k·√(2.2n·4.7n)) = 4.95 kHz   Q = √(4.7/2.2)/2 = 0.731 ✓

    x_ska = x + 98           # position of Node A

    # RSK1 (10kΩ): buf2_lbl → NA
    xrsk1 = x_ska - 10.16
    parts.append(resistor(f"R{ro}", "10k", xrsk1, y0, angle=90))
    parts.append(net_label(buf2_lbl, xrsk1 - 3.0, y0, angle=180))
    parts.append(wire(xrsk1 - 3.0, y0, xrsk1 - 1.524, y0))
    parts.append(wire(xrsk1 + 1.524, y0, x_ska, y0))
    ro += 1

    # C_SK_FB (2.2nF): NA → skout_lbl  (feedback cap)
    xc1, yc1 = x_ska, y0 + 10.16
    parts.append(capacitor(f"C{ro}", "2.2nF", xc1, yc1, angle=0))
    parts.append(wire(x_ska, y0, xc1, yc1 - 1.524))
    parts.append(net_label(skout_lbl, xc1, yc1 + 1.524))
    parts.append(net_label(ska_lbl, x_ska, y0))
    ro += 1

    # RSK2 (10kΩ): NA → SK +in node
    x_ob = x + 120           # TL072-C center
    xrsk2 = x_ob - 17.78
    parts.append(resistor(f"R{ro}", "10k", xrsk2, y0, angle=90))
    parts.append(wire(x_ska, y0, xrsk2 - 1.524, y0))
    x_sk_plus = x_ob - 7.62
    parts.append(wire(xrsk2 + 1.524, y0, x_sk_plus, y0))
    ro += 1

    # C_SK_SH (4.7nF): SK +in → GND  (shunt cap)
    xc2, yc2 = x_sk_plus, y0 + 8.89
    parts.append(capacitor(f"C{ro}", "4.7nF", xc2, yc2, angle=0))
    parts.append(wire(x_sk_plus, y0, xc2, yc2 - 1.524))
    parts.append(power_sym("GND", "GND", xc2, yc2 + 4.064,
                            angle=270, ref_suffix=f"{ro:02d}"))
    ro += 1

    # TL072-C: SK active element (unity-gain buffer)
    _, unit_c, ref_c = oa_ref(oi);  oi += 1
    parts.append(opamp_unit(ref_c, unit_c, x_ob, y0))
    x_out_b = x_ob + 7.62
    parts.append(wire(x_out_b, y0, x_out_b + 2.54, y0))
    parts.append(net_label(skout_lbl, x_out_b + 2.54, y0))

    # ── Output clamp to ±2.5V (ADS1262 AVDD/AVSS protection) ─────────────────
    x_oclamp = x + 140
    parts.append(net_label(skout_lbl, x_oclamp - 5.08, y0, angle=180))
    parts.append(wire(x_oclamp - 5.08, y0, x_oclamp, y0))

    xd3, yd3 = x_oclamp, y0 - 7.62
    parts.append(diode(f"D{ro}", "BAT54", xd3, yd3, angle=270))
    parts.append(wire(x_oclamp, y0, xd3, yd3 + 1.524))
    parts.append(power_sym("VCC", "+2V5", xd3, yd3 - 4.064,
                            angle=0, ref_suffix=f"{ro:02d}"))
    ro += 1

    xd4, yd4 = x_oclamp, y0 + 7.62
    parts.append(diode(f"D{ro}", "BAT54", xd4, yd4, angle=90))
    parts.append(wire(x_oclamp, y0, xd4, yd4 - 1.524))
    parts.append(power_sym("VEE", "-2V5", xd4, yd4 + 4.064,
                            angle=180, ref_suffix=f"{ro:02d}"))
    ro += 1

    # ── ADS1262 output label ───────────────────────────────────────────────────
    parts.append(wire(x_oclamp, y0, x_oclamp + 7.62, y0))
    parts.append(net_label(adc_lbl, x_oclamp + 7.62, y0))

    return parts, ro, oi


# ── lib_symbols (minimal embedded definitions) ────────────────────────────────

LIB_SYMBOLS = '''\
  (lib_symbols
    (symbol "Device:R"
      (pin_numbers hide) (pin_names (offset 0))
      (in_bom yes) (on_board yes)
      (property "Reference" "R" (at 1.016 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "R" (at -1.016 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "R_0_1"
        (rectangle (start -1.016 -0.508) (end 1.016 0.508)
          (stroke (width 0.2032) (type default)) (fill (type none))))
      (symbol "R_1_1"
        (pin passive line (at -1.524 0 0) (length 0.508)
          (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 1.524 0 180) (length 0.508)
          (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))))
    (symbol "Device:C"
      (pin_names (offset 0.254))
      (in_bom yes) (on_board yes)
      (property "Reference" "C" (at 1.016 -0.254 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "C" (at 1.016 0.508 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Footprint" "" (at 0.508 -3.81 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "C_0_1"
        (polyline (pts (xy -2.032 -0.508) (xy 2.032 -0.508))
          (stroke (width 0.508) (type default)) (fill (type none)))
        (polyline (pts (xy -2.032 0.508) (xy 2.032 0.508))
          (stroke (width 0.508) (type default)) (fill (type none))))
      (symbol "C_1_1"
        (pin passive line (at 0 1.524 270) (length 1.016)
          (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -1.524 90) (length 1.016)
          (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))))
    (symbol "Device:D_Schottky"
      (pin_names (offset 0))
      (in_bom yes) (on_board yes)
      (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "D_Schottky" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "D_Schottky_0_1"
        (polyline (pts (xy -1.016 -1.016) (xy -1.016 1.016))
          (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -1.016 0) (xy 1.016 0))
          (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy 1.016 -1.016) (xy -1.016 0) (xy 1.016 1.016))
          (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -1.524 -1.016) (xy -1.016 -1.016) (xy -1.016 -0.508))
          (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -0.508 1.016) (xy -1.016 1.016) (xy -1.016 0.508))
          (stroke (width 0.254) (type default)) (fill (type none))))
      (symbol "D_Schottky_1_1"
        (pin passive line (at -2.54 0 0) (length 1.524)
          (name "A" (effects (font (size 1.27 1.27)))) (number "A" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 2.54 0 180) (length 1.524)
          (name "K" (effects (font (size 1.27 1.27)))) (number "K" (effects (font (size 1.27 1.27)))))))
    (symbol "Amplifier_Operational:TL072"
      (pin_names (offset 0))
      (in_bom yes) (on_board yes)
      (property "Reference" "U" (at 5.08 5.08 0) (effects (font (size 1.27 1.27))))
      (property "Value" "TL072" (at 5.08 3.556 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "https://www.ti.com/lit/ds/symlink/tl072.pdf" (at 0 0 0)
        (effects (font (size 1.27 1.27)) hide))
      (symbol "TL072_1_1"
        (polyline (pts (xy -5.08 -5.08) (xy -5.08 5.08) (xy 5.08 0) (xy -5.08 -5.08))
          (stroke (width 0.254) (type default)) (fill (type none)))
        (pin input line (at -7.62 2.54 0) (length 2.54)
          (name "+" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27)))))
        (pin input line (at -7.62 -2.54 0) (length 2.54)
          (name "-" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
        (pin output line (at 7.62 0 180) (length 2.54)
          (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27))))))
      (symbol "TL072_2_1"
        (polyline (pts (xy -5.08 -5.08) (xy -5.08 5.08) (xy 5.08 0) (xy -5.08 -5.08))
          (stroke (width 0.254) (type default)) (fill (type none)))
        (pin input line (at -7.62 2.54 0) (length 2.54)
          (name "+" (effects (font (size 1.27 1.27)))) (number "5" (effects (font (size 1.27 1.27)))))
        (pin input line (at -7.62 -2.54 0) (length 2.54)
          (name "-" (effects (font (size 1.27 1.27)))) (number "6" (effects (font (size 1.27 1.27)))))
        (pin output line (at 7.62 0 180) (length 2.54)
          (name "~" (effects (font (size 1.27 1.27)))) (number "7" (effects (font (size 1.27 1.27))))))
      (symbol "TL072_3_1"
        (pin power_in line (at 0 7.62 270) (length 2.54)
          (name "V+" (effects (font (size 1.27 1.27)))) (number "8" (effects (font (size 1.27 1.27)))))
        (pin power_in line (at 0 -7.62 90) (length 2.54)
          (name "V-" (effects (font (size 1.27 1.27)))) (number "4" (effects (font (size 1.27 1.27)))))))
    (symbol "power:GND"
      (property "Reference" "#PWR" (at 0 -6.35 0) (effects (font (size 1.27 1.27)) hide))
      (property "Value" "GND" (at 0 -3.81 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "GND_0_1"
        (polyline (pts (xy 0 0) (xy 0 -1.27))
          (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy -1.27 -1.27) (xy 0 -2.54) (xy 1.27 -1.27))
          (stroke (width 0) (type default)) (fill (type none))))
      (symbol "GND_1_1"
        (pin power_in line (at 0 0 270) (length 0)
          (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))))
    (symbol "power:VCC"
      (property "Reference" "#PWR" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) hide))
      (property "Value" "VCC" (at 0 3.556 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "VCC_0_1"
        (polyline (pts (xy -1.016 -0.508) (xy 0 1.016) (xy 1.016 -0.508))
          (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 0 0) (xy 0 -2.54))
          (stroke (width 0) (type default)) (fill (type none))))
      (symbol "VCC_1_1"
        (pin power_in line (at 0 -2.54 90) (length 0)
          (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))))
    (symbol "power:VEE"
      (property "Reference" "#PWR" (at 0 3.556 0) (effects (font (size 1.27 1.27)) hide))
      (property "Value" "VEE" (at 0 -3.556 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "VEE_0_1"
        (polyline (pts (xy -1.016 0.508) (xy 0 -1.016) (xy 1.016 0.508))
          (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 0 0) (xy 0 2.54))
          (stroke (width 0) (type default)) (fill (type none))))
      (symbol "VEE_1_1"
        (pin power_in line (at 0 2.54 270) (length 0)
          (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))))
  )'''


TITLE_BLOCK = '''\
  (title_block
    (title "5D Chaos Monitor — Signal Conditioning Front-End  (Rev 2)")
    (rev "2.0")
    (company "ChaosLab")
    (comment 1 "5 channels: x,y,z (Chua ch0-2)  w,v (extended ch3-4)")
    (comment 2 "3 op-amps per channel: A=input buf  B=divider buf (eliminates SK loading)  C=SK active")
    (comment 3 "15 TL072 units total → 8 SOIC-8 ICs (U1-U8); U8B spare. Alt: 4× TL074 (quad).")
    (comment 4 "fn = 4.95 kHz (ideal, no source loading)  Q = 0.731  Vout max = ±2.0 V for ±8 V Chua")
  )'''


def main():
    lines = [
        f'(kicad_sch',
        f'  (version 20230121)',
        f'  (generator "chaos_sch_gen_v2")',
        f'  (uuid {uid()})',
        f'  (paper "A2")',
        TITLE_BLOCK,
        LIB_SYMBOLS,
    ]

    ro = 1    # passive ref designator index
    oi = 1    # op-amp slot index (1-based, shared across all 5 channels)

    for ch in range(5):
        y0 = 30.0 + ch * CH_STRIDE
        parts, ro, oi = build_channel(ch, y0, ro, oi)
        lines.extend(parts)

    lines.append(f'  (sheet_instances (path "/" (page "1")))')
    lines.append(')')

    out_path = "signal_conditioning.kicad_sch"
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Wrote {out_path}  ({sum(1 for l in lines if l.strip())} non-blank lines)")
    print(f"Op-amp slots used: {oi - 1}  →  {(oi - 1 + 1) // 2} TL072 ICs  (U1–U{(oi-1+1)//2})")
    print()
    print("Open in KiCad 7:  File → Open → signal_conditioning.kicad_sch")
    print("Accept library re-link when prompted.")
    print()
    print("IC assignment:")
    for slot in range(1, oi):
        _, unit, ref = oa_ref(slot)
        ch   = (slot - 1) // 3
        role = ['input buffer', 'divider buffer (NEW)', 'SK active'][(slot - 1) % 3]
        print(f"  {ref:5s}  CH{ch} {role}")


if __name__ == "__main__":
    main()
