#!/usr/bin/env python3
"""
Set the optical-flow detection thresholds (engine 4) on data, not on two runs.

    .venv/Scripts/python tools/calibrate_tremor_flow.py --still 20260930_001605,20260930_003228 \
        --carrier-json <replayed Takes>.json
    .venv/Scripts/python tools/calibrate_tremor_flow.py --rescore results/tremor_eval/calib_<stamp>.csv
    .venv/Scripts/python tools/calibrate_tremor_flow.py --still 20260930_001605 --limit 20   # smoke

Why: engine 3 scored the optical flow against thresholds made for the
landmark reading (AMP_FLOOR_PCT 1.5 / 0.75 % of the hand length). The flow's
still-hand floor is 0.02-0.03 %, and on 2026-09-30 it measured a real
0.08-0.23 % tremor at 4.7-5.1 Hz in all four rest cells, which the landmark
floors called "none" (TREMOR_TEST_PLAN.md §3c). Engine 4 gives the flow its
own floors (AMP_FLOW_POSSIBLE, AMP_FLOW_DETECTED) and a true-peak test
(PEAK_SIDE_MIN). This tool picks them.

Camera path ("flow-grade"): the fingertip arc a wrist rotation makes (gyro
integrated to angle x one hand length, % of hand length -- the rotation path
of tools/eval_tremor_auc.py, P1), read at the frame times of a RECORDED
STILL-HAND FLOW TRACE and added to it (tools/eval_tremor_accel.through_camera,
here with instrument="flow" and exact_times=True, as the offline pass calls
analyse_hand). Carriers: only the sessions named with --still, whose hands
were still; a run with a tremor in it is not noise.

Data:
  PADS          (tools/eval_tremor_auc.load_pads) 79 healthy, 276 PD, 4 tasks
                (Relaxed, RelaxedTask -> rest carriers; StretchHold,
                HoldWeight -> postural carriers), both wrists.
  Parkinson@Home (eval_tremor_auc.load_pathome_labels / pathome_people)
                H1: 20 s windows wholly inside a video-coded segment, code 0
                (still, no tremor) vs 1 (< 3 cm) / 2 (3-10 cm) / 3 (> 10 cm),
                9 PD patients, OFF and ON. H2: sitting windows, 24 HC.

Selection rule (fixed before any result is read):
  Grid: AMP_FLOW_POSSIBLE in {0.03, 0.04, 0.05, 0.06, 0.08, 0.10},
        AMP_FLOW_DETECTED in {0.08, 0.10, 0.12, 0.15, 0.20, 0.30} (> possible),
        PEAK_SIDE_MIN in {1.2, 1.5, 2.0, 2.5}; PROM_MIN / PROM_POSSIBLE stay.
  Admissible when ALL hold:
    C1 every still-carrier cell alone is "none";
    C2 PADS healthy, every task: 0 % "detected", >= 95 % "none";
    C3 Parkinson@Home healthy sitting windows: <= 1 % "detected";
    C4 Parkinson@Home code-0 windows: <= 1 % "detected".
  Among admissible configs: highest Parkinson@Home code-1 "any flag" share,
  then code-2 "detected", then the larger AMP_FLOW_DETECTED (more margin).
  Reported beside it: PADS PD rest shares, codes 2-3, the engine-4 defaults.

Added 2026-09-30 after the first full run, which found no admissible point
(the strictest one missed by one PADS healthy cell of 316 and by 1.08 % vs
1 % on code 0), before any rescored number was read:
  * the grid extends in the strict direction (GRID_*_STRICT);
  * if nothing is admissible, the point with the smallest total violation of
    C1-C4 is chosen and every violation is reported -- no criterion is
    loosened;
  * --carrier-json adds still hands measured by the current engine from
    keep-frames Takes (the saved sessions' flow traces predate engine 4's
    hand-shaped mask);
  * --rescore re-scores a saved rows CSV without recomputing any spectrum.

Rows keep prominence, amp_pct and peak_side from one analyse_hand call per
(record, carrier); classify() is pure, so every grid point re-scores them
without re-running the spectrum. Writes results/tremor_eval/calib_<stamp>.*
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from core.tremor import metrics as tm
from core.tremor.phases import PHASES
from eval_tremor_accel import OUT_DIR, UP_FS, load_carriers, view
from eval_tremor_auc import (PADS_TASKS, PH_FS, REST_MOVE, POST_MOVE, _windows,
                             angle, load_pads, load_pathome_labels, pathome_people,
                             rot_window)

GRID_POSSIBLE = (0.03, 0.04, 0.05, 0.06, 0.08, 0.10)
GRID_DETECTED = (0.08, 0.10, 0.12, 0.15, 0.20, 0.30)
GRID_SIDE = (1.2, 1.5, 2.0, 2.5)
GRID_POSSIBLE_STRICT = (0.12, 0.15)
GRID_DETECTED_STRICT = (0.40, 0.50, 0.60, 0.80)
GRID_SIDE_STRICT = (3.0, 4.0)
PH_CARRIERS = 2          # carriers per Parkinson@Home window (runtime)


def through_flow(sig_pct: np.ndarray, carrier: dict) -> dict:
    """sig_pct: (n, 2) fingertip arc, % of hand length, on the UP_FS grid.
    Read at the carrier's frame times, add to it, analyse as the offline
    pass does."""
    t = carrier["t"] - carrier["t"][0]
    n_need = int(math.ceil((t[-1] + 1.0 / UP_FS) * UP_FS)) + 2
    if len(sig_pct) < n_need:
        sig_pct = np.concatenate([sig_pct] * int(math.ceil(n_need / len(sig_pct))))
    start = (len(sig_pct) - n_need) // 2
    seg = sig_pct[start:start + n_need]
    grid = np.arange(n_need) / UP_FS
    add = np.column_stack([np.interp(t, grid, seg[:, k]) for k in range(2)])
    pts = (carrier["xy"] + add)[:, None, :]
    return tm.analyse_hand(carrier["t"], pts, np.full(len(t), 100.0),
                           move_max=carrier["move_max"], exact_times=True,
                           instrument="flow")


def _row(meta: dict, res: dict) -> dict:
    return {**meta, "scored": bool(res.get("scored")), "why": res.get("why"),
            "peak_hz": res.get("peak_hz"), "prominence": res.get("prominence"),
            "amp_pct": res.get("amp_pct"), "peak_side": res.get("peak_side")}


def run_still(carriers: dict) -> list[dict]:
    rows = []
    for kind, cs in carriers.items():
        for c in cs:
            res = tm.analyse_hand(c["t"], c["xy"][:, None, :], np.full(len(c["t"]), 100.0),
                                  move_max=c["move_max"], exact_times=True, instrument="flow")
            rows.append(_row({"ds": "STILL", "group": "still", "task": kind,
                              "carrier": c["id"]}, res))
    return rows


def run_pads(root: Path, carriers: dict, limit=None) -> list[dict]:
    rows = []
    recs = load_pads(root, limit)
    for i, rec in enumerate(recs, 1):
        sig = view(angle(rec["gyro"], rec["fs"]) * 100.0, "face")     # rad -> % hand
        for c in carriers[rec["hold"]]:
            rows.append(_row({"ds": "PADS", "person": rec["person"], "group": rec["group"],
                              "task": rec["task"], "wrist": rec["wrist"],
                              "carrier": c["id"]}, through_flow(sig, c)))
        if i % 500 == 0:
            print(f"  PADS {i}/{len(recs)}", flush=True)
    return rows


def _ph_window(wrists, a, b, cs, meta):
    out = []
    for side, (t, g) in wrists.items():
        i, j = np.searchsorted(t, [a, b])
        if j - i < 0.9 * (b - a) * PH_FS:
            continue
        xy = rot_window(g[i:j], PH_FS)
        grid = np.arange(int(len(xy) * UP_FS / PH_FS)) / UP_FS
        up = np.column_stack([np.interp(grid, np.arange(len(xy)) / PH_FS, xy[:, k])
                              for k in range(2)])
        for c in cs:
            out.append(_row({**meta, "wrist": side, "carrier": c["id"]}, through_flow(up, c)))
    return out


def run_pathome(root: Path, carriers: dict, limit=None) -> list[dict]:
    labels = load_pathome_labels(root)
    rng = np.random.default_rng(0)
    rest = carriers["rest"]
    rows = []
    for k, (pid, wrists) in enumerate(pathome_people(root)):
        if limit and k >= limit:
            break
        lab = labels.get(pid)
        if lab is None:
            continue
        base = {"ds": "PATHOME", "person": pid, "group": lab["group"]}
        for a, b, c in _windows([s for s in lab["tremor"] if s[2] in (0.0, 1.0, 2.0, 3.0)]):
            cs = [rest[i] for i in rng.choice(len(rest), min(PH_CARRIERS, len(rest)), replace=False)]
            rows += _ph_window(wrists, a, b, cs, {**base, "task": "coded", "code": int(c)})
        if lab["group"] == "HC":
            for a, b, _ in _windows([(a, b) for a, b in lab["sitting"]]):
                cs = [rest[rng.integers(len(rest))]]
                rows += _ph_window(wrists, a, b, cs, {**base, "task": "sitting", "code": None})
        print(f"  Parkinson@Home {pid}: {sum(1 for r in rows if r['person'] == pid)} rows",
              flush=True)
    return rows


# ── re-scoring on the grid ───────────────────────────────────────────────────

def verdict(r: dict, possible: float, detected: float, side: float) -> str:
    if not r["scored"]:
        return "unscored"
    if r["peak_side"] is not None and r["peak_side"] < side:
        return tm.NONE
    if r["prominence"] < tm.PROM_POSSIBLE or r["amp_pct"] < possible:
        return tm.NONE
    if r["prominence"] >= tm.PROM_MIN and r["amp_pct"] >= detected:
        return tm.DETECTED
    return tm.POSSIBLE


def _shares(rs, cfg, per_person_wrist_max=False):
    vs = [verdict(r, *cfg) for r in rs]
    vs = [v for v in vs if v != "unscored"]
    if not vs:
        return {"n": 0, "detected": None, "any": None, "none": None}
    return {"n": len(vs), "detected": round(vs.count(tm.DETECTED) / len(vs), 4),
            "any": round(1 - vs.count(tm.NONE) / len(vs), 4),
            "none": round(vs.count(tm.NONE) / len(vs), 4)}


def evaluate(rows, cfg) -> dict:
    sel = lambda **kw: [r for r in rows if all(r.get(k) == v for k, v in kw.items())]
    out = {"still": _shares(sel(ds="STILL"), cfg)}
    for task in PADS_TASKS:
        out[f"pads_hc_{task}"] = _shares(sel(ds="PADS", group="HC", task=task), cfg)
        out[f"pads_pd_{task}"] = _shares(sel(ds="PADS", group="PD", task=task), cfg)
    out["ph_hc_sitting"] = _shares(sel(ds="PATHOME", task="sitting"), cfg)
    for code in (0, 1, 2, 3):
        out[f"ph_code{code}"] = _shares(sel(ds="PATHOME", task="coded", code=code), cfg)
    return out


def violations(e: dict) -> dict:
    """How far each of C1-C4 is missed (0 when met), as shares."""
    v = {"C1": e["still"]["any"] if e["still"]["n"] else 0.0}
    c2 = 0.0
    for task in PADS_TASKS:
        s = e[f"pads_hc_{task}"]
        if s["n"]:
            c2 += s["detected"] + max(0.0, 0.95 - s["none"])
    v["C2"] = c2
    for c, k in (("C3", "ph_hc_sitting"), ("C4", "ph_code0")):
        v[c] = max(0.0, e[k]["detected"] - 0.01) if e[k]["n"] else 0.0
    return {k: round(x, 4) for k, x in v.items()}


def admissible(e: dict) -> bool:
    return not any(violations(e).values())


def load_carrier_json(path: Path, stamps) -> dict:
    """Still hands from replayed keep-frames Takes:
    {"<session>:<phase>": {hand: {"t", "xy" (px), "len" (px)}}}."""
    out = {"rest": [], "postural": []}
    for key, per in json.loads(Path(path).read_text(encoding="utf-8")).items():
        sess, phase = key.rsplit(":", 1)
        if not any(s in sess for s in stamps):
            continue
        kind = "postural" if phase == "postural" else "rest"
        for hand, tr in per.items():
            if len(tr["t"]) < 40 or not tr["len"]:
                continue
            xy = np.asarray(tr["xy"], float)
            scale = float(np.median(tr["len"]))
            out[kind].append({"id": f"{key}:{hand}", "kind": kind,
                              "move_max": PHASES[phase].move_max,
                              "t": np.asarray(tr["t"], float),
                              "xy": (xy - np.median(xy, axis=0)) / scale * 100.0})
    return out


def load_rows(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["scored"] = r["scored"] == "True"
            for k in ("prominence", "amp_pct", "peak_side", "peak_hz"):
                r[k] = float(r[k]) if r.get(k) not in (None, "", "None") else None
            r["code"] = int(r["code"]) if r.get("code") not in (None, "", "None") else None
            rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--still", default="",
                    help="comma-separated session stamps (YYYYMMDD_HHMMSS) whose hands were still")
    ap.add_argument("--carrier-json", type=Path, default=None,
                    help="replayed keep-frames Takes (still ones picked by --still)")
    ap.add_argument("--rescore", type=Path, default=None,
                    help="re-score a saved calib_<stamp>.csv on the grid, no spectra")
    ap.add_argument("--pads", type=Path, default=Path("C:/Datasets/PADS"))
    ap.add_argument("--pathome", type=Path, default=Path("C:/Datasets/ParkinsonAtHome"))
    ap.add_argument("--results", type=Path, default=_REPO_ROOT / "results")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    stamps = [s.strip() for s in a.still.split(",") if s.strip()]
    if a.rescore:
        rows = load_rows(a.rescore)
        print(f"Re-scoring {len(rows)} rows from {a.rescore}")
    else:
        carriers = {"rest": [], "postural": []}
        for c in load_carriers(a.results, "flow"):
            if any(c["id"].startswith(s) for s in stamps):
                carriers[c["kind"]].append(c)
        if a.carrier_json:
            for kind, cs in load_carrier_json(a.carrier_json, stamps).items():
                carriers[kind] += cs
        if not carriers["rest"] or not carriers["postural"]:
            sys.exit(f"No still flow carriers of both kinds for {stamps}.")
        print(f"Still carriers: {len(carriers['rest'])} rest, {len(carriers['postural'])} postural")
        rows = run_still(carriers)
        rows += run_pads(a.pads, carriers, a.limit)
        if a.pathome.exists():
            rows += run_pathome(a.pathome, carriers, a.limit and max(2, a.limit // 10))

    grid = sorted({(p, d, s) for p, d, s in itertools.chain(
        itertools.product(GRID_POSSIBLE, GRID_DETECTED, GRID_SIDE),
        itertools.product(GRID_POSSIBLE + GRID_POSSIBLE_STRICT,
                          GRID_DETECTED + GRID_DETECTED_STRICT,
                          GRID_SIDE + GRID_SIDE_STRICT)) if d > p})
    table = []
    for cfg in grid:
        e = evaluate(rows, cfg)
        v = violations(e)
        table.append({"possible": cfg[0], "detected": cfg[1], "side": cfg[2],
                      "admissible": not any(v.values()), "violations": v,
                      "violation_total": round(sum(v.values()), 4), **e})
    ok = [t for t in table if t["admissible"]]
    key = lambda t: (t["ph_code1"]["any"] or 0, t["ph_code2"]["detected"] or 0, t["detected"])
    if ok:
        best, chosen_by = max(ok, key=key), "admissible"
    else:
        best = min(table, key=lambda t: (t["violation_total"], -(t["ph_code1"]["any"] or 0)))
        chosen_by = "least_violation"
    defaults = next((t for t in table if (t["possible"], t["detected"], t["side"]) ==
                     (tm.AMP_FLOW_POSSIBLE, tm.AMP_FLOW_DETECTED, tm.PEAK_SIDE_MIN)), None)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not a.rescore:
        with open(OUT_DIR / f"calib_{stamp}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
            w.writeheader()
            w.writerows(rows)
    summary = {"still_sessions": stamps, "rescored_from": str(a.rescore) if a.rescore else None,
               "n_rows": len(rows), "n_admissible": len(ok), "chosen_by": chosen_by,
               "best": best, "engine4_defaults": defaults, "grid": table}
    (OUT_DIR / f"calib_{stamp}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    brief = lambda t: t and {k: t[k] for k in ("possible", "detected", "side", "admissible",
                                               "violations",
                                               "still", "pads_hc_Relaxed", "pads_pd_Relaxed",
                                               "ph_hc_sitting", "ph_code0", "ph_code1",
                                               "ph_code2", "ph_code3")}
    print(json.dumps({"n_admissible": len(ok), "chosen_by": chosen_by, "best": brief(best),
                      "engine4_defaults": brief(defaults)}, indent=1))
    print(f"Wrote {OUT_DIR / f'calib_{stamp}.json'}")


if __name__ == "__main__":
    main()
