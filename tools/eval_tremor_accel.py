#!/usr/bin/env python3
"""
Real tremor through the camera tremor engine: two open accelerometer datasets.

    .venv/Scripts/python tools/eval_tremor_accel.py --et C:/Datasets/ET-Accel --arm C:/Datasets/ArmTremor
    .venv/Scripts/python tools/eval_tremor_accel.py ... --limit 5      # smoke run

Neither dataset has video, so neither can say whether MediaPipe sees a
tremor. What they can do is put REAL tremor waveforms (irregular, drifting in
frequency, with harmonics) through core/tremor/metrics.analyse_hand exactly as
the live test calls it, at the frame times and on top of the tracking noise of
real camera recordings. That tests the part of the engine the synthetic unit
tests cannot: the Welch spectrum at ~17 fps, the aliasing above the band top,
the voluntary-movement gate, and the provisional detection thresholds
(PROM_MIN, PROM_POSSIBLE, AMP_FLOOR_PCT), which were bracketed on synthetic
noise only (docs/tests/TREMOR_TEST_PLAN.md §4).

Data (docs/research/09-tremor-validation-datasets.md):

  ET   zenodo.org/records/19130599, CC-BY 4.0. 29 essential tremor patients,
       both hands, rest and arms-out, one accelerometer axis on the back of
       the hand, 5 kHz, band-passed 2 Hz-2 kHz, amplified x1000. The units
       are volts, not m/s², so ET amplitude cannot be put in centimetres.
       FTM total score per patient.
         <et>/acc_signal_database.mat, <et>/clinical_data.mat
  ARM  zenodo.org/records/4772130 (v2 of 4698248), CC-BY 4.0. 37 people:
       2 ET, 8 Parkinson's, 27 no diagnosed tremor. 3-axis accelerometers on
       index tip, thumb tip, metacarpal and wrist, 62.5 Hz, m/s², ~30 s rest
       and ~30 s postural. Calibrated, so amplitude is absolute.
         <arm>/database.mat   (MATLAB table objects: needs `pip install mat-io`)

Camera simulation, per record:

  1. Reference: Welch peak of the accelerometer at its own rate, 3.5-12 Hz,
     4 s Hann windows; prominence = peak / band median, as the engine does.
  2. Displacement: accel double-integrated in the frequency domain, 2-20 Hz
     (cosine-tapered edges). An accelerometer also sees gravity rotate, which
     double-integrates into displacement that never happened, so the ARM
     amplitudes are an upper bound. Frequency is unaffected.
  3. 2-D view: ARM's three axes are projected onto their first two principal
     components ("face-on", the camera sees the tremor plane) and onto PCs
     2-3 ("edge-on", the worst the camera could be placed). ET has one axis.
  4. Carrier: every hand-phase trace saved in results/*tremor*.json (index
     fingertip, % of hand length, real timestamps; --carriers flow uses the
     optical-flow trace of the same hold instead, runs from tremor_test 0.2). The tremor is read at
     those timestamps and added to the carrier, which brings the real frame
     rate, frame drops, drift and MediaPipe jitter with it. Rest records
     ride rest carriers, postural records postural carriers, each with that
     hold's move_max. Every record is run on every matching carrier.
  5. Engine: analyse_hand(ts, pts, lens=100) with pts one landmark, so the
     result is in % of hand length, as a live run's is.

Analysis (fixed before any results were seen):

  C0  carriers alone: verdicts, peak prominence -- the false-alarm floor of
      the recorded still hands
  F1  frequency: for records whose reference is a clear tremor (prominence
      >= 10), |engine peak - reference peak|: median, share <= 0.5 Hz and
      <= 1 Hz, split by whether the reference lies below the carrier's band
      top (resolvable) or above it (aliased by construction)
  D1  ARM detection by group x hold x view: share detected / possible / none.
      Specificity = no-tremor group not "detected"; sensitivity = PD/ET
      "detected" or "possible"
  D2  ET detection vs amplitude: each record scaled to 0.5, 1, 1.5, 2, 3, 4 %
      RMS in 3.5-12 Hz, share detected per level (uncalibrated units, so the
      level is imposed, not measured). Split by whether the reference itself
      shows a clear tremor: scaling a record with none up to 4 % makes broadband
      noise, not a tremor, and a peak detector is right to pass it. (This split
      was added after a 3-record smoke run, before the full run.)
  D3  threshold sweep on ARM face-on: sensitivity / specificity for
      PROM_MIN x AMP_FLOOR_PCT. Descriptive only -- 10 patients and 27
      controls are not enough to set a threshold, and these are not camera
      recordings of those people
  G1  glove path: ARM metacarpal at 62.5 Hz through core/glove/imu.band_power
      on ||a|| (what analyse_glove uses for the accelerometer) and on the
      principal axis, against the reference peak

Changed after the first full run, before the numbers below were read
(docs/research/09-tremor-validation-datasets.md records both runs):

  * A "clear" reference must also be an interior peak (> EDGE_HZ from either
    band edge): a maximum at exactly 3.50 Hz is power rising toward the band's
    floor, not a tremor.
  * F1's primary reference became the POSITION spectrum of the same stretch
    the camera saw (seg_*). The whole-record accelerometer peak read 0.4 Hz
    higher than the camera even at 4 % amplitude, where camera noise no longer
    matters: position is acceleration / f², which pulls a broad peak lower,
    and a 70 s record drifts in frequency. That gap is kept as F1_accel_ref,
    since the glove comparison (a gyro, i.e. velocity, against camera
    position) has half of the same bias. D2 and P1 use the same stretch.
  * P1, P2, P4 were added: detection where the stretch holds a clear tremor,
    frequency error where the engine flagged one, and which carriers the
    control flags came from.

Unit is one hand-hold; no inferential statistics (too few people per group).
Writes results/tremor_eval/accel_<timestamp>.csv and .json.
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

from core.glove.imu import band_power
from core.tremor import metrics as tm
from core.tremor.phases import PHASES

OUT_DIR = _REPO_ROOT / "results" / "tremor_eval"
BAND = tm.TREMOR_BAND
REF_PROM = 10.0                     # F1: what counts as a clear reference tremor
EDGE_HZ = 0.25                      # a peak this close to a band edge is a slope, not a peak
PALM_CM = tm.PALM_LEN_CM            # the engine's own assumed hand length
HP_HZ, LP_HZ = 2.0, 20.0            # displacement band
UP_FS = 250.0                       # grid the displacement is read from
ET_LEVELS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
SWEEP_PROM = (3.5, 4.5, 6.0, 8.0, 10.0, 15.0)
SWEEP_AMP = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
REST_KEYS = ("rest", "rest_count", "rest_palm_up", "rest_palm_down")


# ── signal helpers ───────────────────────────────────────────────────────────

def ref_spectrum(x: np.ndarray, fs: float) -> dict | None:
    """Welch peak in the tremor band at the sensor's own rate."""
    from scipy.signal import welch
    x = np.asarray(x, float)
    if x.ndim == 1:
        x = x[:, None]
    if len(x) < 4 * fs:
        return None
    f, p = welch(x - x.mean(axis=0), fs=fs, window="hann", nperseg=int(4 * fs),
                 noverlap=int(2 * fs), nfft=int(16 * fs), detrend="linear", axis=0)
    p = p.sum(axis=1)                         # x + y together, as the engine does
    band = (f >= BAND[0]) & (f <= BAND[1])
    pk = int(np.argmax(p[band]))
    med = float(np.median(p[band]))
    hz = float(f[band][pk])
    return {"peak_hz": round(hz, 2),
            "prominence": round(float(p[band][pk] / med), 2) if med > 0 else 0.0,
            "interior": BAND[0] + EDGE_HZ < hz < BAND[1] - EDGE_HZ}


