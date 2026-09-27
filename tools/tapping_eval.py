"""
Pure scoring for the offline tapping evaluation: motion-capture ground truth,
clock alignment, tap matching and agreement statistics. No OpenCV or
MediaPipe here, so it is unit-testable (screening_tests/tests/test_tapping_eval.py);
the video side lives in tools/eval_tapping_videos.py.

Built for EHWGesture (github.com/smilies-polito/EHWGesture): 25 healthy
adults tapping thumb to index against a metronome at 75 / 115 / 140 bpm,
filmed by a 30 fps Kinect while a 120 fps OptiTrack system tracks markers on
the thumb and index tips. The markers are the reference; the question is
whether our detector finds the same taps from the RGB video alone.

Ground truth mirrors the dataset authors' own FT extraction
(ScriptsMOCAP/TrackingData.py): 3-D thumb-index distance, a 4-sample moving
average, and one tap per distance minimum below the trace mean, at least half
a metronome period apart. Their scipy call is reimplemented with the same
semantics because the venv does not carry scipy.

The two clocks are not synchronised -- the dataset ships its own lag
estimates, but in a format this code does not depend on. The offset is found
from the data instead: the one that best correlates our 2-D distance trace
with the 3-D marker trace, the same cross-correlation the authors used
(temporal_reallignment.py) but over the whole recording rather than the first
two seconds. Rate and CV% do not need the offset at all -- both are computed
from intervals, which no clock shift changes -- so only the per-tap timing
figures depend on it.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

MOCAP_FPS = 120.0
# Metronome rate per EHWGesture speed class (groundtruth_for_triggering.py).
SPEED_BPM = {"S": 75.0, "N": 115.0, "F": 140.0}
THUMB = "Hand:Thumb"
INDEX = "Hand:Index"

TASK_RE = re.compile(r"FT([SNF])([12])", re.IGNORECASE)


def parse_task(name: str) -> tuple[str, int] | None:
    """'master_FTN2.mp4' / 'FTN2.csv' -> ('N', 2)."""
    m = TASK_RE.search(name)
    return (m.group(1).upper(), int(m.group(2))) if m else None


# ── motion capture ─────────────────────────────────────────────────────────

def _num(s: str) -> float | None:
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def read_mocap(path: str | Path) -> tuple[list[float], list[tuple | None],
                                          list[tuple | None]]:
    """Read an OptiTrack Motive CSV export.

    Returns (time_s, thumb_xyz, index_xyz); a marker is None on frames where
    it was occluded (Motive leaves those cells blank). Rather than trusting a
    fixed header-row count, the marker-name row is the one that carries
    `Hand:Thumb`, and data rows are the ones whose first two cells are a frame
    number and a time -- so a blank line in the header cannot shift anything.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    col = {}
    for row in rows:
        cells = [c.strip() for c in row]
        if THUMB in cells and INDEX in cells:
            col = {THUMB: cells.index(THUMB), INDEX: cells.index(INDEX)}
            break
    if not col:
        raise ValueError(f"{path}: no {THUMB}/{INDEX} columns in the header")
    times, thumb, index = [], [], []
    for row in rows:
        if len(row) < 2:
            continue
        fr, t = _num(row[0]), _num(row[1])
        if fr is None or t is None:
            continue
        pts = []
        for name in (THUMB, INDEX):
            c = col[name]
            xyz = [_num(v) for v in row[c:c + 3]]
            pts.append(tuple(xyz) if len(xyz) == 3 and None not in xyz else None)
        times.append(t)
        thumb.append(pts[0])
        index.append(pts[1])
    if not times:
        raise ValueError(f"{path}: no data rows")
    return times, thumb, index


def marker_distance(thumb, index) -> list[float | None]:
    return [math.dist(a, b) if a is not None and b is not None else None
            for a, b in zip(thumb, index)]


