#!/usr/bin/env python3
"""
Signal conditioning filter response — scipy analytical simulation.

Runs standalone with no ngspice dependency.
If ngspice output files are present in the same directory, overlays them.

Usage:
    python plot_response.py            # pure scipy
    python plot_response.py --ngspice  # overlay ngspice dat files too
"""

import argparse
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import signal

# ── Circuit parameters ────────────────────────────────────────────────────────

R_IN    = 1e3       # Ω  input series protection
R_DIV_H = 30e3      # Ω  attenuator top
R_DIV_L = 10e3      # Ω  attenuator bottom
R_SK1   = 10e3      # Ω  Sallen-Key R1
R_SK2   = 10e3      # Ω  Sallen-Key R2
C_FB    = 2.2e-9    # F  feedback capacitor (node-A to output)
C_SH    = 4.7e-9    # F  shunt capacitor (+in to GND)

V_CHUA_PEAK = 8.0   # V  representative Chua double-scroll peak

# ── Derived quantities ────────────────────────────────────────────────────────

# Voltage divider (ideal, no SK loading)
K_ideal = R_DIV_L / (R_DIV_H + R_DIV_L)          # 0.25

# Thevenin equivalent of the divider as seen by the SK filter input
R_TH  = R_DIV_H * R_DIV_L / (R_DIV_H + R_DIV_L)  # 7.5 kΩ
K_TH  = K_ideal                                    # Thevenin voltage gain

# Effective SK filter parameters accounting for divider source impedance
R1_EFF = R_TH + R_SK1   # 17.5 kΩ  (R_SK1 in series with Rth)
R2_EFF = R_SK2           # 10.0 kΩ

# 2nd-order LP prototype (unity-gain SK, real poles at Butterworth Q=0.707)
WN_IDEAL  = 1 / (R_SK1 * np.sqrt(C_FB * C_SH))   # unloaded natural freq (rad/s)
Q_IDEAL   = np.sqrt(C_SH / C_FB) / 2              # ≈ 0.731

WN_LOADED = 1 / np.sqrt(R1_EFF * R2_EFF * C_FB * C_SH)   # loaded ωn
Q_LOADED  = (np.sqrt(R1_EFF * R2_EFF * C_FB * C_SH)
             / (C_FB * (R1_EFF + R2_EFF)))                 # ≈ 0.703


def make_tf(K, wn, Q):
    """Return scipy TransferFunction: K·ωn²/(s²+(ωn/Q)s+ωn²)."""
    return signal.TransferFunction([K * wn**2], [1, wn / Q, wn**2])


# Complete transfer functions (Vin → Vout)
TF_IDEAL  = make_tf(K_ideal, WN_IDEAL,  Q_IDEAL)
TF_LOADED = make_tf(K_TH,    WN_LOADED, Q_LOADED)


def print_design_summary():
    print("=" * 60)
    print("Signal Conditioning Filter — Design Summary")
    print("=" * 60)
    print(f"  Attenuator gain (ideal):    {K_ideal:.4f}  ({20*np.log10(K_ideal):.2f} dB)")
    print(f"  Divider Thevenin R:         {R_TH/1e3:.1f} kΩ")
    print()
    print("  ── Unloaded (ideal, no source impedance) ──")
    print(f"     fn   = {WN_IDEAL/(2*np.pi)/1e3:.3f} kHz")
    print(f"     Q    = {Q_IDEAL:.4f}")
    print()
    print("  ── Loaded (Rth = 7.5 kΩ in series with RSK1) ──")
    print(f"     R1_eff = {R1_EFF/1e3:.1f} kΩ")
    print(f"     fn     = {WN_LOADED/(2*np.pi)/1e3:.3f} kHz  ← actual cutoff")
    print(f"     Q      = {Q_LOADED:.4f}  (Butterworth target: 0.707)")
    print()

    freqs_check = [1e3, 3e3, 5e3, 6e3, 10e3, 20e3]
    print("  ── Frequency response (loaded TF) ──")
    print(f"  {'freq':>8s}  {'|H| dB':>9s}  {'phase °':>9s}  {'Vout pk (from 8V Chua)':>22s}")
    for f in freqs_check:
        w = 2 * np.pi * f
        _, h = signal.freqs(TF_LOADED.num, TF_LOADED.den, [w])
        db  = 20 * np.log10(abs(h[0]))
        ph  = np.degrees(np.angle(h[0]))
        vout = V_CHUA_PEAK * abs(h[0])
        print(f"  {f/1e3:>7.1f}k  {db:>9.2f}  {ph:>9.1f}  {vout:>18.3f} V pk")
    print()
    print(f"  Nyquist (6 kHz):  alias rejection = "
          f"{_db_at(TF_LOADED, 6e3):.1f} dB")
    print(f"  Max Vout from ±{V_CHUA_PEAK} V Chua: "
          f"±{V_CHUA_PEAK * abs(K_TH):.2f} V  (within ADS1262 ±2.5 V) ✓")
    print("=" * 60)


