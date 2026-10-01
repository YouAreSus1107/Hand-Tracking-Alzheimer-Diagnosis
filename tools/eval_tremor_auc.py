#!/usr/bin/env python3
"""
Parkinson's vs control AUC for the tremor engine, on open wearable datasets.

    .venv/Scripts/python tools/eval_tremor_auc.py --pads C:/Datasets/PADS
    .venv/Scripts/python tools/eval_tremor_auc.py --pads C:/Datasets/PADS --limit 30   # smoke run

Companion to tools/eval_tremor_accel.py, whose camera simulation this reuses
unchanged (displacement, view, through_camera, load_carriers). That tool asked
"how big must a tremor be to be seen"; this one asks the screening question:
**ranked by the engine's own tremor score, how well are people with
Parkinson's separated from people without it?** Dataset survey and access
notes: docs/research/09-tremor-validation-datasets.md.

Data
----
  PADS  physionet.org/content/parkinsons-disease-smartwatch/1.0.0, CC BY-NC-SA
        4.0 (Varghese et al. 2024). 469 people: Parkinson's, differential
        diagnoses (incl. essential tremor) and healthy controls. An Apple Watch
        on each wrist, accel (g) + gyro (rad/s), 100 Hz. Tasks used here:
          rest      Relaxed (sitting relaxed), RelaxedTask (+ mental arithmetic)
          postural  StretchHold (arms out), HoldWeight
        The raw files hold the whole task (20.48 s for these), not the halves
        the dataset's preprocessing makes.
          <pads>/patients/patient_NNN.json, <pads>/movement/timeseries/*.txt
        Fetch: PhysioNet's zip runs at ~50 kB/s; the AWS open-data mirror
        (physionet-open.s3.amazonaws.com) is used instead.

Per record (one wrist, one task)
--------------------------------
  cam    the camera simulation of eval_tremor_accel: accel -> displacement
         (2-20 Hz) -> face-on 2-D view -> % of hand length -> added to each
         recorded still hand of the same hold kind -> analyse_hand. One result
         per carrier. A wrist moves less than the fingertips the camera scores,
         so amplitudes read low; ranking (AUC) does not care, detection rates
         at fixed thresholds do.
  ideal  the same displacement through analyse_hand at the sensor's own
         100 Hz with no carrier: the ceiling a perfect camera would reach.
  gyro   core/glove/imu.band_power on the gyro's principal axis (the glove
         path, as analyse_glove reads it): band_frac and rms.

Per person: the higher-scoring wrist (a tremor is often one-sided, and the
live test reports the stronger hand). For `cam`, the person's score is the
median over carriers of that max, so no single carrier decides it.

Analysis (fixed before any PADS result was seen)
------------------------------------------------
  E1  PRIMARY. PADS, Parkinson's vs healthy control, task Relaxed, score =
      cam prominence. AUC with a 2000-draw person-level bootstrap 95% CI,
      stratified by group.
  E2  Same, score = ideal prominence, gyro band_frac, cam amp_pct.
  E3  Task RelaxedTask (rest with mental arithmetic, a rest-tremor enhancer).
  E4  Postural: StretchHold, HoldWeight (postural carriers).
  E5  Verdicts at the thresholds in force (PROM_MIN, AMP_FLOOR_PCT): share of
      PD "detected" and "detected or possible" (sensitivity), share of
      controls not "detected" (specificity), per carrier then median. Rest =
      the more severe verdict of Relaxed's two wrists.
  E6  Parkinson's vs essential tremor (differential group, condition naming
      essential tremor), Relaxed and StretchHold, cam prominence. Rest tremor
      is the textbook separator, so Relaxed should beat StretchHold.
  E7  Exploratory: prominence with the band median measured away from the
      peak (excluding ±PEAK_HALF_WIDTH_HZ), the change recommended but not
      applied in research/09, recomputed from each result's own spectrum.
      Same endpoints as E1 and E5.
  X1  Per carrier AUC for E1, to show whether one noisy still hand (the
      2026-09-28 palm-down hold that flags at 4.46 Hz) drives anything.

Expectations written down beforehand: only some Parkinson's patients have a
visible rest tremor, so E1 has a low ceiling; ideal >= cam; E3 >= E1.

Added after the first full run (post hoc; E1-E7 above are unchanged)
-------------------------------------------------------------------
  First run, 2026-09-29: E1 = 0.545 (0.478-0.611), while the gyro alone
  reached 0.66-0.77. A watch's translation is tiny (median 0.02 % of hand
  length, far under the camera's noise), but rest tremor is mostly rotation
  (pronation-supination), which swings the fingertips the camera scores and
  which double-integrated wrist acceleration barely sees. So:
  P1  source `rot` / `rot_ideal`: gyro integrated once to angle (2-20 Hz,
      rad), the two principal axes, times one hand length = fingertip
      displacement in % of hand length (small-angle arc). Through the camera
      and ideal, as `cam` and `ideal`. Same endpoints as E1, E3, E4, E5.

Parkinson@Home (--pathome; fixed before its sensor data was opened)
-------------------------------------------------------------------
  doi.org/10.34973/2xxa-g520, CC0 (Radboud, 2025). 25 Parkinson's, 24
  controls, a Physilog on each wrist, accel (g) + gyro, 200 Hz, ~1 h of
  unscripted life at home OFF medication, then ON. Video annotation
  (docs/video_annotation_protocol.pdf): mobility states for everyone; for
  the 9 patients whose screening found tremor, the whole visit coded per
  segment 0 = hand still, no tremor | 1 / 2 / 3 = hand still, tremor
  < 3 / 3-10 / > 10 cm | 96-98 = hand busy | 99 = not visible.
    <pathome>/sensor_data/phys_cur_{PD,HC}_merged.mat   (MATLAB 7.3: h5py)
    <pathome>/video_annotations/labels_*.mat             (tables: mat-io)
    <pathome>/clinical_data/patient_info.csv             (MDS-UPDRS III)
  Daily life is not a hold, so the voluntary-movement gate must work: the
  gyro is integrated to angle from 0.2 Hz (not 2 Hz as for PADS), leaving
  slow movement in, and analyse_hand's own move_max rejects it exactly as it
  would on camera. Fingertip = angle x one hand length. Windows are 20 s
  (a hold), 10 s apart; score = the stronger wrist, as the live test.
  H1  PRIMARY for this set. 9 tremor-annotated patients, OFF and ON: windows
      wholly inside one code-0 segment vs one code 1-3 segment. AUC of
      rot_ideal prominence, bootstrap over people (windows stay with their
      person). Also verdict shares by code, and the same through the camera
      carriers on up to 40 windows per person per class.
  H2  Parkinson's vs control: windows in "sitting" during the first free-
      living part (OFF for patients); person score = the share of scored
      windows called "detected", and the 95th percentile of prominence.
  H3  Within Parkinson's: OFF MDS-UPDRS 3.17a/b max >= 1 vs 0, H2's scores.
  Amended after a one-control smoke run, before any H result was computed:
  in daily life, slow movement leaks into the bottom of the band, so healthy
  sitting windows showed prominence 150-300 at 3.5-4 Hz with 0.1-0.4 %
  amplitude (verdict "none", correctly). Prominence alone is therefore not a
  ranking score here. H1's primary score becomes the verdict (none <
  possible < detected), what the test reports; secondaries are prominence
  and "interior prominence" (prominence when the peak is > EDGE_HZ inside
  the band, else 0). H2's p95 uses interior prominence.

Writes results/tremor_eval/auc_<timestamp>.csv (one row per record x source)
and .json (summaries); --pathome writes pathome_<timestamp>.* instead.
"""