def _taper(f: np.ndarray) -> np.ndarray:
    """Band gain 2-20 Hz with half-cosine edges one octave-ish wide."""
    g = np.ones_like(f)
    lo = f < HP_HZ
    g[lo] = 0.5 - 0.5 * np.cos(np.pi * np.clip((f[lo] - HP_HZ / 2) / (HP_HZ / 2), 0, 1))
    hi = f > LP_HZ
    g[hi] = 0.5 + 0.5 * np.cos(np.pi * np.clip((f[hi] - LP_HZ) / LP_HZ, 0, 1))
    return g


def displacement(acc: np.ndarray, fs: float) -> np.ndarray:
    """Acceleration (n, c) -> displacement, same units x s², on a UP_FS grid."""
    from scipy.signal import resample_poly
    from fractions import Fraction
    acc = np.asarray(acc, float)
    if acc.ndim == 1:
        acc = acc[:, None]
    fr = Fraction(UP_FS / fs).limit_denominator(100)
    acc = resample_poly(acc - acc.mean(axis=0), fr.numerator, fr.denominator, axis=0)
    n = len(acc)
    spec = np.fft.rfft(acc, axis=0)
    f = np.fft.rfftfreq(n, 1.0 / UP_FS)
    w = 2 * np.pi * np.where(f > 0, f, 1.0)
    spec *= (_taper(f) / -(w ** 2))[:, None]
    spec[0] = 0
    return np.fft.irfft(spec, n=n, axis=0)


