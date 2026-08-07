"""
Real-time attractor visualisation for the 5D chaos monitor.

Layout (dark theme):
  ┌──────────────────────────┬────────────────┬────────────────┐
  │                          │   x – y plane  │   x – z plane  │
  │  3-D phase portrait      │                │                │
  │  ch0(x)·ch1(y)·ch2(z)   ├────────────────┼────────────────┤
  │                          │   w – v plane  │  time series   │
  │                          │  ch3(w)·ch4(v) │  all channels  │
  └──────────────────────────┴────────────────┴────────────────┘
  status bar: per-channel SPS · dropped · checksum errors

FuncAnimation fires at *fps* Hz (default 30); blit=False because
matplotlib's 3-D axes do not support blit.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.animation import FuncAnimation

TRAIL      = 10_000   # points drawn in attractor / 2-D phase plots
TS_SAMPLES = 3_000    # points drawn in the time-series panel per channel

CH_COLORS  = ['#00d4ff', '#ff6b35', '#7bc67e', '#d4a5ff', '#ffd700']
CH_LABELS  = ['x (ch0)', 'y (ch1)', 'z (ch2)', 'w (ch3)', 'v (ch4)']

BG   = '#080808'
GRID = '#1c1c1c'
TXT  = '#aaaaaa'
DIM  = '#555555'


def _safe_lim(arr, margin: float = 0.06):
    lo, hi = float(arr.min()), float(arr.max())
    span = max(hi - lo, 1e-4)
    pad  = span * margin
    return lo - pad, hi + pad


class AttractorPlotter:
    def __init__(self, store, parser, fps: int = 30):
        self.store  = store
        self.parser = parser
        self.fps    = fps
        self._build_figure()

    # ── figure construction ────────────────────────────────────────────────────

    def _build_figure(self):
        plt.style.use('dark_background')
        self.fig = plt.figure(figsize=(15, 8), facecolor=BG)
        self.fig.canvas.manager.set_window_title('5D Chaos Monitor')

        gs = gridspec.GridSpec(
            2, 3, figure=self.fig,
            width_ratios=[2, 1, 1],
            hspace=0.42, wspace=0.32,
            left=0.05, right=0.97, top=0.93, bottom=0.08,
        )

        # ── 3-D attractor (left, spans both rows) ──────────────────────────
        self.ax3d = self.fig.add_subplot(gs[:, 0], projection='3d')
        self._style_3d(self.ax3d, 'Phase portrait  x · y · z')

        # ── 2-D projections ─────────────────────────────────────────────────
        self.ax_xy = self._make_2d(gs[0, 1], 'x – y',  'x (V)', 'y (V)')
        self.ax_xz = self._make_2d(gs[0, 2], 'x – z',  'x (V)', 'z (V)')
        self.ax_wv = self._make_2d(gs[1, 1], 'w – v',  'w (V)', 'v (V)')
        self.ax_ts = self._make_2d(gs[1, 2], 'time series', 'sample', 'V')

        # ── artists ─────────────────────────────────────────────────────────
        self.ln3d, = self.ax3d.plot([], [], [],
                                    lw=0.55, color='#00d4ff', alpha=0.75)

        self.ln_xy, = self.ax_xy.plot([], [], lw=0.45,
                                      color=CH_COLORS[0], alpha=0.8)
        self.ln_xz, = self.ax_xz.plot([], [], lw=0.45,
                                      color=CH_COLORS[2], alpha=0.8)
        self.ln_wv, = self.ax_wv.plot([], [], lw=0.45,
                                      color=CH_COLORS[3], alpha=0.8)

        self.ts_lines = [
            self.ax_ts.plot([], [], lw=0.65,
                            color=CH_COLORS[i], label=CH_LABELS[i],
                            alpha=0.88)[0]
            for i in range(5)
        ]
        self.ax_ts.legend(fontsize=5.5, loc='upper right', framealpha=0.15,
                          labelcolor='white')

        # ── status bar ──────────────────────────────────────────────────────
        self.status = self.fig.text(
            0.005, 0.012, '', color=DIM,
            fontsize=6.5, fontfamily='monospace', va='bottom',
        )

    def _style_3d(self, ax, title):
        for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
            pane.fill = False
            pane.set_edgecolor(GRID)
        ax.set_facecolor(BG)
        ax.grid(True, color=GRID, lw=0.35)
        ax.set_title(title, color=TXT, fontsize=9, pad=6)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.label.set_color(DIM)
            axis.set_tick_params(labelcolor=DIM, labelsize=5)
        ax.set_xlabel('x (V)', fontsize=7, labelpad=2)
        ax.set_ylabel('y (V)', fontsize=7, labelpad=2)
        ax.set_zlabel('z (V)', fontsize=7, labelpad=2)

    def _make_2d(self, pos, title, xlabel, ylabel):
        ax = self.fig.add_subplot(pos)
        ax.set_facecolor(BG)
        ax.spines[:].set_color(GRID)
        ax.tick_params(colors=DIM, labelsize=5)
        ax.grid(True, color=GRID, lw=0.28)
        ax.set_title(title, color=TXT, fontsize=8, pad=3)
        ax.set_xlabel(xlabel, fontsize=7, color=DIM)
        ax.set_ylabel(ylabel, fontsize=7, color=DIM)
        return ax

    # ── animation ──────────────────────────────────────────────────────────────

    def _update(self, _frame):
        bufs = self.store.channels

        _, x = bufs[0].latest(TRAIL)
        _, y = bufs[1].latest(TRAIL)
        _, z = bufs[2].latest(TRAIL)
        _, w = bufs[3].latest(TRAIL)
        _, v = bufs[4].latest(TRAIL)

        # 3-D and x-y, x-z projections require all three Chua channels
        n3 = min(len(x), len(y), len(z))
        if n3 >= 4:
            self.ln3d.set_data_3d(x[:n3], y[:n3], z[:n3])
            self.ax3d.set_xlim(*_safe_lim(x[:n3]))
            self.ax3d.set_ylim(*_safe_lim(y[:n3]))
            self.ax3d.set_zlim(*_safe_lim(z[:n3]))

            self.ln_xy.set_data(x[:n3], y[:n3])
            self.ax_xy.set_xlim(*_safe_lim(x[:n3]))
            self.ax_xy.set_ylim(*_safe_lim(y[:n3]))

            self.ln_xz.set_data(x[:n3], z[:n3])
            self.ax_xz.set_xlim(*_safe_lim(x[:n3]))
            self.ax_xz.set_ylim(*_safe_lim(z[:n3]))

        nwv = min(len(w), len(v))
        if nwv >= 4:
            self.ln_wv.set_data(w[:nwv], v[:nwv])
            self.ax_wv.set_xlim(*_safe_lim(w[:nwv]))
            self.ax_wv.set_ylim(*_safe_lim(v[:nwv]))

        # time series: last TS_SAMPLES points per channel, indexed from -N to 0
        arrs = [x, y, z, w, v]
        ts_min_v, ts_max_v = np.inf, -np.inf
        for i, (arr, ln) in enumerate(zip(arrs, self.ts_lines)):
            n = min(len(arr), TS_SAMPLES)
            if n >= 2:
                seg = arr[-n:]
                ln.set_data(np.arange(-n + 1, 1), seg)
                ts_min_v = min(ts_min_v, float(seg.min()))
                ts_max_v = max(ts_max_v, float(seg.max()))

        if ts_min_v < ts_max_v:
            self.ax_ts.set_xlim(-TS_SAMPLES, 0)
            pad = (ts_max_v - ts_min_v) * 0.06
            self.ax_ts.set_ylim(ts_min_v - pad, ts_max_v + pad)

        # status bar
        rates   = [self.store.rate(i) for i in range(5)]
        dropped = sum(self.parser.stats['dropped'])
        cerr    = self.parser.stats['csum_err']
        sskip   = self.parser.stats['sync_skip']
        sps_str = '  '.join(f'ch{i}:{r:>6.0f}' for i, r in enumerate(rates))
        self.status.set_text(
            f'SPS  {sps_str}    '
            f'dropped:{dropped}  csum_err:{cerr}  sync_skip:{sskip}'
        )

        return [self.ln3d, self.ln_xy, self.ln_xz,
                self.ln_wv] + self.ts_lines

    def run(self):
        self._anim = FuncAnimation(
            self.fig, self._update,
            interval=1000 // self.fps,
            blit=False,            # 3-D axes do not support blit
            cache_frame_data=False,
        )
        plt.show()
