"""
Tremor metrics (pure) — is there a rhythmic 3.5-12 Hz oscillation in a hand
that is meant to be still, how fast is it, and roughly how big.
No camera, no UI; unit-tested on synthetic hands in
screening_tests/tests/test_tremor.py. Plan: docs/tests/TREMOR_TEST_PLAN.md.

What is trusted, and what is not (plan §1):
  peak_hz        TRUSTED. MediaPipe tremor frequency agrees with accelerometers
                 to within ~0.2 Hz (Sci Rep 2025; Williams 2021: <0.5 Hz in
                 97% of phone videos).
  amp_pct        An ESTIMATE. The same studies found video amplitude not yet
                 clinical-grade, and a 2-D camera cannot see motion toward it.
                 Reported in % of the hand's own length (wrist → middle-finger
                 knuckle), which is scale-invariant the way tapping's
                 normaliser is; ``amp_pp_cm_est`` converts it with an assumed
                 palm length only so it can be read against MDS-UPDRS 3.17's
                 centimetre classes.

Why not reuse core/spiral/metrics.compute_tremor: it reports tremor power as a
*fraction* of total movement power, which means something for a hand that is
tracing a spiral and nothing for a hand that is meant to be still — there the
denominator is tracker noise and the fraction is large for everybody. A still
hand needs an absolute amplitude and a peak that stands out from its own band.

Signal: the RAW landmarks (never the One-Euro ones, which would erase the
tremor), in pixels, for the wrist and three fingertips. The tool records only
frames core/framing.py trusts, so a hand at the edge of the picture — whose
guessed landmarks jitter — never reaches this module.

Method: split at gaps → resample each stretch to a uniform grid → Welch
average of 4 s Hann windows (50% overlap, linear detrend each) → drop windows
where the hand was voluntarily moved → one spectrum per hand per phase.
"""

from __future__ import annotations

import math

import numpy as np

from core.tremor import confidence as conf
from core.tremor.phases import REST_PHASES

# ── Analysis constants ──────────────────────────────────────────────────────
#: Tremor band, Hz. The same band as core/glove/imu.TREMOR_BAND and the
#: spiral's, so a camera and a glove tremor figure mean the same thing.
#: Stamped on every session. 1: live landmarks / live optical flow at the
#: loop's rate. 2: the offline pass over every recorded frame
#: (core/tremor/offline.py, docs/tests/TREMOR_RESTRUCTURE_PLAN.md) -- a 60 fps
#: flow reading and a 16 fps landmark reading of one hand are different
#: instruments, so the report says which one it is showing.
ENGINE_VERSION = 2

TREMOR_BAND = (3.5, 12.0)
#: Below this camera rate the band's usable top falls under 7 Hz and no longer
#: covers parkinsonian rest tremor (4-6 Hz) with any margin. Field sessions run
#: ~16 fps (docs/performance/FPS_FINDINGS.md), so this bites only on a loaded CPU.
FS_MIN = 14.0
MIN_BAND_WIDTH_HZ = 2.0
WIN_S = 4.0                 # Welch window: 0.25 Hz resolution, 14 cycles at 3.5 Hz
MIN_WINDOWS = 2             # below this a peak is one window's noise
GAP_MIN_S = 0.2             # a hole this long splits the recording
#: A window whose slow (<1 Hz) position moves more than this, in hand lengths,
#: was a voluntary repositioning, not a hand at rest. This is the default for
#: a supported hand; each phase sets its own (core/tremor/phases.py), because
#: arms held out sway by 15-40% of a hand length as a matter of course — the
#: first live run lost every arms-out window to this gate at 0.15. Sway that
#: slow cannot leak into 3.5 Hz: it sits 12+ Hann bins below the band.
MOVE_MAX = 0.15
PEAK_HALF_WIDTH_HZ = 1.0    # tremor amplitude = power within ±this of the peak
PALM_LEN_CM = 10.0          # assumed wrist → middle-knuckle length, cm