def view(disp: np.ndarray, which: str) -> np.ndarray:
    """(n, 3) -> (n, 2) on principal axes 1-2 (face-on) or 2-3 (edge-on)."""
    if disp.shape[1] == 1:
        return np.column_stack([disp[:, 0], np.zeros(len(disp))])
    _, _, vt = np.linalg.svd(disp - disp.mean(axis=0), full_matrices=False)
    axes = vt[:2] if which == "face" else vt[1:3]
    return disp @ axes.T


def band_rms(xy: np.ndarray, fs: float) -> float:
    """2-D RMS of the 3.5-12 Hz content (sqrt of summed per-axis mean squares)."""
    spec = np.fft.rfft(xy, axis=0)
    f = np.fft.rfftfreq(len(xy), 1.0 / fs)
    keep = (f >= BAND[0]) & (f <= BAND[1])
    ms = 2.0 * (np.abs(spec[keep]) ** 2).sum() / len(xy) ** 2
    return math.sqrt(ms)


# ── data ─────────────────────────────────────────────────────────────────────

def load_carriers(results: Path, source: str = "landmarks") -> list[dict]:
    """Recorded still hands. `source` picks the fingertip landmark traces
    ("landmarks", every tremor run) or the optical-flow traces ("flow", runs
    from tremor_test 0.2 on) -- the same holds seen two ways, which is how
    the two measurements' noise floors are compared."""
    key = "flow_traces" if source == "flow" else "traces"
    out = []
    for fp in sorted(results.glob("*tremor*.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        for ph, block in (d.get("raw", {}).get("phases") or {}).items():
            kind = "rest" if ph in REST_KEYS else "postural"
            move = PHASES[ph].move_max if ph in PHASES else (0.15 if kind == "rest" else 0.60)
            for hand, tr in (block.get(key) or {}).items():
                a = np.asarray(tr, float)
                if len(a) < 40:
                    continue
                out.append({"id": f"{fp.stem[:15]}:{ph}:{hand}", "kind": kind,
                            "move_max": move, "t": a[:, 0], "xy": a[:, 1:3]})
    return out


def load_et(root: Path) -> list[dict]:
    import scipy.io as sio
    acc = sio.loadmat(root / "acc_signal_database.mat", squeeze_me=True,
                      struct_as_record=False)["acc_signal_database"]
    clin = sio.loadmat(root / "clinical_data.mat", squeeze_me=True,
                       struct_as_record=False)["clinical_data"]
    ftm = {}
    for c in clin:
        v = c.FTM_total
        ftm[int(c.subject)] = float(v) if np.size(v) == 1 else None
    recs = []
    for r in acc:
        for cond, kind in (("rest", "rest"), ("posture", "postural")):
            recs.append({"ds": "ET", "person": f"ET{int(r.subject):02d}",
                         "hand": str(r.hand), "group": "ET", "hold": kind,
                         "site": "dorsum", "fs": float(r.Fs),
                         "acc": np.asarray(getattr(r, cond), float),
                         "ftm": ftm.get(int(r.subject))})
    return recs


def load_arm(root: Path) -> list[dict]:
    try:
        from matio import load_from_mat
    except ImportError:
        sys.exit("ARM needs mat-io (pip install mat-io): its tables are MATLAB objects.")
    db = root / "database_v2.mat"
    data = load_from_mat(db if db.exists() else root / "database.mat")["data"].ravel()
    recs = []
    for i, s in enumerate(data):
        s = s.ravel()[0] if hasattr(s, "ravel") else s
        # readme: data{1}-{2} ET, {3}-{10} PD, {11}-{37} no diagnosed tremor
        group = "ET" if i < 2 else "PD" if i < 10 else "none"
        rec = s["recordings"].ravel()[0]
        for cond, kind in (("rest", "rest"), ("postural", "postural")):
            sites = rec[cond].ravel()[0]
            for site in ("metacarpal", "index"):
                # subject 6's rest metacarpal is spelt "Meatcarpal" in the file
                name = next(n for n in sites.dtype.names
                            if n.lower() in (site, "meatcarpal" if site == "metacarpal" else site))
                tbl = sites[name]
                if not hasattr(tbl, "to_numpy"):
                    tbl = tbl.ravel()[0]
                a = np.asarray(tbl.to_numpy(), float)
                recs.append({"ds": "ARM", "person": f"ARM{i + 1:02d}", "hand": "strong",
                             "group": group, "hold": kind, "site": site,
                             "fs": 62.5, "acc": a, "ftm": None})
    return recs


# ── the camera simulation ────────────────────────────────────────────────────

def ref_of(rec: dict) -> dict | None:
    a = rec["acc"]
    if a.ndim == 2 and a.shape[1] > 1:
        c = a - a.mean(axis=0)
        _, _, vt = np.linalg.svd(c, full_matrices=False)
        x = c @ vt[0]
    else:
        x = a.ravel()
    fs = rec["fs"]
    if fs > 1000:                              # ET: 5 kHz, decimate first
        from scipy.signal import decimate
        x = decimate(decimate(x, 10), 2)
        fs = fs / 20
    return ref_spectrum(x, fs)


def through_camera(disp_pct: np.ndarray, carrier: dict, gain: float = 1.0) -> dict:
    """Add a %-of-hand-length tremor (UP_FS grid) to a carrier, run the engine."""
    t = carrier["t"] - carrier["t"][0]
    dur = t[-1] + 1.0 / UP_FS
    n_need = int(math.ceil(dur * UP_FS)) + 2
    if len(disp_pct) < n_need:                 # shorter record: tile it
        reps = int(math.ceil(n_need / len(disp_pct)))
        disp_pct = np.concatenate([disp_pct] * reps)
    start = (len(disp_pct) - n_need) // 2      # the middle, away from edges
    seg = disp_pct[start:start + n_need] * gain
    grid = np.arange(n_need) / UP_FS
    add = np.column_stack([np.interp(t, grid, seg[:, k]) for k in range(2)])
    pts = (carrier["xy"] + add)[:, None, :]
    res = tm.analyse_hand(carrier["t"], pts, np.full(len(t), 100.0),
                          move_max=carrier["move_max"])
    # The fair reference: the same stretch of the same displacement, before
    # the camera's frame times and noise touch it.
    seg_ref = ref_spectrum(seg, UP_FS)
    return {**res, "seg_ref": seg_ref}


def row(rec, ref, carrier, view_name, res, extra=None) -> dict:
    band_hi = res.get("band", [None, None])[1] if res.get("scored") else None
    r = {"ds": rec["ds"], "person": rec["person"], "hand": rec["hand"],
         "group": rec["group"], "hold": rec["hold"], "site": rec["site"],
         "view": view_name, "carrier": carrier["id"], "ftm": rec["ftm"],
         "ref_hz": ref["peak_hz"] if ref else None,
         "ref_prom": ref["prominence"] if ref else None,
         "ref_clear": bool(ref and ref["interior"] and ref["prominence"] >= REF_PROM),
         "seg_hz": (res.get("seg_ref") or {}).get("peak_hz"),
         "seg_prom": (res.get("seg_ref") or {}).get("prominence"),
         "seg_clear": bool(res.get("seg_ref") and res["seg_ref"]["interior"]
                           and res["seg_ref"]["prominence"] >= REF_PROM),
         "scored": res.get("scored"), "why": res.get("why"),
         "fps": res.get("fs"), "band_hi": band_hi,
         "peak_hz": res.get("peak_hz"), "prominence": res.get("prominence"),
         "amp_pct": res.get("amp_pct"), "verdict": res.get("verdict")}
    r.update(extra or {})
    return r


def run(et, arm, carriers, limit=None):
    rows, c0 = [], []
    for c in carriers:
        res = tm.analyse_hand(c["t"], c["xy"][:, None, :], np.full(len(c["t"]), 100.0),
                              move_max=c["move_max"])
        c0.append({"carrier": c["id"], "kind": c["kind"], **{k: res.get(k) for k in
                   ("scored", "why", "fs", "peak_hz", "prominence", "amp_pct", "verdict")}})
    by_kind = {k: [c for c in carriers if c["kind"] == k] for k in ("rest", "postural")}

    glove = []
    for rec in (arm[:limit * 4] if limit else arm):
        ref = ref_of(rec)
        disp = displacement(rec["acc"], rec["fs"]) * 100.0 / PALM_CM * 100.0  # m -> % hand
        for vname in ("face", "edge"):
            xy = view(disp, vname)
            amp_true = band_rms(xy, UP_FS)
            for c in by_kind[rec["hold"]]:
                rows.append(row(rec, ref, c, vname, through_camera(xy, c),
                                {"amp_true_pct": round(amp_true, 3), "level": None}))
        if rec["site"] == "metacarpal":
            a = rec["acc"]
            mag = np.linalg.norm(a, axis=1)
            c = a - a.mean(axis=0)
            _, _, vt = np.linalg.svd(c, full_matrices=False)
            bm, bp = band_power(mag.tolist(), rec["fs"]), band_power((c @ vt[0]).tolist(), rec["fs"])
            glove.append({"person": rec["person"], "group": rec["group"], "hold": rec["hold"],
                          "ref_hz": ref and ref["peak_hz"], "ref_prom": ref and ref["prominence"],
                          "ref_clear": bool(ref and ref["interior"] and ref["prominence"] >= REF_PROM),
         "seg_hz": (res.get("seg_ref") or {}).get("peak_hz"),
         "seg_prom": (res.get("seg_ref") or {}).get("prominence"),
         "seg_clear": bool(res.get("seg_ref") and res["seg_ref"]["interior"]
                           and res["seg_ref"]["prominence"] >= REF_PROM),
                          "mag_hz": bm and round(bm["peak_hz"], 2),
                          "pc1_hz": bp and round(bp["peak_hz"], 2)})

    for rec in (et[:limit * 2] if limit else et):
        ref = ref_of(rec)
        disp = view(displacement(rec["acc"], rec["fs"]), "face")
        base = band_rms(disp, UP_FS)
        if base <= 0:
            continue
        for level in ET_LEVELS:
            xy = disp * (level / base)
            for c in by_kind[rec["hold"]]:
                rows.append(row(rec, ref, c, "single", through_camera(xy, c),
                                {"amp_true_pct": level, "level": level}))
    return rows, c0, glove


# ── the pre-registered summaries ─────────────────────────────────────────────

def _share(rs, pred):
    return round(sum(map(pred, rs)) / len(rs), 3) if rs else None


def _q(vals, q):
    return round(float(np.quantile(vals, q)), 3) if vals else None


def summarise(rows, c0, glove) -> dict:
    out = {"C0_carriers": c0}

    # F1 -- frequency. Reference = the position spectrum of the very stretch
    # the camera saw (seg_*), so the error is the camera's alone. F1_accel
    # keeps the whole-record accelerometer reference: the gap between the two
    # is physics (position = acceleration / f²) plus the tremor's own drift.
    def freq(rs, hz, clear):
        sub = [r for r in rs if r["scored"] and r[clear]]
        out_ = {}
        for part, ss in (("resolvable", [r for r in sub if r[hz] <= r["band_hi"]]),
                         ("above_band_top", [r for r in sub if r[hz] > r["band_hi"]])):
            err = [abs(r["peak_hz"] - r[hz]) for r in ss]
            sgn = [r["peak_hz"] - r[hz] for r in ss]
            out_[part] = {"n": len(ss), "median_abs_hz": _q(err, 0.5),
                          "median_signed_hz": _q(sgn, 0.5), "p90_abs_hz": _q(err, 0.9),
                          "within_0_5": _share(err, lambda e: e <= 0.5),
                          "within_1_0": _share(err, lambda e: e <= 1.0)}
        return out_
    sets = (("ARM_face", [r for r in rows if r["ds"] == "ARM" and r["view"] == "face"]),
            ("ARM_edge", [r for r in rows if r["ds"] == "ARM" and r["view"] == "edge"]),
            *((f"ET_{lv}pct", [r for r in rows if r["ds"] == "ET" and r["level"] == lv])
              for lv in ET_LEVELS))
    out["F1_frequency"] = {k: freq(rs, "seg_hz", "seg_clear") for k, rs in sets}
    out["F1_accel_ref"] = {k: freq(rs, "ref_hz", "ref_clear") for k, rs in sets}

    # D1 -- ARM verdicts by group x hold x view
    d1 = {}
    for g in ("PD", "ET", "none"):
        for h in ("rest", "postural"):
            for v in ("face", "edge"):
                rs = [r for r in rows if r["ds"] == "ARM" and r["site"] == "metacarpal"
                      and r["group"] == g and r["hold"] == h and r["view"] == v]
                sc = [r for r in rs if r["scored"]]
                d1[f"{g}:{h}:{v}"] = {
                    "n": len(rs), "scored": len(sc),
                    "detected": _share(sc, lambda r: r["verdict"] == "detected"),
                    "possible": _share(sc, lambda r: r["verdict"] == "possible"),
                    "none": _share(sc, lambda r: r["verdict"] == "none"),
                    "amp_true_median_pct": _q([r["amp_true_pct"] for r in rs], 0.5),
                    "amp_true_max_pct": _q([r["amp_true_pct"] for r in rs], 1.0)}
    out["D1_arm_detection"] = d1

    # D2 -- ET detection vs imposed amplitude
    d2 = {}
    for h in ("rest", "postural"):
        for ref_clear in (True, False):
            for lv in ET_LEVELS:
                sc = [r for r in rows if r["ds"] == "ET" and r["hold"] == h
                      and r["level"] == lv and r["scored"]
                      and r["seg_clear"] == ref_clear]
                d2[f"{h}:{'clear' if ref_clear else 'unclear'}:{lv}"] = {
                    "n": len(sc),
                    "detected": _share(sc, lambda r: r["verdict"] == "detected"),
                    "any": _share(sc, lambda r: r["verdict"] != "none")}
    out["D2_et_amplitude"] = d2

    # D3 -- threshold sweep, ARM metacarpal face-on, both holds
    arm = [r for r in rows if r["ds"] == "ARM" and r["site"] == "metacarpal"
           and r["view"] == "face" and r["scored"]]
    pos = [r for r in arm if r["group"] in ("PD", "ET")]
    neg = [r for r in arm if r["group"] == "none"]
    sweep = []
    for pm in SWEEP_PROM:
        for am in SWEEP_AMP:
            det = lambda r: r["prominence"] >= pm and r["amp_pct"] >= am
            sweep.append({"prom_min": pm, "amp_floor": am,
                          "sensitivity": _share(pos, det),
                          "specificity": _share(neg, lambda r: not det(r))})
    out["D3_sweep"] = sweep

    # G1 -- glove accelerometer path
    ok = [g for g in glove if g["ref_clear"]
          and g["mag_hz"] is not None and g["pc1_hz"] is not None]
    em = [abs(g["mag_hz"] - g["ref_hz"]) for g in ok]
    ep = [abs(g["pc1_hz"] - g["ref_hz"]) for g in ok]
    out["G1_glove"] = {"n": len(ok),
                       "magnitude": {"median_abs_hz": _q(em, 0.5),
                                     "within_0_5": _share(em, lambda e: e <= 0.5)},
                       "principal_axis": {"median_abs_hz": _q(ep, 0.5),
                                          "within_0_5": _share(ep, lambda e: e <= 0.5)},
                       "rows": glove}

    # Added after the first full run (post hoc, labelled as such in the doc):
    # P1 ARM detection among holds whose own stretch holds a clear interior tremor
    p1 = {}
    for v in ("face", "edge"):
        rs = [r for r in rows if r["ds"] == "ARM" and r["site"] == "metacarpal"
              and r["view"] == v and r["scored"] and r["seg_clear"]]
        p1[v] = {"n": len(rs), "people": len({r["person"] for r in rs}),
                 "detected": _share(rs, lambda r: r["verdict"] == "detected"),
                 "any": _share(rs, lambda r: r["verdict"] != "none"),
                 "amp_true_median_pct": _q([r["amp_true_pct"] for r in rs], 0.5)}
    out["P1_arm_clear_ref"] = p1
    # P2 frequency error where the engine itself named a tremor
    p2 = {}
    for label, rs in (("ARM_face", [r for r in rows if r["ds"] == "ARM" and r["view"] == "face"]),
                      ("ET_all_levels", [r for r in rows if r["ds"] == "ET"])):
        sub = [r for r in rs if r["scored"] and r["seg_clear"] and r["verdict"] != "none"]
        err = [abs(r["peak_hz"] - r["seg_hz"]) for r in sub]
        p2[label] = {"n": len(sub), "median_abs_hz": _q(err, 0.5), "p90_abs_hz": _q(err, 0.9),
                     "within_0_5": _share(err, lambda e: e <= 0.5)}
    out["P2_freq_when_flagged"] = p2
    # P4 which carriers the control flags came from
    ctl = [r for r in rows if r["ds"] == "ARM" and r["group"] == "none" and r["scored"]]
    out["P4_control_flags_by_carrier"] = {
        c: _share([r for r in ctl if r["carrier"] == c], lambda r: r["verdict"] != "none")
        for c in sorted({r["carrier"] for r in ctl})}

    # context: reference prominence by ARM group (does "no tremor" look quiet?)
    ctx = {}
    for g in ("PD", "ET", "none"):
        for h in ("rest", "postural"):
            refs = {(r["person"], r["hold"]): (r["ref_prom"], r["ref_clear"]) for r in rows
                    if r["ds"] == "ARM" and r["site"] == "metacarpal"
                    and r["group"] == g and r["hold"] == h and r["ref_prom"] is not None}
            v = list(refs.values())
            ctx[f"{g}:{h}"] = {"n": len(v), "ref_prom_median": _q([p for p, _ in v], 0.5),
                               "ref_clear": _share(v, lambda pc: pc[1])}
    out["ref_context"] = ctx
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--et", type=Path, default=Path("C:/Datasets/ET-Accel"))
    ap.add_argument("--arm", type=Path, default=Path("C:/Datasets/ArmTremor"))
    ap.add_argument("--results", type=Path, default=_REPO_ROOT / "results")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--carriers", choices=("landmarks", "flow"), default="landmarks",
                    help="noise carriers: the landmark traces or the optical-flow ones")
    a = ap.parse_args()

    carriers = load_carriers(a.results, a.carriers)
    if not carriers:
        sys.exit(f"No tremor sessions with {a.carriers} traces in results/: record one first"
                 + (" with tremor_test 0.2 or later." if a.carriers == "flow" else "."))
    print(f"Carriers: {len(carriers)} "
          f"({sum(c['kind'] == 'rest' for c in carriers)} rest, "
          f"{sum(c['kind'] == 'postural' for c in carriers)} postural)")
    et, arm = load_et(a.et), load_arm(a.arm)
    print(f"ET records: {len(et)}   ARM records: {len(arm)}")
    rows, c0, glove = run(et, arm, carriers, a.limit)
    summary = summarise(rows, c0, glove)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(OUT_DIR / f"accel_{stamp}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (OUT_DIR / f"accel_{stamp}.json").write_text(
        json.dumps({"carriers": a.carriers, "engine": {"PROM_MIN": tm.PROM_MIN, "PROM_POSSIBLE": tm.PROM_POSSIBLE,
                               "AMP_FLOOR_PCT": tm.AMP_FLOOR_PCT},
                    "n_rows": len(rows), **summary}, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("D3_sweep", "G1_glove")}, indent=1))
    print("G1", json.dumps({k: v for k, v in summary["G1_glove"].items() if k != "rows"}))
    print(f"Wrote {OUT_DIR / f'accel_{stamp}.json'}")


if __name__ == "__main__":
    main()
