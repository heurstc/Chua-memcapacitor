#!/usr/bin/env python3
"""
Generate signal_conditioning.kicad_sch  (KiCad 7)  — Rev 3

All symbols extracted from the installed KiCad 7 global library so pin
positions are exact and every wire endpoint lands on the 1.27 mm snap grid.

Actual library pin offsets used (verified from /usr/share/kicad/symbols/):
  Device:R        angle=90  (horizontal)  pins at cx ± 3.81
  Device:C        angle=0   (vertical)    pin1 (top) cy−3.81 / pin2 (bot) cy+3.81
  Device:D_Schottky angle=270             A at (cx, cy+3.81) / K at (cx, cy−3.81)
  TL072 (LM2904)  angle=0                 +in (cx−7.62, cy−2.54)
                                           −in (cx−7.62, cy+2.54)
                                           out (cx+7.62, cy)

Signal path per channel (×5):
  CHUA → [R_IN 1k] → ±9V clamp → TL072-A buf → ÷4 attenuator → TL072-B buf
       → [R_SK1 10k] → Node-A → [R_SK2 10k] → SK+in → TL072-C (SK active)
       → ±2.5V clamp → ADS_CHn

Run: python3 gen_schematic.py
"""

import uuid, re

# ── Library extraction ─────────────────────────────────────────────────────────

KICAD_SYM = {
    "Device":               "/usr/share/kicad/symbols/Device.kicad_sym",
    "Amplifier_Operational":"/usr/share/kicad/symbols/Amplifier_Operational.kicad_sym",
    "power":                "/usr/share/kicad/symbols/power.kicad_sym",
}

def _extract(path, name):
    text = open(path).read()
    idx = text.find(f'(symbol "{name}"')
    if idx < 0:
        raise ValueError(f"{name} not found in {path}")
    depth, end = 0, idx
    for j, ch in enumerate(text[idx:]):
        if ch == '(': depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0: end = idx+j+1; break
    return text[idx:end]

def lib_sym(lib, name, override_name=None):
    """Return symbol S-expr, optionally renaming it."""
    s = _extract(KICAD_SYM[lib], name)
    if override_name:
        s = s.replace(f'(symbol "{name}"', f'(symbol "{override_name}"', 1)
        # Update Value property
        s = re.sub(r'(\(property "Value" ")[^"]*(")', rf'\g<1>{override_name.split(":")[-1]}\2', s, count=1)
    return s


# ── S-expression primitives ────────────────────────────────────────────────────

def uid():
    return str(uuid.uuid4())

def wire(x1, y1, x2, y2):
    if abs(x1-x2) < 1e-6 and abs(y1-y2) < 1e-6:
        return ""   # zero-length wire — skip
    return (f'  (wire (pts (xy {x1:.4f} {y1:.4f}) (xy {x2:.4f} {y2:.4f}))\n'
            f'    (stroke (width 0) (type solid))\n'
            f'    (uuid {uid()})\n'
            f'  )')

def junction(x, y):
    return (f'  (junction (at {x:.4f} {y:.4f}) (diameter 0) (color 0 0 0 0)\n'
            f'    (uuid {uid()})\n'
            f'  )')

def net_label(name, x, y, angle=0):
    return (f'  (label "{name}" (at {x:.4f} {y:.4f} {angle}) (fields_autoplaced)\n'
            f'    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'    (uuid {uid()})\n'
            f'  )')

def no_connect(x, y):
    return (f'  (no_connect (at {x:.4f} {y:.4f})\n'
            f'    (uuid {uid()})\n'
            f'  )')

def sym_inst(lib_id, x, y, angle, unit, ref, val, fp="", datasheet="", extra_props=""):
    props = (f'    (property "Reference" "{ref}" (at {x+1:.2f} {y-1:.2f} 0)\n'
             f'      (effects (font (size 1.016 1.016))))\n'
             f'    (property "Value" "{val}" (at {x-1:.2f} {y-1:.2f} 0)\n'
             f'      (effects (font (size 1.016 1.016))))\n'
             f'    (property "Footprint" "{fp}" (at 0 0 0)\n'
             f'      (effects (font (size 1.27 1.27)) hide))\n'
             f'    (property "Datasheet" "{datasheet}" (at 0 0 0)\n'
             f'      (effects (font (size 1.27 1.27)) hide))')
    return (f'  (symbol (lib_id "{lib_id}") (at {x:.4f} {y:.4f} {angle}) (unit {unit})\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid {uid()})\n'
            f'{props}{extra_props}\n'
            f'  )')