def fill_gaps(vals: list[float | None]) -> list[float]:
    """Linear interpolation over occluded samples; edges hold the nearest value."""
    known = [i for i, v in enumerate(vals) if v is not None]
    if not known:
        raise ValueError("marker trace has no valid samples")
    out = [0.0] * len(vals)
    for i in range(len(vals)):
        if vals[i] is not None:
            out[i] = vals[i]
    for a, b in zip(known, known[1:]):
        for i in range(a + 1, b):
            w = (i - a) / (b - a)
            out[i] = vals[a] * (1 - w) + vals[b] * w
    for i in range(known[0]):
        out[i] = vals[known[0]]
    for i in range(known[-1] + 1, len(vals)):
        out[i] = vals[known[-1]]
    return out


def moving_average(vals: list[float], n: int = 4) -> list[float]:
    """Same as numpy.convolve(v, ones(n)/n, mode='same'), zero-padded edges."""
    # 'same' keeps the full convolution from index (n-1)//2, so output i sums
    # the n samples ending at i + (n-1)//2.
    out = []
    hi_off = (n - 1) // 2
    for i in range(len(vals)):
        lo, hi = max(0, i + hi_off - n + 1), min(len(vals) - 1, i + hi_off)
        out.append(sum(vals[lo:hi + 1]) / n)
    return out


def local_minima(sig: list[float], min_sep: int, below: float) -> list[int]:
    """Indices of local minima under `below`, at least `min_sep` samples apart.

    scipy.signal.find_peaks semantics for -sig with height=-below and
    distance=min_sep: plateaus resolve to their middle sample, and when two
    minima are too close the deeper one wins.
    """
    cand = []
    i, n = 1, len(sig)
    while i < n - 1:
        if sig[i] < sig[i - 1]:
            j = i
            while j + 1 < n and sig[j + 1] == sig[i]:
                j += 1
            if j + 1 < n and sig[j + 1] > sig[i]:
                mid = (i + j) // 2
                if sig[mid] <= below:
                    cand.append(mid)
            i = j + 1
        else:
            i += 1
    keep = []
    taken = [False] * len(cand)
    for k in sorted(range(len(cand)), key=lambda k: sig[cand[k]]):
        if taken[k]:
            continue
        keep.append(cand[k])
        for m in range(len(cand)):
            if abs(cand[m] - cand[k]) < min_sep:
                taken[m] = True
    return sorted(keep)


CONTACT_FRAC = 0.2   # onset = first sample within 20% of the dip above its floor
PROMINENCE_FRAC = 0.3  # a cycle's dip must be this deep, as a share of p5-p95


def dip_prominence(sig: list[float], m: int) -> float:
    """How far the signal must climb out of the dip at `m` before it reaches
    a lower point, on the shallower side (scipy's prominence, for a minimum).
    Noise wiggles on a flat floor score near zero; a real closure scores the
    whole open-close excursion. A side that runs into the end of the
    recording is not held against the dip -- the last closure of a take is
    still a closure -- unless both sides do."""
    def climb(ks):
        top = sig[m]
        for k in ks:
            if sig[k] < sig[m]:
                return top, False
            top = max(top, sig[k])
        return top, True

    left, l_edge = climb(range(m - 1, -1, -1))
    right, r_edge = climb(range(m + 1, len(sig)))
    if l_edge and not r_edge:
        return right - sig[m]
    if r_edge and not l_edge:
        return left - sig[m]
    return (max if l_edge else min)(left, right) - sig[m]


