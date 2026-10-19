#!/usr/bin/env python3
"""Figure 1 for the report.

A: share of values that are measured / partially measured / fully imputed in three released
   benchmarks (value-level match to PeMS) and in a year of current PeMS source data (District 7).
B: District 4 fully measured share by month, 2017–18 (benchmark era) vs 2025–26.

Numbers are the outputs of pems_audit.py (pems-bay, astgcn and summary subcommands) as reported in
report.md. Months with < 28 days of data are left out.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).parent
plt.rcParams.update({"font.family": "Helvetica", "font.size": 9, "axes.edgecolor": "#8a8984",
                     "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
# diverging pair: measured (blue, dark step for grayscale print) <-> imputed (red), neutral gray midpoint
MEAS, PART, IMP = "#184f95", "#d6d5d0", "#e34948"
SURFACE = "#ffffff"

rows = [  # label, measured, partial, imputed  (percent of cells / intervals)
    ("PEMS-BAY benchmark\nspeed · Jan–Jun 2017", 57.7, 17.9, 24.5),
    ("PEMS04 benchmark\nflow · Jan–Feb 2018", 57.1, 11.1, 31.8),
    ("PEMS08 benchmark\nflow · Jul–Aug 2016", 42.8, 9.1, 48.1),
    ("PeMS District 7 (LA), source data\nall stations · Sep 2025–Sep 2026", 12.9, 2.5, 84.6),
]
d4 = {  # month -> fully measured %, District 4, full months only
    "2017-01": 56.3, "2017-02": 57.3, "2017-03": 62.5, "2017-04": 62.1, "2017-05": 63.7, "2017-06": 63.1,
    "2018-01": 61.9, "2018-02": 61.3,
    "2025-10": 27.4, "2025-11": 37.7, "2025-12": 46.0, "2026-01": 46.4, "2026-02": 40.0, "2026-03": 43.5,
    "2026-04": 42.1, "2026-05": 47.3, "2026-06": 37.6, "2026-07": 20.3, "2026-08": 44.6, "2026-09": 45.8,
}

fig = plt.figure(figsize=(6.5, 4.6), dpi=300, facecolor=SURFACE)
gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1], width_ratios=[1, 2.2], hspace=0.62, wspace=0.06)

# ---- Panel A: 100% stacked horizontal bars ----
ax = fig.add_subplot(gs[0, :])
ys = [3.35, 2.35, 1.35, 0]          # extra gap before the source-data row
for (label, m, p, i), y in zip(rows, ys):
    left = 0
    for val, col in ((m, MEAS), (p, PART), (i, IMP)):
        ax.barh(y, val, left=left, height=0.62, color=col, edgecolor=SURFACE, linewidth=1.5)
        if val >= 6:
            ax.text(left + val / 2, y, f"{val:.1f}%", ha="center", va="center",
                    fontsize=8, color="white" if col != PART else INK, fontweight="bold" if col == IMP else None)
        left += val
ax.set_yticks(ys, [r[0] for r in rows], fontsize=7.5)
ax.set_xlim(0, 100); ax.set_ylim(-0.55, 3.9)
ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"], fontsize=7.5)
ax.tick_params(axis="y", length=0); ax.tick_params(axis="x", length=2)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.axhline(0.68, color=GRID, linewidth=0.8)
ax.set_title("A   Benchmark values that are PeMS imputations (matched cell by cell; every value present in both is equal)",
             loc="left", fontsize=8.5, color=INK, pad=16)
# legend above the bars, in reading order
for k, (lab, col) in enumerate((("Fully measured", MEAS), ("Partially measured", PART), ("Fully imputed by PeMS", IMP))):
    x0 = k * 0.27
    ax.add_patch(plt.Rectangle((x0, 1.02), 0.018, 0.045, transform=ax.transAxes, color=col, clip_on=False))
    ax.text(x0 + 0.026, 1.045, lab, transform=ax.transAxes, va="center", fontsize=7.5, color=INK2)

# ---- Panel B: District 4 fully measured share by month, broken time axis ----
eras = [("2017-01", "2018-02", "2017–18 (benchmark era)"), ("2025-10", "2026-09", "2025–26")]
axes = [fig.add_subplot(gs[1, 0]), None]
axes[1] = fig.add_subplot(gs[1, 1], sharey=axes[0])
for axb, (a, b, name) in zip(axes, eras):
    ms = [k for k in d4 if a <= k <= b]
    xs = list(range(len(ms)))
    # break the line where months are not consecutive (2017-06 -> 2018-01)
    seg, segs = [], []
    for k, x in zip(ms, xs):
        if seg and (int(k[:4]) * 12 + int(k[5:])) - (int(seg[-1][0][:4]) * 12 + int(seg[-1][0][5:])) > 1:
            segs.append(seg); seg = []
        seg.append((k, x))
    segs.append(seg)
    for s in segs:
        axb.plot([x for _, x in s], [d4[k] for k, _ in s], color=MEAS, linewidth=2, solid_capstyle="round")
    axb.scatter(xs, [d4[k] for k in ms], s=14, color=MEAS, edgecolor=SURFACE, linewidth=1.2, zorder=3)
    axb.set_xticks(xs, [("Jan " if k[5:] == "01" else "") + {"01": "", "02": "F", "03": "M", "04": "A", "05": "M",
                         "06": "J", "07": "J", "08": "A", "09": "S", "10": "O", "11": "N", "12": "D"}[k[5:]]
                        + (k[2:4] if k[5:] == "01" else "") for k in ms], fontsize=6.5)
    axb.set_xlim(-0.6, len(ms) - 0.4)
    axb.set_ylim(0, 75)
    axb.grid(axis="y", color=GRID, linewidth=0.6); axb.set_axisbelow(True)
    for sp in ("top", "right"):
        axb.spines[sp].set_visible(False)
    axb.tick_params(length=2)
    axb.text(0.02, 0.06, name, transform=axb.transAxes, fontsize=7, color=INK2)
axes[0].set_yticks([0, 25, 50, 75], ["0%", "25%", "50%", "75%"], fontsize=7.5)
axes[1].tick_params(labelleft=False)
axes[1].spines["left"].set_visible(False)
axes[1].tick_params(axis="y", length=0)
# visible axis break between eras
for x in (1.0,):
    axes[0].plot([x - 0.015, x + 0.015], [-0.03, 0.03], transform=axes[0].transAxes, color="#8a8984",
                 linewidth=0.8, clip_on=False)
axes[0].set_title("B   PeMS District 4 (Bay Area): share of 5-minute intervals fully measured, by month",
                  loc="left", fontsize=8.5, color=INK, pad=8)
axes[1].annotate("Jul 2026: 20%", xy=(9, 20.3), xytext=(6.9, 9), fontsize=6.5, color=INK2,
                 arrowprops=dict(arrowstyle="-", color="#8a8984", linewidth=0.6))

fig.savefig(OUT / "fig1-provenance.png", dpi=300, bbox_inches="tight", facecolor=SURFACE)
fig.savefig(OUT / "fig1-provenance.pdf", bbox_inches="tight", facecolor=SURFACE)
print("wrote", OUT / "fig1-provenance.png")