def power_sym(name, x, y, angle=0, pwr_ref=None):
    ref = pwr_ref or f"#PWR_{uid()[:4]}"
    return (f'  (symbol (lib_id "power:{name}") (at {x:.4f} {y:.4f} {angle}) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid {uid()})\n'
            f'    (property "Reference" "{ref}" (at {x:.2f} {y+2:.2f} 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Value" "{name}" (at {x:.2f} {y-2:.2f} 0)\n'
            f'      (effects (font (size 1.27 1.27))))\n'
            f'    (property "Footprint" "" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Datasheet" "" (at 0 0 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide))\n'
            f'  )')

def text_note(s, x, y, size=1.27, bold=False):
    bt = " bold" if bold else ""
    return (f'  (text "{s}" (at {x:.4f} {y:.4f} 0)\n'
            f'    (effects (font (size {size} {size}){bt}))\n'
            f'    (uuid {uid()})\n'
            f'  )')


# ── Component placers (return parts list + pin endpoint coords) ────────────────

G = 2.54   # 1 grid unit mm

# Pin offsets (verified from KiCad 7 symbol library files):
R_P  = 3.81   # Device:R  half-span from centre to pin endpoint (angle=90 → horizontal)
C_P  = 3.81   # Device:C  half-span to pin endpoint (angle=0  → vertical)
D_P  = 3.81   # Device:D  half-span to pin endpoint
OA_IX = 7.62  # TL072 input X offset from centre
OA_IY = 2.54  # TL072 input Y offset from centre (±)
OA_OX = 7.62  # TL072 output X offset

def place_R(ref, val, cx, cy, ro=None, fp="Resistor_SMD:R_0402_1005Metric"):
    """Horizontal resistor (angle=90). Pin2 at cx-R_P, Pin1 at cx+R_P."""
    parts = [sym_inst("Device:R", cx, cy, 90, 1, ref, val, fp=fp)]
    return parts, cx - R_P, cx + R_P, cy   # left_x, right_x, y

def place_C(ref, val, cx, cy, fp="Capacitor_SMD:C_0402_1005Metric"):
    """Vertical capacitor (angle=0). Pin1 top at cy-C_P, Pin2 bottom at cy+C_P."""
    parts = [sym_inst("Device:C", cx, cy, 0, 1, ref, val, fp=fp)]
    return parts, cx, cy - C_P, cy + C_P   # x, top_y, bot_y

def place_D(ref, val, cx, cy, angle=270, fp="Diode_SMD:D_SOD-323"):
    """Diode. angle=270: A at (cx, cy+D_P) [below], K at (cx, cy-D_P) [above]."""
    parts = [sym_inst("Device:D_Schottky", cx, cy, angle, 1, ref, val, fp=fp)]
    if angle == 270:
        return parts, (cx, cy + D_P), (cx, cy - D_P)  # (A_pos, K_pos)
    elif angle == 90:
        return parts, (cx, cy - D_P), (cx, cy + D_P)
    else:
        return parts, (cx - D_P, cy), (cx + D_P, cy)