def mocap_taps(times: list[float], dist: list[float], bpm: float,
               fps: float = MOCAP_FPS, method: str = "onset") -> list[float]:
    """Reference tap times (s, mocap clock) from the marker distance trace.

    Cycles are found as the dataset authors do -- one distance minimum per
    cycle, half a metronome period apart -- plus a prominence test the
    authors lack: each dip must climb PROMINENCE_FRAC of the trace's range on
    both sides. Without it, sensor noise on a long finger rest put a second
    "minimum" more than half a period after the first and one touch counted
    twice (X06 Left S2: 31 reference taps for 26 closures). Where in the
    cycle the tap is stamped:

      "min"    the minimum itself -- the authors' definition. When the fingers
               rest together the markers sit on a flat floor for ~200 ms and
               the minimum lands anywhere on it, which alone put 20-28% CV%
               on healthy metronome tapping (X06 Left).
      "onset"  the moment the closing distance first comes within
               CONTACT_FRAC of that floor -- when contact is made. Stable on
               a flat floor, and the clinical meaning of a tap.
    """
    sig = moving_average(dist, 4)
    cadence = int(round(fps / (bpm / 60.0)))
    mean = sum(sig) / len(sig)
    s = sorted(sig)
    span = s[min(len(s) - 1, int(len(s) * 0.95))] - s[int(len(s) * 0.05)]
    mins = [m for m in local_minima(sig, max(1, cadence // 2), mean)
            if dip_prominence(sig, m) >= PROMINENCE_FRAC * span]
    if method == "min":
        return [times[i] for i in mins]
    out = []
    for m in mins:
        a = max(0, m - cadence)
        p = max(range(a, m + 1), key=lambda k: sig[k])        # preceding peak
        floor = sig[m]
        thr = floor + CONTACT_FRAC * (sig[p] - floor)
        k = next((k for k in range(p, m + 1) if sig[k] <= thr), m)
        if k > p and sig[k - 1] != sig[k]:                     # sub-sample
            w = (sig[k - 1] - thr) / (sig[k - 1] - sig[k])
            out.append(times[k - 1] + w * (times[k] - times[k - 1]))
        else:
            out.append(times[k])
    return out


# ── clock alignment ────────────────────────────────────────────────────────

def read_lag(path: str | Path, task: str) -> int | None:
    """The authors' Kinect->mocap lag for one take, in 120 fps frames, from
    DataKinects/<X>/<side>/<X>_<L|R>_lags.csv (columns: index, Task, Lag).
    Their realignment drops the first `lag` marker samples to line the two
    up, so the marker time at that index is where the video starts."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 3 and row[1].strip().upper() == task.upper():
                    v = _num(row[2])
                    return None if v is None else int(v)
    except OSError:
        return None
    return None


def _interp(ts: list[float], vs: list[float], t: float) -> float | None:
    """Linear interpolation on a sorted, evenly-ish sampled series."""
    if t < ts[0] or t > ts[-1]:
        return None
    lo, hi = 0, len(ts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ts[mid] <= t:
            lo = mid
        else:
            hi = mid
    if ts[hi] == ts[lo]:
        return vs[lo]
    w = (t - ts[lo]) / (ts[hi] - ts[lo])
    return vs[lo] * (1 - w) + vs[hi] * w


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    if saa <= 0 or sbb <= 0:
        return None
    return sab / math.sqrt(saa * sbb)


def estimate_offset(video: list[tuple[float, float]],
                    ref_t: list[float], ref_d: list[float],
                    lo_s: float = -1.0, hi_s: float = 3.0,
                    step_s: float = 1.0 / MOCAP_FPS,
                    min_overlap: float = 0.6) -> tuple[float | None, float | None]:
    """Offset (s) such that ref_time = video_time + offset, and its correlation.

    Scans every offset in [lo_s, hi_s] and keeps the one whose correlation
    between the video's distance trace and the marker trace is highest. A
    shift that leaves less than `min_overlap` of the video inside the marker
    recording is not considered, so a sliver of overlap cannot win by luck.
    """
    if len(video) < 10:
        return None, None
    best = (None, None)
    steps = int(round((hi_s - lo_s) / step_s))
    for k in range(steps + 1):
        off = lo_s + k * step_s
        a, b = [], []
        for t, d in video:
            r = _interp(ref_t, ref_d, t + off)
            if r is not None:
                a.append(d)
                b.append(r)
        if len(a) < min_overlap * len(video):
            continue
        r = _pearson(a, b)
        if r is not None and (best[1] is None or r > best[1]):
            best = (off, r)
    return best


# ── matching and agreement ─────────────────────────────────────────────────

def match_taps(ours: list[float], ref: list[float],
               tol_s: float) -> list[tuple[float, float]]:
    """One-to-one pairs (ours, ref) within `tol_s`, closest pairs first."""
    pairs = sorted(((abs(o - r), i, j) for i, o in enumerate(ours)
                    for j, r in enumerate(ref) if abs(o - r) <= tol_s))
    used_o, used_r, out = set(), set(), []
    for _, i, j in pairs:
        if i in used_o or j in used_r:
            continue
        used_o.add(i)
        used_r.add(j)
        out.append((ours[i], ref[j]))
    return sorted(out)


def timing_agreement(ours: list[float], ref: list[float],
                     tol_s: float = 0.15, lead_search_s: float = 0.3) -> dict:
    """Recall, precision and timing error of our taps against the reference.
    Both lists must already be on one clock and cover one window.

    Our detector fires when the closing fingers cross a threshold, so its
    taps sit a roughly constant distance from the reference's (ours minus
    contact onset: about +20 ms across EHWGesture; against the marker
    minimum it was -50 to -130 ms). A constant offset moves no interval and
    no CV%, but left in it can push true detections outside `tol_s` and book
    them as a miss plus an extra. So it is measured first (median error over
    a loose `lead_search_s` match), reported as `lead_ms` (negative = ours
    earlier), and taken out before the strict match that decides recall and
    precision. `err_sd_ms` is then the per-tap jitter around it.
    """
    loose = match_taps(ours, ref, lead_search_s)
    lead = 0.0
    if loose:
        errs0 = sorted(o - r for o, r in loose)
        lead = errs0[len(errs0) // 2]
    shifted = [o - lead for o in ours]
    pairs = match_taps(shifted, ref, tol_s)
    errs = [(o + lead - r) * 1000.0 for o, r in pairs]
    n = len(pairs)
    out = {"ref_taps": len(ref), "our_taps": len(ours), "matched": n,
           "missed": len(ref) - n, "extra": len(ours) - n,
           "recall": n / len(ref) if ref else None,
           "precision": n / len(ours) if ours else None,
           "lead_ms": lead * 1000.0 if loose else None,
           "err_mean_ms": None, "err_sd_ms": None}
    if n:
        mean = sum(errs) / n
        out["err_mean_ms"] = mean
        if n > 1:
            out["err_sd_ms"] = math.sqrt(sum((e - mean) ** 2 for e in errs) / (n - 1))
    return out


def bland_altman(ours: list[float], ref: list[float]) -> dict | None:
    """Bias and 95% limits of agreement, plus Pearson r and MAE."""
    pairs = [(a, b) for a, b in zip(ours, ref) if a is not None and b is not None]
    n = len(pairs)
    if n < 2:
        return None
    diffs = [a - b for a, b in pairs]
    bias = sum(diffs) / n
    sd = math.sqrt(sum((d - bias) ** 2 for d in diffs) / (n - 1))
    return {"n": n, "bias": bias, "loa_low": bias - 1.96 * sd,
            "loa_high": bias + 1.96 * sd,
            "mae": sum(abs(d) for d in diffs) / n,
            "r": _pearson([a for a, _ in pairs], [b for _, b in pairs])}


# ── statistics for label-based validation (HUBU-FIS) ─────────────────────────

def ranks(vals: list[float]) -> list[float]:
    """1-based ranks with ties sharing their average rank."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman's rho: Pearson on average ranks, so ties are handled."""
    if len(x) < 3:
        return None
    return _pearson(ranks(x), ranks(y))


def auc(pos: list[float], neg: list[float]) -> float | None:
    """Probability a random `pos` value exceeds a random `neg` one (ties
    count half) -- the Mann-Whitney form of the ROC area."""
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(pos) * len(neg))


def cluster_bootstrap(rows: list[dict], cluster: str, stat, n: int = 2000,
                      seed: int = 0, level: float = 0.95):
    """(estimate, low, high) for `stat(rows)`, resampling whole clusters.

    Each person contributes two hands, so resampling videos would treat
    them as independent and understate the interval. Draws where the
    statistic is undefined (e.g. one AUC group empty) are skipped."""
    import random
    est = stat(rows)
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[cluster], []).append(r)
    keys = sorted(groups)
    rng = random.Random(seed)
    draws = []
    for _ in range(n):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in groups[k]]
        v = stat(sample)
        if v is not None:
            draws.append(v)
    if est is None or len(draws) < n // 2:
        return est, None, None
    draws.sort()
    a = (1 - level) / 2
    return est, draws[int(a * len(draws))], draws[min(len(draws) - 1, int((1 - a) * len(draws)))]
