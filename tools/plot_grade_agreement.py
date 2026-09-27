#!/usr/bin/env python3
"""
Draw the Why This page's grade-agreement figure from an evaluation CSV.

    .venv/Scripts/python tools/plot_grade_agreement.py [results/tapping_eval/<run>.csv]

One dot per recording: our CV% (camera) against the motion-capture CV%, with
the 15 / 25 % band cut-offs drawn on both axes. The three squares on the
diagonal are "same grade"; a dot outside them is a grade disagreement.
Agreement is carried by colour AND marker shape, so it never rides on colour
alone. Colours are the page's tokens (styles.css); the amber is stepped down
from --warning so the pair passes the dataviz palette validator on --surface.
Defaults to the newest CSV. Writes launcher_web/img/validation/grade-agreement.webp.
"""

from __future__ import annotations

import csv
import glob
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "launcher_web" / "img" / "validation" / "grade-agreement.webp"
CUTS = (15.0, 25.0)          # core/tapping/modes.py cv_typical / cv_monitor
AXIS_MAX = 60.0              # a handful of tracking failures run past this
BANDS = ("Typical", "Monitor", "Follow-up")

BG, TEXT, MUTED, FAINT, GRID = "#111827", "#F8FAFC", "#B4C0D0", "#8C9BB2", "#2A3442"
AGREE, DISAGREE = "#12A594", "#C97A0A"


def band(v: float) -> int:
    return 0 if v < CUTS[0] else 1 if v < CUTS[1] else 2


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        sorted(glob.glob(str(REPO / "results/tapping_eval/ehwgesture_*.csv")))[-1])
    pts = []
    for r in csv.DictReader(open(src, encoding="utf-8")):
        if r.get("scoreable_ours") == "True" and r.get("scoreable_ref") == "True":
            pts.append((float(r["cv_pct_ref"]), float(r["cv_pct_ours"])))
    same = [p for p in pts if band(p[0]) == band(p[1])]
    diff = [p for p in pts if band(p[0]) != band(p[1])]
    clipped = sum(max(p) > AXIS_MAX for p in pts)
    print(f"{src.name}: {len(pts)} recordings, {len(same)} same grade, {clipped} beyond {AXIS_MAX:.0f}%")

    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 16})
    fig = plt.figure(figsize=(16, 9), dpi=100, facecolor=BG)
    ax = fig.add_axes([0.075, 0.13, 0.44, 0.78], facecolor=BG)   # square plot, text on the right

    # Same-grade squares on the diagonal, then the cut-off lines.
    edges = (0.0, *CUTS, AXIS_MAX)
    for i in range(3):
        a, b = edges[i], edges[i + 1]
        ax.add_patch(Rectangle((a, a), b - a, b - a, facecolor=AGREE, alpha=0.10,
                               edgecolor="none", zorder=0))
    for c in CUTS:
        ax.axvline(c, color=FAINT, lw=1, ls=(0, (4, 4)), zorder=1)
        ax.axhline(c, color=FAINT, lw=1, ls=(0, (4, 4)), zorder=1)
    ax.plot([0, AXIS_MAX], [0, AXIS_MAX], color=MUTED, lw=1, alpha=0.5, zorder=1)

    clip = lambda ps: ([min(x, AXIS_MAX - 0.6) for x, _ in ps], [min(y, AXIS_MAX - 0.6) for _, y in ps])
    xs, ys = clip(same)
    ax.scatter(xs, ys, s=90, marker="o", color=AGREE, edgecolor=BG, linewidth=1.5,
               alpha=0.85, zorder=3)
    xs, ys = clip(diff)
    ax.scatter(xs, ys, s=110, marker="D", color=DISAGREE, edgecolor=BG, linewidth=1.5,
               zorder=4)

    ax.set_xlim(0, AXIS_MAX); ax.set_ylim(0, AXIS_MAX); ax.set_aspect("equal")
    ax.set_xlabel("Motion capture CV%", color=MUTED, fontsize=21, labelpad=12)
    ax.set_ylabel("Our camera CV%", color=MUTED, fontsize=21, labelpad=12)
    ax.tick_params(colors=FAINT, labelsize=18, length=0, pad=10)
    ax.set_xticks([0, 15, 25, 40, 60]); ax.set_yticks([0, 15, 25, 40, 60])
    for s in ax.spines.values():
        s.set_color(GRID)
    # Band names above the plot, one per column, clear of the dots.
    for i, name in enumerate(BANDS):
        mid = (edges[i] + edges[i + 1]) / 2
        ax.text(mid, AXIS_MAX + 1.2, name, ha="center", va="bottom", color=MUTED, fontsize=18,
                clip_on=False)

    # Right-hand panel: the headline and a legend that carries the counts.
    x0 = 0.585
    fig.text(x0, 0.80, f"{len(same)} of {len(pts)}", color=TEXT, fontsize=66, fontweight="bold")
    fig.text(x0, 0.72, "recordings got the same grade", color=MUTED, fontsize=25)
    fig.text(x0, 0.665, "as motion capture", color=MUTED, fontsize=25)
    ax_leg = fig.add_axes([x0, 0.40, 0.4, 0.2]); ax_leg.axis("off")
    ax_leg.set_xlim(0, 1); ax_leg.set_ylim(0, 1)
    ax_leg.scatter([0.03], [0.78], s=200, marker="o", color=AGREE, edgecolor=BG, linewidth=1.5)
    ax_leg.text(0.09, 0.78, f"Same grade  ({len(same)})", color=TEXT, fontsize=23, va="center")
    ax_leg.scatter([0.03], [0.30], s=210, marker="D", color=DISAGREE, edgecolor=BG, linewidth=1.5)
    ax_leg.text(0.09, 0.30, f"Different grade  ({len(diff)})", color=TEXT, fontsize=23, va="center")
    notes = ["Each dot is one 20 s recording.",
             "Shaded squares mean the same grade."]
    if clipped:
        notes.append(f"{clipped} dots past {AXIS_MAX:.0f}% are pinned to the edge.")
    for k, line in enumerate(notes):
        fig.text(x0, 0.29 - k * 0.065, line, color=FAINT, fontsize=19)
    fig.text(x0, 0.08, "EHWGesture · 22 volunteers · 120 fps motion capture", color=FAINT, fontsize=17)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    png = OUT.with_suffix(".png")
    fig.savefig(png, facecolor=BG)
    Image.open(png).save(OUT, "WEBP", quality=90, method=6)
    png.unlink()
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