from __future__ import annotations

import argparse
import csv
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

from core.glove.imu import band_power
from core.tremor import metrics as tm
from core.tremor.phases import PHASES
from eval_tremor_accel import (EDGE_HZ, OUT_DIR, PALM_CM, UP_FS, displacement, load_carriers,
                               through_camera, view)

G = 9.80665
REST_MOVE = PHASES["rest_palm_up"].move_max if "rest_palm_up" in PHASES else 0.15
POST_MOVE = PHASES["postural"].move_max if "postural" in PHASES else 0.60
PADS_TASKS = {"Relaxed": "rest", "RelaxedTask": "rest",
              "StretchHold": "postural", "HoldWeight": "postural"}
N_BOOT = 2000
RANK = {"none": 0, "possible": 1, "detected": 2}


# ── statistics ───────────────────────────────────────────────────────────────

def auc(pos, neg) -> float | None:
    """Mann-Whitney AUC, ties counted half: P(score_pos > score_neg)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    while i < len(sv):                       # average ranks over ties
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    r_pos = ranks[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def auc_ci(pos, neg, seed=0) -> dict:
    a = auc(pos, neg)
    if a is None:
        return {"auc": None, "n_pos": len(pos), "n_neg": len(neg)}
    rng = np.random.default_rng(seed)
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    boots = [auc(rng.choice(pos, len(pos)), rng.choice(neg, len(neg))) for _ in range(N_BOOT)]
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"auc": round(a, 3), "ci95": [round(float(lo), 3), round(float(hi), 3)],
            "n_pos": len(pos), "n_neg": len(neg)}


def prom_off_peak(res: dict) -> float | None:
    """E7: peak / median of the band with ±PEAK_HALF_WIDTH_HZ around the peak
    left out, from the result's own 0.25 Hz amplitude-density spectrum."""
    if not res.get("scored") or not res.get("spectrum"):
        return None
    f = np.array([p[0] for p in res["spectrum"]])
    p = np.array([p[1] for p in res["spectrum"]]) ** 2          # amplitude -> power
    lo, hi = res["band"]
    band = (f >= lo) & (f <= hi)
    pk = f[band][int(np.argmax(p[band]))]
    rest = band & (np.abs(f - pk) > tm.PEAK_HALF_WIDTH_HZ)
    if rest.sum() < 2:
        return None
    med = float(np.median(p[rest]))
    return float(p[band].max() / med) if med > 0 else None