def _db_at(tf, f):
    w = 2 * np.pi * f
    _, h = signal.freqs(tf.num, tf.den, [w])
    return 20 * np.log10(abs(h[0]))


# ── Plotting ──────────────────────────────────────────────────────────────────

BG    = '#0a0a0a'
GRID  = '#1e1e1e'
TXT   = '#cccccc'
DIM   = '#555555'
C0    = '#00d4ff'   # ideal
C1    = '#ff6b35'   # loaded
C2    = '#7bc67e'   # ngspice (if present)
CHUA  = '#ffd700'   # Chua signal


def _ax(ax, title):
    ax.set_facecolor(BG)
    ax.spines[:].set_color(GRID)
    ax.tick_params(colors=DIM, labelsize=8)
    ax.grid(True, color=GRID, lw=0.4, which='both')
    ax.set_title(title, color=TXT, fontsize=9, pad=4)


def plot_bode(axm, axp, ngspice_ac=None):
    f = np.logspace(0, 5.7, 3000)   # 1 Hz – 500 kHz
    w = 2 * np.pi * f

    for tf, color, label in [
        (TF_IDEAL,  C0, f'Ideal  (fn={WN_IDEAL/(2*np.pi)/1e3:.2f} kHz, Q={Q_IDEAL:.3f})'),
        (TF_LOADED, C1, f'Loaded (fn={WN_LOADED/(2*np.pi)/1e3:.2f} kHz, Q={Q_LOADED:.3f})'),
    ]:
        _, h = signal.freqs(tf.num, tf.den, w)
        db  = 20 * np.log10(np.maximum(np.abs(h), 1e-12))
        ph  = np.degrees(np.unwrap(np.angle(h)))
        axm.semilogx(f, db,  color=color, lw=1.4, label=label)
        axp.semilogx(f, ph,  color=color, lw=1.4)

    if ngspice_ac is not None:
        f_ng, mag_ng, ph_ng = ngspice_ac
        axm.semilogx(f_ng, mag_ng, color=C2, lw=1.0, ls='--', label='ngspice')
        axp.semilogx(f_ng, ph_ng,  color=C2, lw=1.0, ls='--')

    # Annotate key frequencies
    for f_mark, label_str in [
        (WN_IDEAL/(2*np.pi),  'fn ideal'),
        (WN_LOADED/(2*np.pi), 'fn loaded'),
        (6e3,                  'Nyquist'),
    ]:
        for ax in (axm, axp):
            ax.axvline(f_mark, color=DIM, lw=0.6, ls=':')
        axm.text(f_mark*1.05, axm.get_ylim()[0]+2, label_str,
                 color=DIM, fontsize=6, rotation=90, va='bottom')

    # -3 dB reference
    axm.axhline(_db_at(TF_LOADED, 1), color=DIM, lw=0.4, ls='--')
    axm.axhline(_db_at(TF_LOADED, 1) - 3, color=C1, lw=0.5, ls='--', alpha=0.5)

    axm.set_ylabel('Magnitude (dB)', color=DIM, fontsize=8)
    axm.legend(fontsize=7, loc='lower left', framealpha=0.15, labelcolor='white')
    axm.set_xlim(1, 5e5)
    axm.set_xlabel('')

    axp.set_ylabel('Phase (°)', color=DIM, fontsize=8)
    axp.set_xlabel('Frequency (Hz)', color=DIM, fontsize=8)
    axp.set_xlim(1, 5e5)