# ── Detection thresholds (PROVISIONAL) ──────────────────────────────────────
# Bracketed from synthetic tracker noise; to be retuned on real still-hand
# recordings the way tapping's ADAPT_MIN_RANGE_FRAC was measured
# (TREMOR_TEST_PLAN.md §4). Two gates, because each alone fails: small hands
# make tracker noise large (amplitude alone flags everyone), and a tiny but
# clean peak is physiological tremor nobody needs to hear about (prominence
# alone flags healthy people in the arms-out phase).
PROM_MIN = 6.0              # peak / band median for "detected"
PROM_POSSIBLE = 3.5         # below this there is no peak worth naming
AMP_FLOOR_PCT = 1.5         # RMS, % of hand length, for "detected"

#: Landmarks read: wrist, thumb tip, index tip, middle tip. The wrist carries
#: the forearm's rotation, the tips carry pill-rolling.
LANDMARKS = (0, 4, 8, 12)
HAND_LEN_FROM, HAND_LEN_TO = 0, 9

DETECTED, POSSIBLE, NONE = "detected", "possible", "none"


def hand_length(points) -> float | None:
    """Wrist → middle-finger knuckle, in the units of `points` (pixels)."""
    if points is None or len(points) <= HAND_LEN_TO:
        return None
    (x0, y0), (x1, y1) = points[HAND_LEN_FROM][:2], points[HAND_LEN_TO][:2]
    d = math.hypot(x1 - x0, y1 - y0)
    return d if d > 0 else None


def select(points) -> list[tuple[float, float]]:
    """The landmarks this module reads, as (x, y), from a 21-point hand."""
    return [(float(points[i][0]), float(points[i][1])) for i in LANDMARKS]


# ── bands ────────────────────────────────────────────────────────────────────

def classify(prominence: float, amp_pct: float) -> str:
    if prominence < PROM_POSSIBLE or amp_pct < AMP_FLOOR_PCT / 2:
        return NONE
    if prominence >= PROM_MIN and amp_pct >= AMP_FLOOR_PCT:
        return DETECTED
    return POSSIBLE


def band(verdict: str) -> tuple[str, str]:
    """(status token, plain-language label) for one hand in one phase, or for
    the whole run (its worst cell). No severity grade: amplitude is an estimate."""
    if verdict == DETECTED:
        return "danger", "Tremor detected - consider follow-up"
    if verdict == POSSIBLE:
        return "warning", "Possible tremor - repeat to confirm"
    return "success", "No tremor detected"


# ── one hand, one phase ──────────────────────────────────────────────────────

#: With exact frame times (offline, device-stamped), up to this many lost
#: frames in a row are filled by linear interpolation; a longer hole splits
#: the recording. Filling one sample at 60 fps is a negligible low-pass below
#: 12 Hz -- unlike resampling a 16 fps stream, which under-read a 5 Hz tremor
#: by a quarter and was rejected (analyse_hand). Left alone, one lost frame
#: shifts every later sample of its window one period early: 30 deg at 5 Hz.
FILL_MAX = 2