# ── data ─────────────────────────────────────────────────────────────────────

def _pads_group(condition: str) -> str:
    c = condition.lower()
    if c.startswith("healthy"):
        return "HC"
    if c.startswith("parkinson"):
        return "PD"
    if "essential" in c:
        return "ET"
    return "DD"


def load_pads(root: Path, limit: int | None = None) -> list[dict]:
    recs = []
    pats = sorted((root / "patients").glob("patient_*.json"))
    if limit:
        # spread a smoke run over every group rather than the first N ids
        pats = pats[::max(1, len(pats) // limit)][:limit]
    for fp in pats:
        p = json.loads(fp.read_text(encoding="utf-8"))
        pid = str(p["id"]).zfill(3)
        cond = str(p.get("condition", ""))
        group = _pads_group(cond)
        for task, hold in PADS_TASKS.items():
            for wrist in ("Left", "Right"):
                ts = root / "movement" / "timeseries" / f"{pid}_{task}_{wrist}Wrist.txt"
                if not ts.exists():
                    continue
                a = np.loadtxt(ts, delimiter=",", ndmin=2)
                if a.shape[1] == 7:                  # a leading time column
                    a = a[:, 1:]
                if a.shape[1] != 6 or len(a) < 400:
                    continue
                recs.append({"ds": "PADS", "person": f"PADS{pid}", "group": group,
                             "condition": cond, "task": task, "hold": hold,
                             "wrist": wrist.lower(), "fs": 100.0,
                             "acc": a[:, :3] * G, "gyro": a[:, 3:6]})
    return recs


# ── scoring one record ───────────────────────────────────────────────────────

def _pick(res: dict) -> dict:
    return {"scored": bool(res.get("scored")), "why": res.get("why"),
            "peak_hz": res.get("peak_hz"), "prominence": res.get("prominence"),
            "amp_pct": res.get("amp_pct"), "verdict": res.get("verdict"),
            "prom_off_peak": prom_off_peak(res)}


def score_record(rec: dict, carriers: dict) -> list[dict]:
    move = REST_MOVE if rec["hold"] == "rest" else POST_MOVE
    disp = displacement(rec["acc"], rec["fs"]) * 100.0 / PALM_CM * 100.0   # m -> % hand
    xy = view(disp, "face")
    out = []

    # ideal camera: the displacement itself at a clean 100 Hz, no carrier
    step = int(round(UP_FS / rec["fs"]))
    ideal_xy = xy[::step]
    t = np.arange(len(ideal_xy)) / rec["fs"]
    res = tm.analyse_hand(t, ideal_xy[:, None, :], np.full(len(t), 100.0), move_max=move)
    out.append({"source": "ideal", "carrier": "", **_pick(res)})

    # glove path: gyro principal axis
    g = rec["gyro"] - rec["gyro"].mean(axis=0)
    _, _, vt = np.linalg.svd(g, full_matrices=False)
    bp = band_power((g @ vt[0]).tolist(), rec["fs"])
    out.append({"source": "gyro", "carrier": "", "scored": bp is not None,
                "peak_hz": bp and round(bp["peak_hz"], 2),
                "band_frac": bp and round(bp["band_frac"], 4),
                "gyro_rms": bp and round(bp["rms"] or 0.0, 5)})

    for c in carriers[rec["hold"]]:
        out.append({"source": "cam", "carrier": c["id"], **_pick(through_camera(xy, c))})

    # P1 (post hoc): the fingertip arc a wrist rotation makes, one hand length out
    rot_xy = view(angle(rec["gyro"], rec["fs"]) * 100.0, "face")           # rad -> % hand
    t = np.arange(len(rot_xy[::step])) / rec["fs"]
    res = tm.analyse_hand(t, rot_xy[::step][:, None, :], np.full(len(t), 100.0), move_max=move)
    out.append({"source": "rot_ideal", "carrier": "", **_pick(res)})
    for c in carriers[rec["hold"]]:
        out.append({"source": "rot", "carrier": c["id"], **_pick(through_camera(rot_xy, c))})
    return out


def angle(gyro: np.ndarray, fs: float) -> np.ndarray:
    """Angular rate (n, 3) rad/s -> angle, rad, 2-20 Hz, on the UP_FS grid:
    displacement()'s frequency-domain integration and taper, done once."""
    from fractions import Fraction
    from scipy.signal import resample_poly
    from eval_tremor_accel import _taper
    fr = Fraction(UP_FS / fs).limit_denominator(100)
    g = resample_poly(gyro - gyro.mean(axis=0), fr.numerator, fr.denominator, axis=0)
    n = len(g)
    spec = np.fft.rfft(g, axis=0)
    f = np.fft.rfftfreq(n, 1.0 / UP_FS)
    w = 2 * np.pi * np.where(f > 0, f, 1.0)
    spec *= (_taper(f) / (1j * w))[:, None]
    spec[0] = 0
    return np.fft.irfft(spec, n=n, axis=0)


def run(recs, carriers) -> list[dict]:
    rows = []
    for i, rec in enumerate(recs, 1):
        meta = {k: rec[k] for k in ("ds", "person", "group", "condition", "task", "hold", "wrist")}
        for r in score_record(rec, carriers):
            rows.append({**meta, **r})
        if i % 200 == 0:
            print(f"  {i}/{len(recs)} records", flush=True)
    return rows


# ── the pre-registered summaries ─────────────────────────────────────────────

def person_scores(rows, task, source, key, carrier=None) -> dict:
    """{person: (group, score)}: max over wrists, then median over carriers."""
    per = {}
    for r in rows:
        if r["task"] != task or r["source"] != source or r.get(key) is None:
            continue
        if carrier is not None and r["carrier"] != carrier:
            continue
        per.setdefault(r["person"], [r["group"], {}])
        d = per[r["person"]][1]
        d[r["carrier"]] = max(d.get(r["carrier"], -math.inf), float(r[key]))
    return {p: (g, float(np.median(list(d.values())))) for p, (g, d) in per.items()}


def compare(scores: dict, pos="PD", neg="HC", seed=0) -> dict:
    return auc_ci([s for g, s in scores.values() if g == pos],
                  [s for g, s in scores.values() if g == neg], seed)


def verdicts(rows, task, key="verdict", prom_min=None, source="cam") -> dict:
    """E5: per carrier, each person's most severe wrist; then median shares."""
    per_c = {}
    for r in rows:
        if r["task"] != task or r["source"] != source or not r["scored"]:
            continue
        v = r[key] if prom_min is None else _reclass(r, prom_min)
        d = per_c.setdefault(r["carrier"], {})
        g, best = d.get(r["person"], (r["group"], "none"))
        d[r["person"]] = (g, v if RANK[v] > RANK[best] else best)
    stats = {"pd_detected": [], "pd_any": [], "hc_not_detected": [], "hc_none": []}
    for d in per_c.values():
        pd = [v for g, v in d.values() if g == "PD"]
        hc = [v for g, v in d.values() if g == "HC"]
        if pd:
            stats["pd_detected"].append(np.mean([v == "detected" for v in pd]))
            stats["pd_any"].append(np.mean([v != "none" for v in pd]))
        if hc:
            stats["hc_not_detected"].append(np.mean([v != "detected" for v in hc]))
            stats["hc_none"].append(np.mean([v == "none" for v in hc]))
    return {k: round(float(np.median(v)), 3) if v else None for k, v in stats.items()}


def _reclass(r, prom_min) -> str:
    """E7 verdicts: classify with the off-peak prominence."""
    p = r.get("prom_off_peak")
    if p is None:
        return r["verdict"]
    if p >= prom_min and r["amp_pct"] >= tm.AMP_FLOOR_PCT:
        return "detected"
    return "possible" if p >= tm.PROM_POSSIBLE else "none"


def summarise(rows) -> dict:
    out = {}
    out["groups"] = {g: len({r["person"] for r in rows if r["group"] == g})
                     for g in sorted({r["group"] for r in rows})}
    out["E1_primary"] = compare(person_scores(rows, "Relaxed", "cam", "prominence"))
    out["E2_scores"] = {
        "ideal_prominence": compare(person_scores(rows, "Relaxed", "ideal", "prominence")),
        "gyro_band_frac": compare(person_scores(rows, "Relaxed", "gyro", "band_frac")),
        "gyro_rms": compare(person_scores(rows, "Relaxed", "gyro", "gyro_rms")),
        "cam_amp_pct": compare(person_scores(rows, "Relaxed", "cam", "amp_pct"))}
    out["E3_relaxed_task"] = {
        "cam_prominence": compare(person_scores(rows, "RelaxedTask", "cam", "prominence")),
        "ideal_prominence": compare(person_scores(rows, "RelaxedTask", "ideal", "prominence")),
        "gyro_band_frac": compare(person_scores(rows, "RelaxedTask", "gyro", "band_frac"))}
    out["E4_postural"] = {
        t: {"cam_prominence": compare(person_scores(rows, t, "cam", "prominence")),
            "ideal_prominence": compare(person_scores(rows, t, "ideal", "prominence")),
            "gyro_band_frac": compare(person_scores(rows, t, "gyro", "band_frac"))}
        for t in ("StretchHold", "HoldWeight")}
    out["E5_verdicts"] = {t: verdicts(rows, t) for t in ("Relaxed", "RelaxedTask", "StretchHold")}
    out["E6_pd_vs_et"] = {
        t: compare(person_scores(rows, t, "cam", "prominence"), pos="PD", neg="ET")
        for t in ("Relaxed", "StretchHold")}
    out["E7_off_peak"] = {
        "auc": compare(person_scores(rows, "Relaxed", "cam", "prom_off_peak")),
        "verdicts_relaxed": verdicts(rows, "Relaxed", prom_min=tm.PROM_MIN)}
    out["P1_rotation"] = {
        t: {"rot_prominence": compare(person_scores(rows, t, "rot", "prominence")),
            "rot_amp_pct": compare(person_scores(rows, t, "rot", "amp_pct")),
            "rot_ideal_prominence": compare(person_scores(rows, t, "rot_ideal", "prominence")),
            "verdicts": verdicts(rows, t, source="rot")}
        for t in PADS_TASKS}
    out["X1_per_carrier"] = {
        c: compare(person_scores(rows, "Relaxed", "cam", "prominence", carrier=c))["auc"]
        for c in sorted({r["carrier"] for r in rows
                         if r["source"] == "cam" and r["hold"] == "rest"})}
    return out


# ── Parkinson@Home ───────────────────────────────────────────────────────────

PH_FS = 200.0
PH_WIN_S, PH_HOP_S = 20.0, 10.0
PH_HP_HZ = 0.2                   # keep slow movement in, for the gate to see
PH_CAM_PER_CLASS = 40
ROT_FS = 100.0                   # analyse the angle at 100 Hz, as PADS
BAND_LO = tm.TREMOR_BAND[0]
BAND_HI_IDEAL = min(tm.TREMOR_BAND[1], 0.95 * ROT_FS / 2)


def _cell(v):
    while isinstance(v, np.ndarray) and v.dtype == object and v.size == 1:
        v = v.ravel()[0]
    return v


def _num(v):
    v = _cell(v)
    return float(np.ravel(v)[0]) if isinstance(v, np.ndarray) and v.size else None


def _segments_of(tbl, t0: float) -> list[tuple[float, float, float]]:
    """ELAN table (Start, Duration in 200 Hz samples from t0) -> (start s, end s, code)."""
    import pandas as pd
    if not isinstance(tbl, pd.DataFrame):
        return []
    out = []
    for s, d, c in zip(tbl["Start"], tbl["Duration"], tbl["Code"]):
        a = t0 + (float(s) - 1.0) / PH_FS
        out.append((a, a + float(d) / PH_FS, float(np.ravel(c)[0])))
    return out


def load_pathome_labels(root: Path) -> dict:
    """{id: {"group", "sitting": [(a, b)], "tremor": [(a, b, code)], "u317": int|None}}"""
    import pandas as pd
    from matio import load_from_mat
    ci = pd.read_csv(root / "clinical_data" / "patient_info.csv", sep=";")
    ci["record_id"] = ci["record_id"].str.strip("'")
    ci = ci.set_index("record_id")
    out = {}
    for fn, group in (("labels_PD_phys_tremor.mat", "PD"), ("labels_HC_phys.mat", "HC")):
        for e in load_from_mat(root / "video_annotations" / fn)["labels"].ravel():
            pid = str(np.ravel(_cell(e["id"]))[0])
            first, start = ("premed", "premedstart") if group == "PD" else ("pre", "prestart")
            mob = _segments_of(_cell(e[first]), _num(e[start]))
            tremor = []
            if group == "PD":
                for part in ("premed", "postmed"):
                    t0 = _num(e[f"{part}_tremorstart"])
                    if t0 is not None:
                        tremor += _segments_of(_cell(e[f"{part}_tremor"]), t0)
            u = None
            if pid in ci.index:
                vals = ci.loc[pid, ["OFF_UPDRS_3_17a", "OFF_UPDRS_3_17b"]].astype(float)
                u = None if vals.isna().all() else int(vals.max())
            out[pid] = {"group": group, "u317": u, "tremor": tremor,
                        "sitting": [(a, b) for a, b, c in mob if c == 1.0]}
    return out


def pathome_people(root: Path):
    """Yield (id, {"LW"|"RW": (t, gyro deg/s (n, 3))}) one person at a time:
    each file is ~2-3 GB, so nothing is held for longer than one person."""
    import h5py
    for group in ("PD", "HC"):
        with h5py.File(root / "sensor_data" / f"phys_cur_{group}_merged.mat", "r") as f:
            phys = f["phys"]
            for i in range(phys["id"].shape[0]):
                pid = "".join(chr(int(c)) for c in f[phys["id"][i, 0]][()].ravel())
                wr = {}
                for side in ("LW", "RW"):
                    s = f[phys[side][i, 0]]
                    g = s["gyro"][()]
                    wr[side] = (g[0], g[1:4].T)
                yield pid, wr


def _gain(f, hp, lp=20.0):
    g = np.ones_like(f)
    lo = f < hp
    g[lo] = 0.5 - 0.5 * np.cos(np.pi * np.clip((f[lo] - hp / 2) / (hp / 2), 0, 1))
    hi = f > lp
    g[hi] = 0.5 + 0.5 * np.cos(np.pi * np.clip((f[hi] - lp) / lp, 0, 1))
    return g


def rot_window(gyro_deg: np.ndarray, fs: float) -> np.ndarray:
    """One window of gyro (deg/s) -> fingertip arc, % of hand length, (n, 2),
    face-on, integrated from PH_HP_HZ so the slow movement stays in."""
    g = np.deg2rad(gyro_deg - gyro_deg.mean(axis=0))
    n = len(g)
    spec = np.fft.rfft(g, axis=0)
    f = np.fft.rfftfreq(n, 1.0 / fs)
    w = 2 * np.pi * np.where(f > 0, f, 1.0)
    spec *= (_gain(f, PH_HP_HZ) / (1j * w))[:, None]
    spec[0] = 0
    return view(np.fft.irfft(spec, n=n, axis=0) * 100.0, "face")


def _windows(spans, win=PH_WIN_S, hop=PH_HOP_S):
    for a, b, *rest in spans:
        s = a
        while s + win <= b:
            yield s, s + win, (rest[0] if rest else None)
            s += hop


def score_pathome_window(wrists: dict, a: float, b: float, carriers=None) -> list[dict]:
    out = []
    for side, (t, g) in wrists.items():
        i, j = np.searchsorted(t, [a, b])
        if j - i < 0.9 * PH_WIN_S * PH_FS:
            continue
        xy = rot_window(g[i:j], PH_FS)
        step = int(round(PH_FS / ROT_FS))
        xs = xy[::step]
        ts = np.arange(len(xs)) / ROT_FS
        res = tm.analyse_hand(ts, xs[:, None, :], np.full(len(ts), 100.0), move_max=REST_MOVE)
        out.append({"wrist": side, "source": "rot_ideal", "carrier": "", **_pick(res)})
        for c in carriers or ():
            grid = np.arange(int(len(xy) * UP_FS / PH_FS)) / UP_FS
            up = np.column_stack([np.interp(grid, np.arange(len(xy)) / PH_FS, xy[:, k])
                                  for k in range(2)])
            out.append({"wrist": side, "source": "rot", "carrier": c["id"],
                        **_pick(through_camera(up, c))})
    return out


def run_pathome(root: Path, carriers: dict, limit=None) -> list[dict]:
    labels = load_pathome_labels(root)
    rng = np.random.default_rng(0)
    rows = []
    for k, (pid, wrists) in enumerate(pathome_people(root)):
        if limit and k >= limit:
            break
        lab = labels.get(pid)
        if lab is None:
            print(f"  {pid}: no labels, skipped")
            continue
        base = {"ds": "PATHOME", "person": pid, "group": lab["group"], "u317": lab["u317"]}
        # H1: tremor-coded windows, code 0 vs 1-3
        coded = [(a, b, c) for a, b, c in _windows(
            [s for s in lab["tremor"] if s[2] in (0.0, 1.0, 2.0, 3.0)])]
        cam_pick = set()
        for cls in (0, 1):
            idx = [n for n, w in enumerate(coded) if (w[2] > 0) == bool(cls)]
            cam_pick.update(rng.choice(idx, min(PH_CAM_PER_CLASS, len(idx)), replace=False).tolist()
                            if idx else [])
        for n, (a, b, c) in enumerate(coded):
            for r in score_pathome_window(wrists, a, b,
                                          carriers["rest"] if n in cam_pick else None):
                rows.append({**base, "part": "H1", "win": round(a, 1), "code": int(c), **r})
        # H2/H3: sitting windows, first free-living part
        for a, b, _ in _windows([(a, b) for a, b in lab["sitting"]]):
            for r in score_pathome_window(wrists, a, b):
                rows.append({**base, "part": "H2", "win": round(a, 1), "code": None, **r})
        print(f"  {pid}: {len(coded)} coded windows, "
              f"{sum(1 for r in rows if r['person'] == pid and r['part'] == 'H2') // 2} sitting",
              flush=True)
    return rows


def _win_best(rows, part, source, carrier_median=False):
    """{(person, win): (group, code, u317, prominence, verdict)} over the stronger wrist
    (and, for the camera, the median prominence over carriers)."""
    acc = {}
    for r in rows:
        if r["part"] != part or r["source"] != source or not r["scored"]:
            continue
        k = (r["person"], r["win"])
        d = acc.setdefault(k, {"meta": (r["group"], r["code"], r["u317"]), "c": {}})
        interior = BAND_LO + EDGE_HZ < r["peak_hz"] < BAND_HI_IDEAL - EDGE_HZ
        cur = (RANK[r["verdict"]], r["prominence"], r["prominence"] if interior else 0.0)
        prev = d["c"].get(r["carrier"])
        # the stronger wrist: most severe verdict, then the higher prominence
        d["c"][r["carrier"]] = cur if prev is None else tuple(max(x, y) for x, y in zip(prev, cur))
    out = {}
    for k, d in acc.items():
        vals = np.array(list(d["c"].values()))
        agg = np.median(vals, axis=0) if carrier_median else vals.max(axis=0)
        out[k] = (*d["meta"], {"ord": float(agg[0]), "prom": float(agg[1]),
                               "prom_int": float(agg[2])})
    return out


def _clustered_auc(pos: dict, neg: dict, seed=0) -> dict:
    """AUC of windows, bootstrap resampling people (each keeps its windows)."""
    a = auc([v for vs in pos.values() for v in vs], [v for vs in neg.values() for v in vs])
    if a is None:
        return {"auc": None}
    people = sorted(set(pos) | set(neg))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(N_BOOT):
        draw = rng.choice(people, len(people))
        p = [v for q in draw for v in pos.get(q, [])]
        n = [v for q in draw for v in neg.get(q, [])]
        b = auc(p, n)
        if b is not None:
            boots.append(b)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"auc": round(a, 3), "ci95": [round(float(lo), 3), round(float(hi), 3)],
            "n_pos": sum(map(len, pos.values())), "n_neg": sum(map(len, neg.values())),
            "people": len(people)}


def summarise_pathome(rows) -> dict:
    out = {"groups": {g: len({r["person"] for r in rows if r["group"] == g}) for g in ("PD", "HC")}}
    for src, med in (("rot_ideal", False), ("rot", True)):
        w = _win_best(rows, "H1", src, carrier_median=med)
        res = {}
        for key in ("ord", "prom", "prom_int"):
            pos, neg = {}, {}
            for (p, _), (g, code, u, s) in w.items():
                (pos if code > 0 else neg).setdefault(p, []).append(s[key])
            res[key] = _clustered_auc(pos, neg)
        by_code = {}
        for (p, _), (g, code, u, s) in w.items():
            by_code.setdefault(code, []).append(s["ord"])
        res["verdicts_by_code"] = {
            str(c): {"n": len(vs), "detected": round(float(np.mean([v >= 2 for v in vs])), 3),
                     "any": round(float(np.mean([v >= 1 for v in vs])), 3)}
            for c, vs in sorted(by_code.items())}
        out[f"H1_{src}"] = res
    w = _win_best(rows, "H2", "rot_ideal")
    per = {}
    for (p, _), (g, code, u, s) in w.items():
        per.setdefault(p, {"g": g, "u": u, "prom": [], "det": []})
        per[p]["prom"].append(s["prom_int"])
        per[p]["det"].append(s["ord"] >= 2)
    s_det = {p: (d["g"], float(np.mean(d["det"]))) for p, d in per.items()}
    s_p95 = {p: (d["g"], float(np.quantile(d["prom"], 0.95))) for p, d in per.items()}
    out["H2_pd_vs_hc"] = {"detected_share": compare(s_det), "prominence_p95": compare(s_p95),
                          "windows_per_person_median": int(np.median([len(d["prom"]) for d in per.values()]))}
    pd_ = {p: d for p, d in per.items() if d["g"] == "PD" and d["u"] is not None}
    u_det = {p: ("T" if d["u"] >= 1 else "N", float(np.mean(d["det"]))) for p, d in pd_.items()}
    u_p95 = {p: ("T" if d["u"] >= 1 else "N", float(np.quantile(d["prom"], 0.95))) for p, d in pd_.items()}
    out["H3_updrs317"] = {"detected_share": compare(u_det, pos="T", neg="N"),
                          "prominence_p95": compare(u_p95, pos="T", neg="N")}
    return out


def _write(prefix: str, rows: list[dict], meta: dict, summary: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(OUT_DIR / f"{prefix}_{stamp}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    out = OUT_DIR / f"{prefix}_{stamp}.json"
    out.write_text(json.dumps({**meta, "engine": {
        "version": tm.ENGINE_VERSION, "PROM_MIN": tm.PROM_MIN, "PROM_POSSIBLE": tm.PROM_POSSIBLE,
        "AMP_FLOOR_PCT": tm.AMP_FLOOR_PCT}, "n_rows": len(rows), **summary}, indent=1),
        encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--pads", type=Path, default=Path("C:/Datasets/PADS"))
    ap.add_argument("--pathome", type=Path, default=None,
                    help="run the Parkinson@Home analysis (H1-H3) instead of PADS")
    ap.add_argument("--results", type=Path, default=_REPO_ROOT / "results")
    ap.add_argument("--carriers", choices=("landmarks", "flow"), default="landmarks")
    ap.add_argument("--limit", type=int, default=None, help="people, for a smoke run")
    a = ap.parse_args()

    cs = load_carriers(a.results, a.carriers)
    carriers = {k: [c for c in cs if c["kind"] == k] for k in ("rest", "postural")}
    if not carriers["rest"] or not carriers["postural"]:
        sys.exit("Need recorded rest and postural tremor holds in results/ as noise carriers.")
    print(f"Carriers: {len(carriers['rest'])} rest, {len(carriers['postural'])} postural")
    meta = {"carriers": a.carriers, "limit": a.limit}

    if a.pathome:
        rows = run_pathome(a.pathome, carriers, a.limit)
        summary = summarise_pathome(rows)
        out = _write("pathome", rows, meta, summary)
    else:
        recs = load_pads(a.pads, a.limit)
        if not recs:
            sys.exit(f"No PADS records under {a.pads}")
        print(f"PADS: {len({r['person'] for r in recs})} people, {len(recs)} records")
        rows = run(recs, carriers)
        summary = summarise(rows)
        out = _write("auc", rows, meta, summary)
    print(json.dumps(summary, indent=1))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