def plot_step(ax, ngspice_step=None):
    fs = 500e3    # simulation sample rate
    t  = np.arange(0, 1e-3, 1/fs)
    t_step = 100e-6

    x = np.where(t >= t_step, 4.0, 0.0)   # 4 V step (half of ±8 V Chua)

    for tf, color, label in [
        (TF_IDEAL,  C0, 'Ideal'),
        (TF_LOADED, C1, 'Loaded'),
    ]:
        _, y, _ = signal.lsim(tf, x, t)
        t_us = (t - t_step) * 1e6
        ax.plot(t_us, y, color=color, lw=1.3, label=label)

    ax.plot((t - t_step)*1e6, x, color=CHUA, lw=0.8, ls='--',
            alpha=0.6, label='Input (4 V step)')

    if ngspice_step is not None:
        t_ng, v_ng = ngspice_step
        ax.plot((t_ng - t_ng[np.argmax(np.diff(v_ng))])*1e6, v_ng,
                color=C2, lw=1.0, ls='--', label='ngspice')

    ax.set_xlim(-50, 700)
    ax.set_xlabel('Time (µs)', color=DIM, fontsize=8)
    ax.set_ylabel('Voltage (V)', color=DIM, fontsize=8)
    ax.legend(fontsize=7, framealpha=0.15, labelcolor='white')
    ax.axhline(4 * K_TH, color=DIM, lw=0.4, ls='--')   # steady-state
    ax.text(650, 4*K_TH + 0.02, f'DC: {4*K_TH:.3f} V', color=DIM, fontsize=6, ha='right')


def plot_multitone(ax):
    """Chua-like multi-tone input vs filtered output."""
    fs = 500e3
    t  = np.arange(0, 5e-3, 1/fs)

    # Chua attractor spectrum: dominant ~ 1–3 kHz, harmonics, broadband noise floor
    components = [
        (1000, 8.0, 0),        # fundamental (in-band)
        (2500, 3.0, 0.8),      # harmonic (in-band)
        (7500, 2.0, 1.2),      # out-of-band harmonic
        (15000, 1.0, 0.4),     # alias-risk component
    ]
    x = sum(A * np.sin(2*np.pi*f*t + ph) for f, A, ph in components)

    _, y, _ = signal.lsim(TF_LOADED, x, t)

    t_ms = t * 1e3
    ax.plot(t_ms, x, color=CHUA, lw=0.6, alpha=0.7, label='Chua input (sum of tones)')
    ax.plot(t_ms, y, color=C1,   lw=1.0, label='Filtered output (loaded TF)')

    # Annotation: indicate out-of-band components
    ax.text(0.05, 0.05,
            '7.5 kHz + 15 kHz components\nstrongly attenuated by SK filter',
            transform=ax.transAxes, color=DIM, fontsize=7, va='bottom')

    ax.set_xlabel('Time (ms)', color=DIM, fontsize=8)
    ax.set_ylabel('Voltage (V)', color=DIM, fontsize=8)
    ax.legend(fontsize=7, framealpha=0.15, labelcolor='white')


def plot_pole_zero(ax):
    """s-plane pole locations for both TFs."""
    for tf, color, label in [
        (TF_IDEAL,  C0, 'Ideal'),
        (TF_LOADED, C1, 'Loaded'),
    ]:
        poles = np.roots(tf.den)
        zeros = np.roots(tf.num) if len(tf.num) > 1 else []
        ax.plot(poles.real / (2*np.pi*1e3), poles.imag / (2*np.pi*1e3),
                'x', color=color, ms=10, mew=2, label=f'{label} poles')
        if len(zeros):
            ax.plot(zeros.real / (2*np.pi*1e3), zeros.imag / (2*np.pi*1e3),
                    'o', color=color, ms=6, mew=1.5, fillstyle='none')

    ax.axhline(0, color=GRID, lw=0.5)
    ax.axvline(0, color=GRID, lw=0.5)
    ax.set_xlabel('Re (kHz)', color=DIM, fontsize=8)
    ax.set_ylabel('Im (kHz)', color=DIM, fontsize=8)
    ax.legend(fontsize=7, framealpha=0.15, labelcolor='white')


# ── ngspice output parser ─────────────────────────────────────────────────────

def _load_ngspice_ac(path):
    """Parse wrdata AC output: freq Re(V1) Im(V1) ... Re(Vn) Im(Vn)."""
    try:
        d = np.loadtxt(path, comments='*')
    except Exception as e:
        print(f"[warn] Cannot load {path}: {e}")
        return None
    if d.ndim < 2 or d.shape[1] < 10:
        print(f"[warn] {path}: unexpected column count {d.shape}")
        return None
    freq     = d[:, 0]
    # Column layout: freq  Re(NIN) Im(NIN)  Re(NDIV) Im(NDIV)  Re(NA) Im(NA)
    #                      Re(NSKPLUS) Im(NSKPLUS)  Re(NSKOUT) Im(NSKOUT)
    vin_cpx  = d[:, 1] + 1j * d[:, 2]
    vout_cpx = d[:, 9] + 1j * d[:, 10]
    mag_db   = 20 * np.log10(np.abs(vout_cpx) / np.maximum(np.abs(vin_cpx), 1e-15))
    phase    = np.degrees(np.unwrap(np.angle(vout_cpx / vin_cpx)))
    return freq, mag_db, phase