def fill_drops(ts: np.ndarray, arr: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Insert linearly interpolated samples where 1..FILL_MAX frames are
    missing. Returns (ts, arr, frames_filled). `arr` is (n, C)."""
    if len(ts) < 3:
        return ts, arr, 0
    dt = np.diff(ts)
    period = float(np.median(dt))
    if period <= 0:
        return ts, arr, 0
    k = np.rint(dt / period).astype(int) - 1          # lost frames per interval
    holes = np.nonzero((dt > 1.5 * period) & (k >= 1) & (k <= FILL_MAX))[0]
    if not len(holes):
        return ts, arr, 0
    t_out, a_out, prev, filled = [], [], 0, 0
    for i in holes:
        t_out.append(ts[prev:i + 1])
        a_out.append(arr[prev:i + 1])
        n = int(k[i])
        f = np.arange(1, n + 1, dtype=np.float64) / (n + 1)
        t_out.append(ts[i] + f * (ts[i + 1] - ts[i]))
        a_out.append(arr[i] + np.outer(f, arr[i + 1] - arr[i]))
        prev, filled = i + 1, filled + n
    t_out.append(ts[prev:])
    a_out.append(arr[prev:])
    return np.concatenate(t_out), np.concatenate(a_out), filled


def _segments(ts: np.ndarray, gap: float | None = None) -> list[tuple[int, int]]:
    """[start, end) index ranges with no hole longer than the gap threshold."""
    if len(ts) < 2:
        return []
    dt = np.diff(ts)
    if gap is None:
        gap = max(GAP_MIN_S, 3.0 * float(np.median(dt)))
    cuts = np.nonzero(dt > gap)[0]
    out, start = [], 0
    for c in cuts:
        out.append((start, int(c) + 1))
        start = int(c) + 1
    out.append((start, len(ts)))
    return out


def _slow_range(x: np.ndarray, fs: float) -> float:
    """Peak-to-peak of the <1 Hz component — voluntary drift, not tremor. A
    1 s boxcar has nulls at every whole Hz and passes ~9% at 3.5 Hz, so even a
    large tremor barely reaches it."""
    k = max(1, int(round(fs)))
    if len(x) <= k:
        return float(np.ptp(x))
    slow = np.convolve(x, np.ones(k) / k, mode="valid")
    return float(np.ptp(slow))


def analyse_hand(ts, pts, lens, move_max: float = MOVE_MAX,
                 exact_times: bool = False) -> dict:
    """Spectrum of one hand over one phase.

    ts   : frame times, s (trusted frames only, settle already removed)
    pts  : per frame, the LANDMARKS as (x, y) pixels (see `select`)
    lens : per frame, hand_length in the same pixels
    move_max : the voluntary-movement gate for this hold, in hand lengths
    exact_times : the frame times are capture times from a camera that
           delivers every frame (the offline pass, core/tremor/offline.py):
           lost frames are then filled (fill_drops) and anything longer
           splits. Off for the live loop, whose intervals vary all the time
           with the CPU and would read as losses everywhere.

    Always returns a dict. ``scored`` False carries ``why`` — a code, not a
    sentence; compute_metrics turns codes into the one reason a person reads.
    """
    ts = np.asarray(ts, dtype=np.float64)
    if len(ts) < 8:
        return {"scored": False, "why": "no_data"}
    order = np.argsort(ts)
    ts = ts[order]
    arr = np.asarray(pts, dtype=np.float64)[order]          # (n, K, 2)
    lens = np.asarray(lens, dtype=np.float64)[order]
    good = np.isfinite(lens) & (lens > 0)
    if good.sum() < 8:
        return {"scored": False, "why": "no_data"}
    # One constant scale per phase. Dividing frame by frame would multiply
    # the hand-length estimate's own jitter into the signal.
    scale = float(np.median(lens[good]))
    n_ch = arr.shape[1] * 2
    arr = arr.reshape(len(ts), n_ch) / scale                 # hand lengths

    filled = 0
    if exact_times:
        ts, arr, filled = fill_drops(ts, arr)
        period = float(np.median(np.diff(ts))) if len(ts) > 2 else 0.0
        segs = _segments(ts, gap=(FILL_MAX + 1.5) * period if period > 0 else None)
    else:
        segs = _segments(ts)
    # Mean frame rate, not 1/median(dt): a CPU-bound camera drops frames
    # unevenly, and the median interval then overstates the rate — which
    # would move the peak frequency, the one number this test trusts.
    rates = [(b - a - 1) / (ts[b - 1] - ts[a]) for a, b in segs
             if b - a > 1 and ts[b - 1] > ts[a]]
    if not rates:
        return {"scored": False, "why": "no_data"}
    fs = float(np.median(rates))
    nyq = fs / 2.0
    lo, hi = TREMOR_BAND[0], min(TREMOR_BAND[1], 0.95 * nyq)
    if fs < FS_MIN or hi - lo < MIN_BAND_WIDTH_HZ:
        return {"scored": False, "why": "low_fps", "fs": round(fs, 1)}

    n = int(round(WIN_S * fs))
    step = max(1, n // 2)
    nfft = 1 << int(math.ceil(math.log2(4 * n)))             # finer peak grid
    w = np.hanning(n)
    w_ss = float((w * w).sum())
    freqs = np.fft.rfftfreq(nfft, d=1.0 / fs)                # common grid
    density = np.zeros_like(freqs)                           # ms per Hz
    used = rejected = 0
    valid_s = 0.0
    idx = np.arange(n, dtype=np.float64)

    # Samples are taken as evenly spaced *within each window*, at that
    # window's own measured rate. Interpolating onto a uniform grid instead
    # was tried and under-read a 5 Hz tremor by a quarter at 16 fps: linear
    # interpolation is a low-pass filter exactly where the band sits. Each
    # window's spectrum is then mapped onto one common frequency grid.
    for a, b in segs:
        if ts[b - 1] - ts[a] < WIN_S * 0.95:
            continue
        valid_s += ts[b - 1] - ts[a]
        for s in range(a, b - n + 1, step):
            span = ts[s + n - 1] - ts[s]
            if span <= 0:
                continue
            fs_w = (n - 1) / span
            win = arr[s:s + n].T                              # (C, n)
            if max(_slow_range(ch, fs_w) for ch in win) > move_max:
                rejected += 1
                continue
            coef = np.polyfit(idx, win.T, 1)                  # linear detrend
            detr = win - (np.outer(coef[0], idx) + coef[1][:, None])
            spec = np.fft.rfft(detr * w, n=nfft, axis=1)
            # one-sided power → mean square per bin (Parseval with the
            # window's energy), then per Hz so windows at different rates add
            ms_w = 2.0 * (np.abs(spec) ** 2).sum(axis=0) / (nfft * w_ss)
            f_w = np.fft.rfftfreq(nfft, d=1.0 / fs_w)
            density += np.interp(freqs, f_w, ms_w / (fs_w / nfft),
                                 right=0.0)
            used += 1

    base = {"fs": round(fs, 1), "windows": used, "rejected_windows": rejected,
            "valid_s": round(valid_s, 1)}
    if exact_times:
        base["filled"] = filled
    if used < MIN_WINDOWS:
        why = "moving" if rejected and rejected >= used else "too_short"
        return {"scored": False, "why": why, **base}

    density /= used
    psd = density
    # Mean square per common bin, averaged over the K landmarks: x and y
    # together make a 2-D RMS displacement.
    k_lm = n_ch / 2
    ms = density * (fs / nfft) / k_lm

    in_band = (freqs >= lo) & (freqs <= hi)
    band_p = psd[in_band]
    band_f = freqs[in_band]
    pk = int(np.argmax(band_p))
    peak_hz = float(band_f[pk])
    median_p = float(np.median(band_p))
    prominence = float(band_p[pk] / median_p) if median_p > 0 else 0.0
    near = in_band & (np.abs(freqs - peak_hz) <= PEAK_HALF_WIDTH_HZ)
    # Zero padding repeats each true bin ~nfft/n times; the Parseval scaling
    # above already accounts for it, so these sums are real mean squares.
    amp = math.sqrt(float(ms[near].sum()))
    band_amp = math.sqrt(float(ms[in_band].sum()))
    verdict = classify(prominence, amp * 100.0)
    status, label = band(verdict)

    # A light copy of the spectrum for the report: 0.25 Hz steps from 1 Hz,
    # as RMS-amplitude density so its units match amp_pct.
    report_f = np.arange(1.0, hi + 1e-9, 0.25)
    dens = np.interp(report_f, freqs, ms) * (nfft / n)        # per true bin
    spectrum = [[round(float(f), 2), round(math.sqrt(max(0.0, float(v))) * 100, 3)]
                for f, v in zip(report_f, dens)]

    return {
        "scored": True, **base,
        "peak_hz": round(peak_hz, 2),
        "amp_pct": round(amp * 100.0, 2),
        "amp_pp_cm_est": round(2 * math.sqrt(2) * amp * PALM_LEN_CM, 2),
        "band_amp_pct": round(band_amp * 100.0, 2),
        "prominence": round(prominence, 2),
        "band": [lo, round(hi, 2)],
        "verdict": verdict, "status": status, "label": label,
        "spectrum": spectrum,
    }


# ── glove IMU, one phase ─────────────────────────────────────────────────────

def analyse_glove(series: dict | None) -> dict | None:
    """Tremor band of the glove IMU over one phase (core/glove/imu.band_power).

    The gyro is the primary channel: rest tremor is largely rotation
    (pronation-supination, pill-rolling), which the gyro sees directly and
    the accelerometer only through the small linear motion it causes.

    **The gyro is read along its principal axis, not as a magnitude.** A
    tremor is a rotation back and forth about roughly one axis, so its
    angular rate swings through zero; |ω| rectifies that and puts the peak at
    *twice* the tremor frequency. The first principal component keeps the
    sign and, like a magnitude, does not care how the board is mounted. The
    accelerometer keeps ||a||, which gravity holds far from zero, so it does
    not rectify — and it matches the Developer page's Motion card.
    """
    if not series or not series.get("accel") or series.get("fs", 0) <= 0:
        return None
    from core.glove.imu import band_power, magnitude
    fs = float(series["fs"])
    a_mag = [magnitude(*v) for v in series["accel"]]
    acc = band_power(a_mag, fs)
    gyr = band_power(_principal_axis(series["gyro"]), fs)
    if acc is None and gyr is None:
        return None

    def pick(d):
        return None if d is None else {"peak_hz": round(d["peak_hz"], 2),
                                       "band_frac": round(d["band_frac"], 3),
                                       "rms": round(d["rms"] or 0.0, 4)}
    return {"fs": round(fs, 1), "n": len(a_mag), "accel": pick(acc),
            "gyro": pick(gyr)}


def _principal_axis(vectors) -> list[float]:
    """3-axis samples projected on their direction of greatest variance."""
    v = np.asarray(vectors, dtype=np.float64)
    if v.ndim != 2 or len(v) < 4:
        return []
    v = v - v.mean(axis=0)
    _, _, vt = np.linalg.svd(v, full_matrices=False)
    return (v @ vt[0]).tolist()


def glove_peak_hz(g: dict | None) -> float | None:
    if not g:
        return None
    src = g.get("gyro") or g.get("accel")
    return src["peak_hz"] if src else None


# ── the whole run ────────────────────────────────────────────────────────────

_RANK = {NONE: 0, POSSIBLE: 1, DETECTED: 2}


def compute_metrics(cells: dict, *, phase_order, hands=("left", "right"),
                    glove: dict | None = None, clipped_pct: float = 0.0,
                    glove_hand: str | None = None) -> dict:
    """Score a run from the per-cell analyses.

    cells : {phase: {hand: analyse_hand(...) result}}
    glove : {phase: analyse_glove(...) result} or None when no glove was worn
    glove_hand : "left"/"right" when the person said which hand wears it; the
            glove is then compared with THAT hand's rest reading. None keeps
            the old rule (the camera's strongest rest cell), which compares
            the wrong hand whenever the tremor is in the other one.

    Always returns a dict; ``scoreable`` False with a human-readable
    ``reason`` when no honest reading can be formed.
    """
    out = {
        "scoreable": False, "reason": None, "status": None, "label": None,
        "tremor_amp_pct": None, "tremor_peak_hz": None, "tremor_where": None,
        "rest_amp_left_pct": None, "rest_amp_right_pct": None,
        "rest_peak_hz": None, "palm_up_amp_pct": None,
        "palm_down_amp_pct": None, "postural_amp_pct": None,
        "postural_peak_hz": None, "asymmetry_ratio": None,
        "scored_cells": 0, "detected_cells": 0,
        "possible_cells": 0, "sample_fps": None, "band_hi_hz": None,
        "glove_rest_peak_hz": None, "cam_glove_hz_diff": None,
        "glove_hand": glove_hand if glove else None,
        "confidence_pct": None, "confidence_level": None,
        "confidence_reasons": [], "cells": cells, "glove": glove,
    }

    scored = [(p, h, c) for p in phase_order for h in hands
              if (c := (cells.get(p) or {}).get(h)) and c.get("scored")]
    unscored = [c for p in phase_order for h in hands
                if (c := (cells.get(p) or {}).get(h)) and not c.get("scored")]
    fs_seen = [c["fs"] for c in list(cells_iter(cells)) if c.get("fs")]
    out["sample_fps"] = round(float(np.median(fs_seen)), 1) if fs_seen else None

    if not scored:
        whys = {c.get("why") for c in unscored}
        if "low_fps" in whys:
            out["reason"] = ("The camera frame rate was too low to see tremor - "
                             "close other programs and try again.")
        elif "moving" in whys:
            out["reason"] = ("The hands kept moving, so there was no still "
                             "stretch to measure - let them rest and try again.")
        elif whys & {"too_short"}:
            out["reason"] = ("Neither hand stayed in view long enough to "
                             "measure - keep both hands inside the picture.")
        else:
            out["reason"] = ("No hands were detected - check the camera can "
                             "see both hands, then try again.")
        return out

    out["scoreable"] = True
    out["scored_cells"] = len(scored)
    out["band_hi_hz"] = max(c["band"][1] for _, _, c in scored)
    out["detected_cells"] = sum(c["verdict"] == DETECTED for _, _, c in scored)
    out["possible_cells"] = sum(c["verdict"] == POSSIBLE for _, _, c in scored)

    # Headline: the largest amplitude at the tremor peak, wherever it was.
    # Worst verdict first, so a detected tremor is never out-ranked by a
    # bigger but peakless noise reading.
    p, h, top = max(scored, key=lambda s: (_RANK[s[2]["verdict"]],
                                           s[2]["amp_pct"]))
    out["tremor_amp_pct"] = top["amp_pct"]
    # A peak frequency is only a finding when there is a peak. In a clean
    # hold the tallest bin is tracker noise, and its frequency is random —
    # saving it would chart a meaningless number beside every healthy run.
    out["tremor_peak_hz"] = _peak(top)
    out["tremor_where"] = f"{p}:{h}"
    worst = max((c["verdict"] for _, _, c in scored), key=_RANK.get)
    out["status"], out["label"] = band(worst)

    def cell(phase, hand):
        c = (cells.get(phase) or {}).get(hand)
        return c if c and c.get("scored") else None

    def best(phase):
        cs = [c for h in hands if (c := cell(phase, h))]
        return max(cs, key=lambda c: c["amp_pct"]) if cs else None

    # Rest tremor per hand is the stronger of its two lap holds (palm up,
    # palm down): a tremor that shows on either side of the hand is a rest
    # tremor, and ranking by verdict first keeps a real peak from losing to
    # a larger but peakless reading in the other hold.
    rest_keys = [k for k in REST_PHASES if k in phase_order]

    def rest_of(hand):
        cs = [(k, c) for k in rest_keys if (c := cell(k, hand))]
        return max(cs, key=lambda kc: (_RANK[kc[1]["verdict"]],
                                       kc[1]["amp_pct"])) if cs else (None, None)

    (_, rl), (_, rr) = rest_of("left"), rest_of("right")
    out["rest_amp_left_pct"] = rl["amp_pct"] if rl else None
    out["rest_amp_right_pct"] = rr["amp_pct"] if rr else None
    if rl and rr and min(rl["amp_pct"], rr["amp_pct"]) > 0:
        out["asymmetry_ratio"] = round(max(rl["amp_pct"], rr["amp_pct"])
                                       / min(rl["amp_pct"], rr["amp_pct"]), 2)
    rest_cells = [kc for h in hands if (kc := rest_of(h))[1]]
    rest_key, rest = (max(rest_cells, key=lambda kc: (_RANK[kc[1]["verdict"]],
                                                      kc[1]["amp_pct"]))
                      if rest_cells else (None, None))
    if rest:
        out["rest_peak_hz"] = _peak(rest)
    for key, field in (("rest_palm_up", "palm_up_amp_pct"),
                       ("rest_palm_down", "palm_down_amp_pct")):
        b = best(key)
        out[field] = b["amp_pct"] if b else None
    post = best("postural")
    if post:
        out["postural_amp_pct"] = post["amp_pct"]
        out["postural_peak_hz"] = _peak(post)

    if glove:
        # Compared over the same hold the camera's figure came from, so both
        # read the same seconds of movement -- and, when we know which hand
        # wears the glove, from that hand's own rest cell.
        if glove_hand in hands:
            g_key, g_cell = rest_of(glove_hand)
            cam_hz = _peak(g_cell) if g_cell else None
        else:
            g_key, cam_hz = rest_key, out["rest_peak_hz"]
        g_rest = glove_peak_hz(glove.get(g_key or (rest_keys[0] if rest_keys else "")))
        out["glove_rest_peak_hz"] = g_rest
        if g_rest is not None and cam_hz is not None:
            out["cam_glove_hz_diff"] = round(abs(cam_hz - g_rest), 2)

    q = conf.confidence(
        expected_cells=len(phase_order) * len(hands),
        scored=[c for _, _, c in scored], clipped_pct=clipped_pct)
    out["confidence_pct"] = round(q["confidence_pct"], 1)
    out["confidence_level"] = q["confidence_level"]
    out["confidence_reasons"] = q["reasons"]
    return out


def _peak(cell: dict) -> float | None:
    return cell["peak_hz"] if cell["verdict"] != NONE else None


def cells_iter(cells: dict):
    for per_hand in cells.values():
        for c in (per_hand or {}).values():
            if c:
                yield c