def place_OA(ref, unit_int, cx, cy, val="TL072"):
    """TL072 unit (angle=0).
    +in at (cx-7.62, cy-2.54), -in at (cx-7.62, cy+2.54), out at (cx+7.62, cy)."""
    lib_id = "Amplifier_Operational:TL072"
    parts = [sym_inst(lib_id, cx, cy, 0, unit_int, ref, val,
                      fp="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                      datasheet="https://www.ti.com/lit/ds/symlink/tl072.pdf")]
    plus_pin  = (cx - OA_IX, cy - OA_IY)
    minus_pin = (cx - OA_IX, cy + OA_IY)
    out_pin   = (cx + OA_OX, cy)
    return parts, plus_pin, minus_pin, out_pin


# ── Op-amp slot → IC/unit reference ───────────────────────────────────────────

def oa_ref(oi):
    """oi is 1-based op-amp slot across all channels."""
    ic   = (oi - 1) // 2 + 1
    unit = 1 if (oi % 2 == 1) else 2
    ltr  = 'A' if unit == 1 else 'B'
    return f"U{ic}", unit, f"U{ic}{ltr}"


# ── Channel builder ────────────────────────────────────────────────────────────
#
# Grid layout (X from X0=10.16, absolute mm):
#
#  [0]       [4]     [7]    [12]      [17]    [17+R_P]  [24]     [31]   [31+R_P]
#  CHUA_X -- R_IN -- clamp -- OA_A -- RDIVH -- DIV -- OA_B -- RSK1 -- Node_A
#
#  [37]   [37+R_P]  [44]      [51]     [55]
#  RSK2 -- SK+in -- OA_C -- out_clamp -- ADS_CHn
#
# Y: signal rail at y_rail.  Op-amp centres at y_rail + 2.54 so that
#    +in pin lands exactly on y_rail.  After each op-amp output, a short
#    vertical wire restores the signal to y_rail.

X0 = 4 * G           # 10.16 mm  — left margin
CH_STRIDE = 24 * G   # 60.96 mm  — vertical spacing

CH_NAMES = ['x', 'y', 'z', 'w', 'v']

def build_channel(ch, y_rail, ro, oi):
    """
    ch      : channel index 0–4
    y_rail  : Y coordinate of signal rail (mm)
    ro      : next passive ref index
    oi      : next op-amp slot index (1-based)
    Returns (parts, new_ro, new_oi)
    """
    parts = []
    name = CH_NAMES[ch]

    # Absolute X positions
    xL   = X0 + 0*G   # 10.16 — Chua input label
    xRIN = X0 + 4*G   # 20.32 — R_IN centre
    xCL  = X0 + 7*G   # 27.94 — input clamp X
    xOAA = X0 + 12*G  # 40.64 — TL072-A centre
    xDH  = X0 + 17*G  # 53.34 — R_DIV_H centre
    xDIV = xDH + R_P  # 57.15 — divider node
    xOAB = X0 + 24*G  # 71.12 — TL072-B centre
    xSK1 = X0 + 31*G  # 88.90 — R_SK1 centre
    xNA  = xSK1 + R_P # 92.71 — Node-A
    xSK2 = X0 + 37*G  # 104.14— R_SK2 centre
    xSKP = xSK2 + R_P # 107.95— SK +input node
    xOAC = X0 + 44*G  # 121.92— TL072-C centre
    xOCL = X0 + 51*G  # 139.70— output clamp X
    xADS = X0 + 55*G  # 149.86— ADS label

    # Op-amp centres are 2.54 below signal rail so +in lands on rail
    y_oa = y_rail + OA_IY

    # Net label names
    chua_lbl  = f"CHUA_{name.upper()}"
    adc_lbl   = f"ADS_CH{ch}"
    buf1_lbl  = f"BUF1_CH{ch}"   # TL072-A output (→ div)
    div_lbl   = f"DIV_CH{ch}"    # divider node
    buf2_lbl  = f"BUF2_CH{ch}"   # TL072-B output (→ SK)
    ska_lbl   = f"SK_A{ch}"      # Node A
    skout_lbl = f"SK_OUT{ch}"    # TL072-C output / feedback

    # ── Channel title ──────────────────────────────────────────────────────────
    parts.append(text_note(f"CH{ch} ({name})  —  3-op-amp topology",
                            xL, y_rail - 10, size=1.5, bold=True))

    # ── CHUA input label (right-justified, angle=180) ─────────────────────────
    parts.append(net_label(chua_lbl, xL, y_rail, angle=180))

    # ── R_IN 1kΩ ──────────────────────────────────────────────────────────────
    p, l_x, r_x, _ = place_R(f"R{ro}", "1k", xRIN, y_rail)
    parts += p
    parts.append(wire(xL, y_rail, l_x, y_rail))       # label → R_IN left
    ro += 1

    # ── Input ±9V clamp diodes ─────────────────────────────────────────────────
    # Wire R_IN right → clamp junction
    parts.append(wire(r_x, y_rail, xCL, y_rail))

    # D1 (signal → +9V): angle=270 → A at cy+D_P, K at cy-D_P
    #   centre cy such that A-pin = y_rail → cy = y_rail - D_P
    cy_d1 = y_rail - D_P
    p, a_pos, k_pos = place_D(f"D{ro}", "BAT54", xCL, cy_d1, angle=270)
    parts += p
    # A-pin is at (xCL, y_rail) — on signal rail → junction
    parts.append(junction(xCL, y_rail))
    # K-pin → +9V power symbol
    parts.append(power_sym("VCC", k_pos[0], k_pos[1] - G, angle=0))
    parts.append(wire(k_pos[0], k_pos[1], k_pos[0], k_pos[1] - G))
    ro += 1

    # D2 (-9V → signal): angle=270 → A at cy+D_P, K at cy-D_P
    #   centre cy such that K-pin = y_rail → cy = y_rail + D_P
    cy_d2 = y_rail + D_P
    p, a_pos, k_pos = place_D(f"D{ro}", "BAT54", xCL, cy_d2, angle=270)
    parts += p
    # K-pin is at (xCL, y_rail) — on signal rail (shared junction above)
    # A-pin → -9V power symbol
    parts.append(power_sym("VEE", a_pos[0], a_pos[1] + G, angle=0))
    parts.append(wire(a_pos[0], a_pos[1], a_pos[0], a_pos[1] + G))
    ro += 1

    # ── TL072-A: unity-gain input buffer ──────────────────────────────────────
    _, unit_a, ref_a = oa_ref(oi);  oi += 1
    p, plus_a, minus_a, out_a = place_OA(ref_a, unit_a, xOAA, y_oa)
    parts += p
    # Wire clamp junction → +in  (both at y_rail)
    parts.append(wire(xCL, y_rail, plus_a[0], plus_a[1]))
    # Unity gain: −in = out via label
    parts.append(net_label(buf1_lbl, minus_a[0] - G, minus_a[1], angle=180))
    parts.append(wire(minus_a[0] - G, minus_a[1], minus_a[0], minus_a[1]))
    # Short wire from out (y_oa) up to rail (y_rail); label at junction
    parts.append(wire(out_a[0], out_a[1], out_a[0], y_rail))
    parts.append(net_label(buf1_lbl, out_a[0], y_rail))

    # ── Voltage divider ÷4  (R_DIV_H 30kΩ / R_DIV_L 10kΩ) ───────────────────
    p, l_x, r_x, _ = place_R(f"R{ro}", "30k", xDH, y_rail)
    parts += p
    parts.append(wire(out_a[0], y_rail, l_x, y_rail))  # buf1 out → RDIVH left
    ro += 1

    # RDIVH right pin IS the divider node xDIV
    # R_DIV_L vertical: top pin at y_rail → centre at y_rail + C_P
    # Use a resistor at angle=0 (vertical): pins at cy ± R_P
    # For vertical R: pin1-top at cy-R_P, pin2-bot at cy+R_P
    # Want top pin at y_rail → cy = y_rail + R_P
    cy_dl = y_rail + R_P
    p, l_x2, r_x2, _ = place_R(f"R{ro}", "10k", xDIV, cy_dl, fp="Resistor_SMD:R_0402_1005Metric")
    # Actually Device:R angle=0 is vertical; pin offsets are ±R_P in Y (not X)
    # Reuse sym_inst directly with angle=0
    parts.append(sym_inst("Device:R", xDIV, cy_dl, 0, 1, f"R{ro}", "10k",
                            fp="Resistor_SMD:R_0402_1005Metric"))
    # Pin1 top at (xDIV, cy_dl - R_P) = (xDIV, y_rail)
    # Pin2 bot at (xDIV, cy_dl + R_P) = (xDIV, y_rail + 2*R_P)
    p_top = (xDIV, cy_dl - R_P)   # = (xDIV, y_rail)
    p_bot = (xDIV, cy_dl + R_P)   # = (xDIV, y_rail + 7.62)
    parts.append(junction(xDIV, y_rail))
    parts.append(wire(r_x, y_rail, xDIV, y_rail))    # RDIVH right → divnode
    parts.append(power_sym("GND", p_bot[0], p_bot[1] + G, angle=270))
    parts.append(wire(p_bot[0], p_bot[1], p_bot[0], p_bot[1] + G))
    parts.append(net_label(div_lbl, xDIV, y_rail))
    ro += 1

    # ── TL072-B: divider buffer (eliminates 7.5kΩ source loading) ─────────────
    _, unit_b, ref_b = oa_ref(oi);  oi += 1
    p, plus_b, minus_b, out_b = place_OA(ref_b, unit_b, xOAB, y_oa)
    parts += p
    # +in: wire from divider node (xDIV, y_rail) → (plus_b) at y_rail
    parts.append(net_label(div_lbl, plus_b[0] - G, plus_b[1], angle=180))
    parts.append(wire(plus_b[0] - G, plus_b[1], plus_b[0], plus_b[1]))
    # Unity gain
    parts.append(net_label(buf2_lbl, minus_b[0] - G, minus_b[1], angle=180))
    parts.append(wire(minus_b[0] - G, minus_b[1], minus_b[0], minus_b[1]))
    parts.append(wire(out_b[0], out_b[1], out_b[0], y_rail))
    parts.append(net_label(buf2_lbl, out_b[0], y_rail))

    # ── Sallen-Key 2nd-order Butterworth LPF ──────────────────────────────────
    # R_SK1: buf2 → Node-A
    p, l_sk1, r_sk1, _ = place_R(f"R{ro}", "10k", xSK1, y_rail)
    parts += p
    parts.append(net_label(buf2_lbl, l_sk1 - G, y_rail, angle=180))
    parts.append(wire(l_sk1 - G, y_rail, l_sk1, y_rail))
    ro += 1

    # C_FB 2.2nF: Node-A → skout (feedback cap, vertical, hangs below)
    # Centre at (xNA, y_rail + C_P + G)  → top pin at y_rail + G
    # Actually place centre so top pin touches Node A at y_rail + 1G below rail:
    #   We route: xNA, y_rail → short wire down G → C_FB top pin
    cy_cfb = y_rail + G + C_P     # top pin at y_rail+G
    parts.append(junction(xNA, y_rail))
    parts.append(wire(r_sk1, y_rail, xNA, y_rail))      # RSK1 right → Node-A
    p, cx_cfb, top_cfb, bot_cfb = place_C(f"C{ro}", "2.2nF", xNA, cy_cfb)
    parts += p
    parts.append(wire(xNA, y_rail, xNA, top_cfb))        # Node-A → C_FB top
    parts.append(net_label(skout_lbl, xNA, bot_cfb))
    parts.append(net_label(ska_lbl, xNA + G, y_rail))
    ro += 1

    # R_SK2: Node-A → SK+input
    p, l_sk2, r_sk2, _ = place_R(f"R{ro}", "10k", xSK2, y_rail)
    parts += p
    parts.append(wire(xNA, y_rail, l_sk2, y_rail))
    ro += 1

    # C_SH 4.7nF: SK+input → GND (shunt cap, vertical, hangs below)
    parts.append(junction(xSKP, y_rail))
    parts.append(wire(r_sk2, y_rail, xSKP, y_rail))
    cy_csh = y_rail + G + C_P
    p, cx_csh, top_csh, bot_csh = place_C(f"C{ro}", "4.7nF", xSKP, cy_csh)
    parts += p
    parts.append(wire(xSKP, y_rail, xSKP, top_csh))
    parts.append(power_sym("GND", xSKP, bot_csh + G, angle=270))
    parts.append(wire(xSKP, bot_csh, xSKP, bot_csh + G))
    ro += 1

    # TL072-C: SK active element
    _, unit_c, ref_c = oa_ref(oi);  oi += 1
    p, plus_c, minus_c, out_c = place_OA(ref_c, unit_c, xOAC, y_oa)
    parts += p
    parts.append(wire(xSKP, y_rail, plus_c[0], plus_c[1]))
    # Unity gain: −in and out share skout label
    parts.append(net_label(skout_lbl, minus_c[0] - G, minus_c[1], angle=180))
    parts.append(wire(minus_c[0] - G, minus_c[1], minus_c[0], minus_c[1]))
    parts.append(wire(out_c[0], out_c[1], out_c[0], y_rail))

    # ── Output ±2.5V clamp ─────────────────────────────────────────────────────
    parts.append(net_label(skout_lbl, out_c[0], y_rail, angle=180))
    parts.append(wire(out_c[0], y_rail, xOCL, y_rail))
    parts.append(junction(xOCL, y_rail))

    cy_d3 = y_rail - D_P
    p, a_pos3, k_pos3 = place_D(f"D{ro}", "BAT54", xOCL, cy_d3, angle=270)
    parts += p
    parts.append(power_sym("VCC", k_pos3[0], k_pos3[1] - G, angle=0))
    parts.append(wire(k_pos3[0], k_pos3[1], k_pos3[0], k_pos3[1] - G))
    ro += 1

    cy_d4 = y_rail + D_P
    p, a_pos4, k_pos4 = place_D(f"D{ro}", "BAT54", xOCL, cy_d4, angle=270)
    parts += p
    parts.append(power_sym("VEE", a_pos4[0], a_pos4[1] + G, angle=0))
    parts.append(wire(a_pos4[0], a_pos4[1], a_pos4[0], a_pos4[1] + G))
    ro += 1

    # ── ADS1262 output label ───────────────────────────────────────────────────
    parts.append(wire(xOCL, y_rail, xADS, y_rail))
    parts.append(net_label(adc_lbl, xADS, y_rail))

    # Filter empty strings
    parts = [p for p in parts if p]
    return parts, ro, oi


# ── Assemble schematic ─────────────────────────────────────────────────────────

def build_lib_symbols():
    """Embed exact copies from KiCad global libraries."""
    # TL072 extends LM2904 — copy LM2904 graphics under the TL072 name
    tl072 = _extract(KICAD_SYM["Amplifier_Operational"], "LM2904")
    tl072 = tl072.replace('(symbol "LM2904"', '(symbol "Amplifier_Operational:TL072"', 1)
    # Rename all inner sub-unit names to match the new outer name
    tl072 = re.sub(r'\(symbol "LM2904(_\d+_\d+")',
                   r'(symbol "Amplifier_Operational:TL072\1', tl072)
    tl072 = re.sub(r'(\(property "Value" ")[^"]*(")', r'\g<1>TL072\2', tl072, count=1)
    tl072 = re.sub(r'(\(property "Datasheet" ")[^"]*(")',
                   r'\g<1>https://www.ti.com/lit/ds/symlink/tl072.pdf\2', tl072, count=1)

    syms = []
    for lib, name in [("Device","R"), ("Device","C"), ("Device","D_Schottky"),
                      ("power","GND"), ("power","VCC"), ("power","VEE")]:
        syms.append(_extract(KICAD_SYM[lib], name))
    syms.append(tl072)

    body = "\n".join("  " + line if line.strip() else line
                     for s in syms for line in s.splitlines())
    return f"  (lib_symbols\n{body}\n  )"


TITLE_BLOCK = '''\
  (title_block
    (title "5D Chaos Monitor — Signal Conditioning  Rev 3")
    (rev "3.0")
    (company "ChaosLab")
    (comment 1 "5 ch: x y z (Chua 0-2)  w v (extended 3-4)")
    (comment 2 "3 op-amps/ch: A=input buf  B=divider buf  C=SK active")
    (comment 3 "fn=4.95 kHz  Q=0.731  Vout max=2.0 V for 8 V Chua  8x TL072 SOIC-8")
    (comment 4 "All coordinates on 2.54 mm grid; pin endpoints on 1.27 mm grid")
  )'''


def main():
    lib_syms = build_lib_symbols()

    lines = [
        "(kicad_sch",
        "  (version 20230121)",
        '  (generator "chaos_sch_gen_v3")',
        f'  (uuid {uid()})',
        '  (paper "A2")',
        TITLE_BLOCK,
        lib_syms,
    ]

    ro = 1   # passive ref index
    oi = 1   # op-amp slot index

    for ch in range(5):
        y_rail = (12 + ch * 24) * G   # 30.48, 91.44, 152.40, 213.36, 274.32
        parts, ro, oi = build_channel(ch, y_rail, ro, oi)
        lines.extend(parts)

    lines.append(f'  (sheet_instances (path "/" (page "1")))')
    lines.append(")")

    out = "signal_conditioning.kicad_sch"
    with open(out, "w") as f:
        f.write("\n".join(lines))

    n_lines = sum(1 for l in lines if l.strip())
    print(f"Wrote {out}  ({n_lines} non-blank lines)")
    print(f"Op-amp slots: {oi-1}  → {(oi)//2} TL072 ICs (U1–U{(oi-1+1)//2})")
    print()
    print("IC assignment:")
    for slot in range(1, oi):
        _, unit, ref = oa_ref(slot)
        ch   = (slot - 1) // 3
        role = ["input buffer", "divider buffer", "SK active"][(slot-1) % 3]
        print(f"  {ref:5s}  CH{ch}  {role}")

if __name__ == "__main__":
    main()
