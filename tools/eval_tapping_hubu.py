#!/usr/bin/env python3
"""
Does the finger tapping score follow clinical severity? HUBU-FIS evaluation.

    .venv/Scripts/python tools/eval_tapping_hubu.py --root C:/Datasets/HUBU-FIS --limit 4
    .venv/Scripts/python tools/eval_tapping_hubu.py --root C:/Datasets/HUBU-FIS

HUBU-FIS (zenodo.org/records/17738775, CC-BY 4.0; Universidad de Burgos and
Hospital Universitario de Burgos) holds 234 finger tapping videos from 43
controls and 75 Parkinson's patients, each rated by a neurologist on the
UPDRS finger tapping item (0-4; 0-3 occur here). Expected layout:

    <root>/videos_FIS/fis_diagnostic.csv      ID,UPDRS
    <root>/videos_FIS/videos/CONTROL01_DCHA.mp4 ...   (_DCHA right, _IZDA left)

Every video goes through the live test's pipeline (tools/eval_tapping_videos.py
extract/detect, then core/tapping/metrics.compute_metrics with the Big & Fast
mode, whole clip). Nothing is fitted to this data: the bands, detector and
quality gate are the shipped ones, so what comes out is a test, not a tune.

The analysis was fixed before any results were seen (see the plan the
statistics below implement):

  P1  Spearman rho, CV% vs UPDRS 0-3                       (primary)
  S1  AUC of CV%, UPDRS >= 2 vs UPDRS 0
  S2  AUC of CV%, patients vs controls
  S3  our bands: UPDRS 0 graded Typical; UPDRS >= 2 graded Monitor or worse
  S4  unscoreable rate per UPDRS grade (must not rise with severity)
  S5  P1/S1 for tap rate and speed decrement
  S6  P1/S1 on the 10 s window

Unit is one video; every 95% CI resamples people (two hands each), 2000
draws, seed 0. Unscoreable runs are left out of P1/S1/S2/S5/S6, counted in S4.
Writes results/tapping_eval/hubu_<timestamp>.csv and .json.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))

from core.tapping.metrics import compute_metrics
from core.tapping.modes import MODES
from tools import tapping_eval as te
from tools.eval_tapping_videos import OUT_DIR, detect, load_trace

MODE = MODES["big_and_fast"]
PICK = "largest"
BOOT_N, BOOT_SEED = 2000, 0


def discover(root: Path) -> list[dict]:
    base = root / "videos_FIS"
    labels = {r["ID"]: int(r["UPDRS"]) for r in
              csv.DictReader(open(base / "fis_diagnostic.csv", encoding="utf-8-sig"))}
    items = []
    for vid in sorted((base / "videos").iterdir()):
        key = vid.stem
        if key not in labels:
            continue
        m = re.match(r"([A-Za-z]+)(\d+)_(DCHA|IZDA)$", key)
        if not m:
            continue
        items.append({"id": key, "person": m.group(1) + m.group(2),
                      "group": "control" if m.group(1).upper() == "CONTROL" else "patient",
                      "side": "Right" if m.group(3) == "DCHA" else "Left",
                      "updrs": labels[key], "video": vid})
    return items


def score(item: dict, trace: dict) -> dict:
    taps, series, calibrated, near_miss = detect(trace, MODE)
    n = max(1, trace["frames"])
    vis = sum(d is not None for d in trace["d"]) / n
    t = trace["t"]
    m = compute_metrics(MODE, taps, series, t[0], t[-1] if t else 0.0,
                        hand_visible_ratio=vis, camera_fps=trace["fps"],
                        near_miss=near_miss)
    return {"id": item["id"], "person": item["person"], "group": item["group"],
            "side": item["side"], "updrs": item["updrs"],
            "fps": round(trace["fps"], 2), "frames": trace["frames"],
            "hand_visible": round(vis, 3), "calibrated": calibrated,
            "taps": m["taps"], "near_miss": near_miss,
            "rate_hz": m["frequency_hz"], "cv_pct": m["cv_pct"],
            "cv_pct_w10": m["cv_pct_w10"], "amp_cv_pct": m["amplitude_cv_pct"],
            "decrement_pct_per_s": m["decrement_pct_per_s"],
            "confidence_pct": m["confidence_pct"], "status": m["status"],
            "scoreable": m["scoreable"], "reason": m["reason"]}


# ── the pre-registered statistics ────────────────────────────────────────────

def _rho(key):
    def f(rows):
        rs = [r for r in rows if r[key] is not None]
        return te.spearman([r[key] for r in rs], [r["updrs"] for r in rs])
    return f


def _auc(key, pos, neg, higher_is_worse=True):
    def f(rows):
        p = [r[key] for r in rows if r[key] is not None and pos(r)]
        n = [r[key] for r in rows if r[key] is not None and neg(r)]
        a = te.auc(p, n)
        return a if a is None or higher_is_worse else 1 - a
    return f


def _share(pred, cond):
    def f(rows):
        rs = [r for r in rows if cond(r)]
        return sum(pred(r) for r in rs) / len(rs) if rs else None
    return f


def analyse(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["scoreable"]]
    ci = lambda stat, data=scored: te.cluster_bootstrap(data, "person", stat, BOOT_N, BOOT_SEED)
    severe = lambda r: r["updrs"] >= 2
    none_ = lambda r: r["updrs"] == 0
    out = {"n_videos": len(rows), "n_scored": len(scored),
           "n_people": len({r["person"] for r in rows}),
           "P1_rho_cv": ci(_rho("cv_pct")),
           "S1_auc_cv_updrs2_vs_0": ci(_auc("cv_pct", severe, none_)),
           "S2_auc_cv_patient_vs_control": ci(_auc("cv_pct", lambda r: r["group"] == "patient",
                                                   lambda r: r["group"] == "control")),
           "S3_specificity_updrs0_typical": ci(_share(lambda r: r["status"] == "success", none_)),
           "S3_sensitivity_updrs2_flagged": ci(_share(lambda r: r["status"] in ("warning", "danger"), severe)),
           "S5_rho_rate": ci(_rho("rate_hz")),
           "S5_auc_rate_updrs2_vs_0": ci(_auc("rate_hz", severe, none_, higher_is_worse=False)),
           "S5_rho_decrement": ci(_rho("decrement_pct_per_s")),
           "S5_auc_decrement_updrs2_vs_0": ci(_auc("decrement_pct_per_s", severe, none_,
                                                   higher_is_worse=False)),
           "S6_rho_cv_w10": ci(_rho("cv_pct_w10")),
           "S6_auc_cv_w10_updrs2_vs_0": ci(_auc("cv_pct_w10", severe, none_))}
    per = {}
    for g in sorted({r["updrs"] for r in rows}):
        rs = [r for r in rows if r["updrs"] == g]
        cv = sorted(r["cv_pct"] for r in rs if r["scoreable"])
        per[g] = {"videos": len(rs), "unscoreable": sum(not r["scoreable"] for r in rs),
                  "median_cv": cv[len(cv) // 2] if cv else None}
    out["S4_per_grade"] = per
    return out


def _fmt(v, nd=2):
    return "-" if v is None else f"{v:.{nd}f}"


def report(a: dict) -> None:
    print(f"\n{a['n_videos']} videos, {a['n_people']} people, {a['n_scored']} scoreable\n")
    lines = [("P1  Spearman rho, CV% vs UPDRS (primary)", "P1_rho_cv"),
             ("S1  AUC CV%, UPDRS>=2 vs 0", "S1_auc_cv_updrs2_vs_0"),
             ("S2  AUC CV%, patients vs controls", "S2_auc_cv_patient_vs_control"),
             ("S3  UPDRS 0 graded Typical", "S3_specificity_updrs0_typical"),
             ("S3  UPDRS>=2 graded Monitor or worse", "S3_sensitivity_updrs2_flagged"),
             ("S5  Spearman rho, tap rate vs UPDRS", "S5_rho_rate"),
             ("S5  AUC tap rate (slower = worse), UPDRS>=2 vs 0", "S5_auc_rate_updrs2_vs_0"),
             ("S5  Spearman rho, decrement vs UPDRS", "S5_rho_decrement"),
             ("S5  AUC decrement (more negative = worse)", "S5_auc_decrement_updrs2_vs_0"),
             ("S6  Spearman rho, CV% first 10 s", "S6_rho_cv_w10"),
             ("S6  AUC CV% first 10 s, UPDRS>=2 vs 0", "S6_auc_cv_w10_updrs2_vs_0")]
    for label, key in lines:
        est, lo, hi = a[key]
        print(f"  {label:<50} {_fmt(est)}  [{_fmt(lo)}, {_fmt(hi)}]")
    print("\n  S4  per UPDRS grade: videos, unscoreable, median CV%")
    for g, v in a["S4_per_grade"].items():
        print(f"      UPDRS {g}: {v['videos']:3d}  {v['unscoreable']:3d} unscoreable  "
              f"median CV% {_fmt(v['median_cv'], 1)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", required=True, type=Path,
                    help="folder holding videos_FIS/")
    ap.add_argument("--max-side", type=int, default=960,
                    help="downscale frames to this longer side (default 960)")
    ap.add_argument("--limit", type=int, help="stop after N videos")
    ap.add_argument("--only", help="comma list of video IDs to run")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--cached-only", action="store_true",
                    help="score only videos already processed")
    args = ap.parse_args()

    items = discover(args.root)
    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        items = [i for i in items if i["id"] in want]
    if args.limit:
        items = items[:args.limit]
    print(f"{len(items)} videos")
    rows = []
    for k, item in enumerate(items, 1):
        t0 = time.time()
        try:
            if args.cached_only:
                from tools.eval_tapping_videos import _cache_path, cache_matches
                cp = _cache_path(item["video"], args.root)
                if not cp.exists():
                    continue
                data = json.loads(cp.read_text())
                if not cache_matches(data, item["video"].stat().st_size, PICK, args.max_side):
                    continue
                trace = data
            else:
                trace = load_trace(item["video"], args.root, None, not args.no_cache,
                                   pick=PICK, max_side=args.max_side)
            row = score(item, trace)
        except Exception as e:           # one bad file must not end a long run
            print(f"[{k}/{len(items)}] {item['id']}: FAILED {e!r}", flush=True)
            continue
        rows.append(row)
        print(f"[{k}/{len(items)}] {item['id']:<16} UPDRS {row['updrs']}  "
              f"taps {row['taps']:3d}  CV% {_fmt(row['cv_pct'], 1):>5}  "
              f"rate {_fmt(row['rate_hz'])} Hz  "
              f"{'' if row['scoreable'] else 'UNSCOREABLE: ' + (row['reason'] or '')[:50]}"
              f"  ({time.time() - t0:.0f}s)", flush=True)
    if not rows:
        print("nothing scored")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    out = OUT_DIR / f"hubu_{stamp}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    a = analyse(rows)
    a["settings"] = {"mode": MODE.key, "pick": PICK, "max_side": args.max_side,
                     "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED}}
    out.with_suffix(".json").write_text(json.dumps(a, indent=1), encoding="utf-8")
    report(a)
    print(f"\nPer-video results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