def _load_ngspice_tran(path, col_in=1, col_out=2):
    """Parse wrdata TRAN output: time V1 V2 ..."""
    try:
        d = np.loadtxt(path, comments='*')
    except Exception as e:
        print(f"[warn] Cannot load {path}: {e}")
        return None
    return d[:, 0], d[:, col_out - 1]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ngspice', action='store_true',
                    help='Overlay ngspice simulation results if .dat files are present')
    ap.add_argument('--save', metavar='FILE',
                    help='Save figure to FILE instead of displaying')
    args = ap.parse_args()

    print_design_summary()

    # Optional ngspice overlays
    ng_ac   = _load_ngspice_ac('ac_bode.dat')   if args.ngspice else None
    ng_step = _load_ngspice_tran('tran_step.dat') if args.ngspice else None

    if args.ngspice:
        if ng_ac   is None: print("[info] ac_bode.dat not found — run ngspice first")
        if ng_step is None: print("[info] tran_step.dat not found — run ngspice first")

    # ── Figure ────────────────────────────────────────────────
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(16, 10), facecolor=BG)
    fig.patch.set_facecolor(BG)
    fig.suptitle('Signal Conditioning Front-End — Filter Response',
                 color=TXT, fontsize=11, y=0.98)

    gs = gridspec.GridSpec(3, 3, figure=fig,
                           hspace=0.5, wspace=0.38,
                           left=0.07, right=0.97, top=0.94, bottom=0.06)

    ax_mag  = fig.add_subplot(gs[0, :2])
    ax_ph   = fig.add_subplot(gs[1, :2], sharex=ax_mag)
    ax_step = fig.add_subplot(gs[0, 2])
    ax_tone = fig.add_subplot(gs[1, 2])
    ax_pz   = fig.add_subplot(gs[2, 2])
    ax_info = fig.add_subplot(gs[2, :2])

    for ax, title in [
        (ax_mag,  'Bode Plot — Magnitude'),
        (ax_ph,   'Bode Plot — Phase'),
        (ax_step, 'Step Response'),
        (ax_tone, 'Chua-like Multi-tone'),
        (ax_pz,   's-plane Pole Locations'),
        (ax_info, 'Key Metrics'),
    ]:
        _ax(ax, title)

    plot_bode(ax_mag, ax_ph, ng_ac)
    plot_step(ax_step, ng_step)
    plot_multitone(ax_tone)
    plot_pole_zero(ax_pz)

    # ── Metrics text panel ────────────────────────────────────
    lines = [
        f"Attenuator gain:          K  = {K_ideal:.4f}  ({20*np.log10(K_ideal):.2f} dB)",
        f"Divider Thevenin R:      Rth = {R_TH/1e3:.1f} kΩ",
        "",
        f"Unloaded  fn = {WN_IDEAL/(2*np.pi)/1e3:.3f} kHz   Q = {Q_IDEAL:.4f}",
        f"Loaded    fn = {WN_LOADED/(2*np.pi)/1e3:.3f} kHz   Q = {Q_LOADED:.4f}  ← actual",
        "",
        "Attenuation vs. ADS1262 Nyquist (6 kHz):",
        f"   @ 3.74 kHz (fn loaded):  {_db_at(TF_LOADED,WN_LOADED/(2*np.pi)):.1f} dB  (−3 dB)",
        f"   @ 5.0  kHz:              {_db_at(TF_LOADED,5e3):.1f} dB",
        f"   @ 6.0  kHz (Nyquist):    {_db_at(TF_LOADED,6e3):.1f} dB",
        f"   @ 10.0 kHz:              {_db_at(TF_LOADED,10e3):.1f} dB",
        f"   @ 20.0 kHz:              {_db_at(TF_LOADED,20e3):.1f} dB",
        "",
        f"Max Vout from ±{V_CHUA_PEAK:.0f} V Chua: ±{V_CHUA_PEAK*K_TH:.2f} V  (ADS1262 limit ±2.50 V ✓)",
        "",
        "To restore fn=5 kHz:  reduce RDIVH to 15 kΩ  (Rth → 5 kΩ, R1_eff → 15 kΩ)",
    ]
    ax_info.axis('off')
    ax_info.text(0.02, 0.95, '\n'.join(lines),
                 transform=ax_info.transAxes,
                 color=TXT, fontsize=7.5, fontfamily='monospace',
                 va='top', linespacing=1.5)

    if args.save:
        plt.savefig(args.save, dpi=150, facecolor=BG)
        print(f"Saved to {args.save}")
    else:
        plt.show()


if __name__ == '__main__':
    main()
