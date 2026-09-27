#!/usr/bin/env python3
"""
Draw the Why This page's patient figure from a HUBU-FIS evaluation.

    .venv/Scripts/python tools/plot_updrs_cv.py [results/tapping_eval/hubu_<run>.csv]

One dot per scored video: our CV% against the neurologist's UPDRS finger
tapping grade, with each grade's median and its 95% interval (bootstrapped by
person, as in tools/eval_tapping_hubu.py) and the 15 / 25 % band cut-offs.
The headline statistics come from the run's .json, never recomputed here.
Defaults to the newest run. Writes launcher_web/img/validation/updrs-cv.webp.
"""

from __future__ import annotations

import csv
import glob
import json
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import tapping_eval as te  # noqa: E402

OUT = REPO / "launcher_web" / "img" / "validation" / "updrs-cv.webp"
CUTS = (15.0, 25.0)
AXIS_MAX = 60.0
BG, TEXT, MUTED, FAINT, GRID = "#111827", "#F8FAFC", "#B4C0D0", "#8C9BB2", "#2A3442"
DOT, MEDIAN = "#12A594", "#F8FAFC"


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        sorted(glob.glob(str(REPO / "results/tapping_eval/hubu_*.csv")))[-1])
    stats = json.loads(src.with_suffix(".json").read_text(encoding="utf-8"))
    rows = [r for r in csv.DictReader(open(src, encoding="utf-8")) if r["scoreable"] == "True"]
    for r in rows:
        r["cv"] = float(r["cv_pct"])
        r["updrs"] = int(r["updrs"])
    grades = sorted({r["updrs"] for r in rows})
    clipped = sum(r["cv"] > AXIS_MAX for r in rows)

    def median(rs):
        v = sorted(r["cv"] for r in rs)
        return v[len(v) // 2] if v else None

    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 16})
    fig = plt.figure(figsize=(16, 9), dpi=100, facecolor=BG)
    ax = fig.add_axes([0.075, 0.13, 0.40, 0.78], facecolor=BG)
    for c in CUTS:
        ax.axhline(c, color=FAINT, lw=1, ls=(0, (4, 4)), zorder=1)
    # Band names just outside the right edge, clear of the dots.
    for name, y in (("Typical", 7.5), ("Monitor", 20.0), ("Follow-up", 42.0)):
        ax.text(len(grades) - 0.3, y, name, color=MUTED, fontsize=16, ha="left", va="center",
                clip_on=False)

    rng = random.Random(0)
    for i, g in enumerate(grades):
        rs = [r for r in rows if r["updrs"] == g]
        xs = [i + rng.uniform(-0.22, 0.22) for _ in rs]
        ys = [min(r["cv"], AXIS_MAX - 0.8) for r in rs]
        ax.scatter(xs, ys, s=70, color=DOT, alpha=0.7, edgecolor=BG, linewidth=1.2, zorder=3)
        est, lo, hi = te.cluster_bootstrap(rs, "person", median, 2000, 0)
        ax.errorbar([i], [est], yerr=[[est - lo], [hi - est]], fmt="none",
                    ecolor=MEDIAN, elinewidth=2.5, capsize=10, capthick=2.5, zorder=4)
        ax.plot([i - 0.3, i + 0.3], [est, est], color=MEDIAN, lw=3.5, zorder=5,
                solid_capstyle="round")
        ax.text(i, -5.2, f"{len(rs)} videos", color=FAINT, fontsize=14, ha="center", va="top",
                clip_on=False)

    ax.set_xlim(-0.6, len(grades) - 0.4)
    ax.set_ylim(0, AXIS_MAX)
    ax.set_xticks(range(len(grades)))
    ax.set_xticklabels([f"UPDRS {g}" for g in grades])
    ax.set_yticks([0, 15, 25, 40, 60])
    ax.set_ylabel("Our CV%", color=MUTED, fontsize=21, labelpad=12)
    ax.tick_params(colors=FAINT, labelsize=18, length=0, pad=12)
    ax.tick_params(axis="x", colors=MUTED, labelsize=19, pad=14)
    for s in ax.spines.values():
        s.set_color(GRID)

    auc, alo, ahi = stats["S1_auc_cv_updrs2_vs_0"]
    rho, rlo, rhi = stats["P1_rho_cv"]
    spec = stats["S3_specificity_updrs0_typical"][0]
    sens = stats["S3_sensitivity_updrs2_flagged"][0]
    x0 = 0.585
    fig.text(x0, 0.80, f"AUC {auc:.2f}", color=TEXT, fontsize=66, fontweight="bold")
    fig.text(x0, 0.72, "separating UPDRS 2-3 from UPDRS 0", color=MUTED, fontsize=25)
    fig.text(x0, 0.665, f"95% CI {alo:.2f} to {ahi:.2f}", color=FAINT, fontsize=19)
    for k, (big, small) in enumerate(((f"{spec:.0%}", "of UPDRS 0 graded Typical"),
                                      (f"{sens:.0%}", "of UPDRS 2-3 flagged"),
                                      (f"{rho:.2f}", f"rank correlation with grade ({rlo:.2f} to {rhi:.2f})"))):
        y = 0.52 - k * 0.095
        fig.text(x0, y, big, color=TEXT, fontsize=30, fontweight="bold")
        fig.text(x0 + 0.1, y + 0.008, small, color=MUTED, fontsize=19)
    notes = ["Each dot is one hand. The white bar is the median", "with its 95% interval."]
    if clipped:
        notes[-1] = notes[-1][:-1] + (f", {clipped} dot pinned at {AXIS_MAX:.0f}%." if clipped == 1
                                      else f", {clipped} dots pinned at {AXIS_MAX:.0f}%.")
    for k, line in enumerate(notes):
        fig.text(x0, 0.2 - k * 0.05, line, color=FAINT, fontsize=17)
    fig.text(x0, 0.06, f"HUBU-FIS · {stats['n_people']} people · Parkinson's and controls",
             color=FAINT, fontsize=17)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    png = OUT.with_suffix(".png")
    fig.savefig(png, facecolor=BG)
    Image.open(png).save(OUT, "WEBP", quality=90, method=6)
    png.unlink()
    print(f"{src.name}: {len(rows)} scored videos, {clipped} clipped; wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
