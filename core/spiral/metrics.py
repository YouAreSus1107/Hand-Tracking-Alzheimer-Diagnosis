"""
Spiral metrics (pure) — literature-standard movement-quality scoring for a
self-paced spiral trace. No camera, no UI; unit-tested against synthetic traces
in screening_tests/tests/test_spiral.py. See docs/tests/SPIRAL_TEST_PLAN.md §3.

Headline is movement smoothness:
  sparc / smoothness_index  Spectral Arc Length (Balasubramanian et al., J
                            NeuroEng Rehabil 2015) of the speed profile — the
                            amplitude/duration-robust smoothness measure.
Support:
  norm_jerk                 dimensionless jerk from the 2-D position path.
  vel_cv_pct                speed coefficient of variation (Schroter V-Rel 2003).
  tremor_power_frac / hz    detrended-position tremor-band power + peak (bounded
                            by the 30 fps Nyquist caveat — secondary readout).
  mean_dev_pct              swept-angle radial deviation (spatial accuracy).
  completion_pct            fraction of the template visited — a data-quality
                            GATE, not the headline.

Jitter is measured on the *raw* (minimally filtered) fingertip: the One-Euro
smoothing used for display would erase it (docs/tests/SPIRAL_TEST_PLAN.md §3.1).
"""

from __future__ import annotations

import math

import numpy as np

# ── Gates / thresholds ──────────────────────────────────────────────────────
MIN_FRAMES = 30            # minimum data frames to score
MIN_DURATION_S = 4.0       # minimum trace length to score
MIN_COMPLETION = 0.25      # must have traced this fraction of the template
IDLE_VEL_THRESHOLD = 15.0  # px/s below which a frame is "idle" (active ratio)
CLOSE_THRESHOLD = 30.0     # px proximity that counts a template point "visited"

# Tremor analysis band (Hz). Lower edge sits above the voluntary tracing motion
# (a self-paced spiral turns at < ~1 Hz); upper edge is clamped to the Nyquist.
TREMOR_BAND = (3.5, 12.0)

# ── SPARC → smoothness-index / band anchors (PROVISIONAL) ───────────────────
# SPARC is negative; nearer zero = smoother. Anchors below are bracketed from
# our own traces + the literature's direction, NOT clinically validated — to be
# calibrated on public HandPD/NewHandPD spiral data (docs/tests/SPIRAL_TEST_PLAN.md §4).
SAL_SMOOTH = -1.5          # maps to smoothness index 100
SAL_ROUGH = -6.0           # maps to smoothness index 0
SAL_TYPICAL = -3.2         # success ↔ warning boundary
SAL_CONCERN = -4.0         # warning ↔ danger boundary

# SPARC's cutoff is found above the tracker's noise floor (see sparc()). K and
# the smoothing were chosen by replaying all 41 recorded runs (2026-09-30):
# median -2.27, 38/41 Typical, the three left are the runs with real tracking
# trouble (multi-second dropouts, 15 % off the line); the canonical cutoff put
# 30/41 outside Typical and 16 at index 0, on traces whose deviation and
# tremor readings were clean. The same sweep kept a 2 px tremor injected into
# a recorded run, and 4-16 px synthetic tremors, below SAL_CONCERN. Wider
# smoothing (0.3 Hz) spread a steady tremor line under the threshold; K 5
# let the bad-tracking runs through.
NOISE_K = 4.0              # cutoff threshold = NOISE_K x the noise floor
CUTOFF_SMOOTH_HZ = 0.1     # spectrum smoothing used only to find the cutoff

# ── the two scores (engine 4, PROVISIONAL) ───────────────────────────────────
# The run is reported as two separate scores, and the verdict is the worse:
#
#   Line accuracy (0-100, higher = closer): how far the trace strays from the
#     spiral, from mean_dev_pct (radial error at the swept angle, % of radius).
#   Tremor (0-100, higher = more tremor): fingertip oscillation in TREMOR_BAND,
#     the clinical tremor range, as a % of the radius.
#
# SPARC (the smoothness index) is still computed and saved but decides
# nothing: on the one labelled pair (2026-10-01 07:26 no tremor / 07:27 a
# deliberate tremor) it scored the tremor run smoother, 92 vs 79.
#
# Tremor amplitude is ROBUST: median of the band-passed amplitude, scaled so a
# steady oscillation reads its RMS. A tracking jump is a one-frame spike that
# an RMS turns into "tremor" (one such run read 3.4 % by RMS, 0.8 % robust);
# a tremor is sustained, so the median keeps it.
TREMOR_BAND = (4.0, 8.0)   # Hz; 4 = the floor of pathological tremor; the
                           # upper edge is clamped below Nyquist
_RAYLEIGH_MEDIAN_TO_RMS = 1.2011   # 1/sqrt(ln 4): median -> RMS of a 2-D sine

# Tremor bands, % of radius. The labelled pair read 0.50 (no tremor) and 0.81
# (tremor); recorded runs that look clean read 0.2-0.5. Mild sits between the
# pair, Marked above everything recorded so far. Set on two labelled runs:
# re-set these as soon as more labelled runs exist.
TREMOR_MILD_PCT = 0.65
TREMOR_MARKED_PCT = 1.0
TREMOR_FLOOR_PCT = 0.30    # tremor score 0 (camera jitter of a clean run)
TREMOR_FULL_PCT = 1.50     # tremor score 100

# Line accuracy: mean deviation (% of radius) -> score. 3 % or less = 100
# (recorded clean runs sit at 2-5 %), 7 % = 60, 10 % = 30, 13 % = 0. Tolerant:
# only runs that visibly left the line (7.5-15 %) fall below Typical.
ACC_PERFECT_DEV = 3.0
ACC_PTS_PER_DEV = 10.0
ACC_TYPICAL = 60.0         # score >= this: Typical
ACC_CONCERN = 30.0         # score < this: Follow-up

# 1 = canonical SPARC cutoff (lost to the noise floor); 2 = noise-aware cutoff
# and Nyquist clamp; 3 = shake folded into a SPARC verdict; 4 = two scores,
# line accuracy and tremor, SPARC kept as a reading only. Stamped per session.
ENGINE_VERSION = 4


# np.trapz was renamed np.trapezoid in NumPy 2.0.
_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))


# ── shared speed profile ─────────────────────────────────────────────────────

def _speed_profile(ts, xs, ys):
    """Resample the fingertip path to a uniform time grid and return
    (tu, xu, yu, fs, speed). Uniform sampling is required for the FFT-based
    metrics (SPARC, tremor). Returns None if the trace is too short/degenerate."""
    ts = np.asarray(ts, dtype=np.float64)
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    n = len(ts)
    if n < 4:
        return None
    duration = ts[-1] - ts[0]
    if duration <= 1e-6:
        return None
    fs = (n - 1) / duration                 # mean sampling rate
    tu = np.linspace(ts[0], ts[-1], n)
    xu = np.interp(tu, ts, xs)
    yu = np.interp(tu, ts, ys)
    dt = 1.0 / fs
    speed = np.hypot(np.diff(xu), np.diff(yu)) / dt
    return tu, xu, yu, fs, speed


# ── SPARC (Balasubramanian et al. 2015) ──────────────────────────────────────

def sparc(speed, fs, padlevel=4, fc=10.0, amp_th=0.05,
          noise_k=NOISE_K, smooth_hz=CUTOFF_SMOOTH_HZ):
    """Spectral Arc Length of a speed profile. Returns a negative scalar (nearer
    zero = smoother), or None when it can't be computed. Canonical formulation:
    normalized magnitude spectrum, adaptive amplitude cutoff, arc length.

    Engine 2: the adaptive cutoff is found above the tracker's noise floor.
    The speed of a webcam fingertip carries a flat (white) noise floor of
    ~1-3 % of the DC peak from ~1 Hz to Nyquist, and its random bumps reached
    the canonical 5 % threshold in about half of the recorded runs: one bump
    at 7 Hz stretched the arc across all the noise and turned a clean trace
    (mean deviation 3.5 %, no tremor) from -2.3 into -6.0, index 0. So the
    cutoff is now read off a lightly smoothed spectrum (`smooth_hz`), against
    `max(amp_th, noise_k * floor)` where the floor is the median of the upper
    half of the analysed band (a narrow tremor peak does not move a median).
    The arc itself is still measured on the unsmoothed spectrum. A real tremor
    of 2 px stands well clear of the floor and still pulls SPARC down (-2.1 ->
    -5.8 on a replayed run), which the old cutoff could not tell apart from no
    tremor at all. `fc` is also clamped to Nyquist: at 13 fps a 10 Hz
    cutoff read the mirrored half of the spectrum. noise_k=0 restores the
    canonical cutoff (Nyquist clamp aside)."""
    speed = np.asarray(speed, dtype=np.float64)
    if len(speed) < 10 or fs <= 0:
        return None
    nfft = int(2 ** (math.ceil(math.log2(len(speed))) + padlevel))
    f = np.arange(0, fs, fs / nfft)
    Mf = np.abs(np.fft.fft(speed, nfft))
    mx = Mf.max()
    if mx <= 0:
        return None
    Mf = Mf / mx
    L = min(len(f), len(Mf))
    f, Mf = f[:L], Mf[:L]

    sel = np.where(f <= min(fc, fs / 2.0))[0]
    if len(sel) < 2:
        return None
    f_sel, Mf_sel = f[sel], Mf[sel]

    th = amp_th
    look = Mf_sel
    if noise_k > 0 and len(f_sel) >= 8:
        w = max(1, int(round(smooth_hz / (f_sel[1] - f_sel[0]))))
        if w > 1:
            look = np.convolve(Mf_sel, np.ones(w) / w, mode="same")
        upper = look[f_sel >= f_sel[-1] / 2.0]
        if len(upper):
            th = max(amp_th, noise_k * float(np.median(upper)))

    inx = np.where(look >= th)[0]
    if len(inx) < 2:
        return None
    f_sel = f_sel[inx[0]:inx[-1] + 1]
    Mf_sel = Mf_sel[inx[0]:inx[-1] + 1]
    span = f_sel[-1] - f_sel[0]
    if span <= 0 or len(f_sel) < 2:
        return None

    sal = -np.sum(np.sqrt((np.diff(f_sel) / span) ** 2 + np.diff(Mf_sel) ** 2))
    return float(sal)


def live_smoothness_status(ts, xs, ys):
    """Status token ('success'/'warning'/'danger'/'info') for a short rolling
    window of the raw fingertip — colours the live fingertip so the on-screen
    signal matches how the run will be scored."""
    prof = _speed_profile(ts, xs, ys)
    if prof is None:
        return "info"
    return sparc_band(sparc(prof[4], prof[3]))[0]


def smoothness_index(sal):
    """Map SPARC to a 0–100 smoothness index (higher = smoother) for display."""
    if sal is None:
        return None
    idx = (sal - SAL_ROUGH) / (SAL_SMOOTH - SAL_ROUGH) * 100.0
    return float(max(0.0, min(100.0, idx)))


def sparc_band(sal):
    """(status_token, plain-language label) for a SPARC value. PROVISIONAL bands
    — always shown with icon + word per the style guide."""
    if sal is None:
        return "info", "Smoothness unavailable"
    if sal > SAL_TYPICAL:
        return "success", "Smooth, well-controlled tracing"
    if sal > SAL_CONCERN:
        return "warning", "Mild jitter - consider monitoring"
    return "danger", "Marked jitter - recommend follow-up"


# ── normalized jerk (2-D position path) ──────────────────────────────────────

def compute_normalized_jerk(ts, xs, ys):
    """Dimensionless jerk from the position path: (T^5 / L^2) * ∫|jerk|^2 dt.
    Lower = smoother. Returns None for degenerate traces."""
    prof = _speed_profile(ts, xs, ys)
    if prof is None:
        return None
    tu, xu, yu, fs, speed = prof
    if len(tu) < 6:
        return None
    vx, vy = np.gradient(xu, tu), np.gradient(yu, tu)
    ax, ay = np.gradient(vx, tu), np.gradient(vy, tu)
    jx, jy = np.gradient(ax, tu), np.gradient(ay, tu)
    jerk_sq = jx ** 2 + jy ** 2
    duration = tu[-1] - tu[0]
    length = float(_trapz(np.hypot(vx, vy), tu))
    if duration <= 0 or length < 1.0:
        return None
    integral = float(_trapz(jerk_sq, tu))
    return integral * (duration ** 5) / (length ** 2)


# ── velocity coefficient of variation (Schroter V-Rel) ───────────────────────

def compute_velocity_cv(ts, xs, ys):
    """Return (mean_speed, sd_speed, cv_pct) of the speed profile."""
    prof = _speed_profile(ts, xs, ys)
    if prof is None:
        return None, None, None
    speed = prof[4]
    if len(speed) < 2:
        return None, None, None
    mean_v = float(np.mean(speed))
    sd_v = float(np.std(speed, ddof=1))
    cv = (sd_v / mean_v * 100.0) if mean_v > 0 else 0.0
    return mean_v, sd_v, cv


# ── tremor (detrended-position spectrum) ─────────────────────────────────────

def compute_tremor(ts, xs, ys, band=TREMOR_BAND):
    """High-pass the position path, then report the fraction of spectral power in
    the tremor band and its peak frequency. Bounded by the actual Nyquist — the
    band's upper edge is clamped to what the sampling rate can resolve. Returns a
    dict or None. SECONDARY, caveated readout (docs/tests/SPIRAL_TEST_PLAN.md §3.3)."""
    prof = _speed_profile(ts, xs, ys)
    if prof is None:
        return None
    tu, xu, yu, fs, _ = prof
    m = len(tu)
    if m < 32:
        return None
    nyq = fs / 2.0
    if nyq <= band[0]:
        return None                          # fps can't resolve the tremor band
    hi = min(band[1], nyq * 0.95)

    # Linear-detrend each axis (remove drift, keep the voluntary tracing
    # oscillation as the spectral denominator) then de-mean. High-passing first
    # would empty the denominator and force the fraction toward 1.
    def detrend(sig):
        out = sig - np.polyval(np.polyfit(tu, sig, 1), tu)
        return out - out.mean()

    w = np.hanning(m)
    Fx = np.fft.rfft(detrend(xu) * w)
    Fy = np.fft.rfft(detrend(yu) * w)
    freqs = np.fft.rfftfreq(m, d=1.0 / fs)
    psd = np.abs(Fx) ** 2 + np.abs(Fy) ** 2

    analysis = (freqs >= 0.2) & (freqs <= hi)
    total = float(psd[analysis].sum())
    if total <= 0:
        return None
    in_band = (freqs >= band[0]) & (freqs <= hi)
    tremor_power = float(psd[in_band].sum())
    dom = float(freqs[in_band][np.argmax(psd[in_band])]) if in_band.any() else None
    return {"tremor_power_frac": tremor_power / total,
            "tremor_dominant_hz": dom, "sample_fps": float(fs)}


# ── tremor: 4-8 Hz oscillation of the fingertip ──────────────────────────────

# Same gate as core/spiral/progress.py: faster than this many outer radii per
# second is a tracking glitch (a real 8 Hz tremor at 5 % of the radius moves
# about 2.5 radii/s). A run of more than MAX_TELEPORT_RUN such frames is taken
# as a real move, as progress.py does.
TELEPORT_RADII_S = 6.0
MAX_TELEPORT_RUN = 3


def _drop_teleports(ts, xs, ys, radius_px):
    """Samples without one-frame tracking jumps (measured against the last
    kept sample). The gap is bridged by the uniform resample."""
    if len(ts) < 3:
        return ts, xs, ys
    keep = [0]
    run = 0
    for i in range(1, len(ts)):
        j = keep[-1]
        dt = ts[i] - ts[j]
        fast = dt > 0 and (math.hypot(xs[i] - xs[j], ys[i] - ys[j]) / dt
                           > TELEPORT_RADII_S * radius_px)
        if fast and run < MAX_TELEPORT_RUN:
            run += 1
            continue
        run = 0
        keep.append(i)
    if len(keep) == len(ts):
        return ts, xs, ys
    return ([ts[i] for i in keep], [xs[i] for i in keep],
            [ys[i] for i in keep])


def compute_tremor_amp(ts, xs, ys, radius_px, band=TREMOR_BAND):
    """Robust fingertip oscillation in `band` (Hz): px and % of the spiral's
    radius, plus the band's peak frequency. None when the trace is too short
    or the frame rate cannot reach the band. Plain NumPy: a moving average one
    lower-edge period long takes the tracing motion out, an FFT mask keeps the
    band, half a second is dropped at each end (edge effects), and the median
    amplitude (not the RMS) is kept so tracking jumps do not read as tremor.
    Frames that jump faster than a hand can move are dropped first: the FFT
    mask rings, so an undropped spike lifts the whole band-passed trace."""
    if radius_px and radius_px > 0:
        ts, xs, ys = _drop_teleports(ts, xs, ys, radius_px)
    prof = _speed_profile(ts, xs, ys)
    if prof is None or not radius_px or radius_px <= 0:
        return None
    tu, xu, yu, fs, _ = prof
    lo, hi = band[0], min(band[1], fs / 2.0 * 0.9)
    edge = int(0.5 * fs)
    if hi <= lo or len(tu) < 4 * edge + 16:
        return None
    L = max(3, int(round(fs / lo)))
    kernel = np.ones(L) / L

    def bandpass(sig):
        padded = np.pad(sig, (L, L), mode="reflect")
        resid = sig - np.convolve(padded, kernel, mode="same")[L:-L]
        F = np.fft.rfft(resid)
        f = np.fft.rfftfreq(len(resid), 1.0 / fs)
        F[(f < lo) | (f > hi)] = 0
        return np.fft.irfft(F, len(resid))[edge:-edge], F, f

    bx, Fx, f = bandpass(xu)
    by, Fy, _ = bandpass(yu)
    amp = float(np.median(np.hypot(bx, by))) * _RAYLEIGH_MEDIAN_TO_RMS
    power = np.abs(Fx) ** 2 + np.abs(Fy) ** 2
    peak = float(f[int(np.argmax(power))]) if power.any() else None
    return {"tremor_px": amp, "tremor_pct": amp / radius_px * 100.0,
            "tremor_peak_hz": peak}


def tremor_score(pct):
    """0-100, higher = more tremor."""
    if pct is None:
        return None
    x = (pct - TREMOR_FLOOR_PCT) / (TREMOR_FULL_PCT - TREMOR_FLOOR_PCT)
    return float(max(0.0, min(1.0, x)) * 100.0)


def tremor_band(pct):
    """(status_token, label) for a tremor reading. PROVISIONAL bands."""
    if pct is None:
        return "info", "Tremor unavailable"
    if pct < TREMOR_MILD_PCT:
        return "success", "No tremor detected"
    if pct < TREMOR_MARKED_PCT:
        return "warning", "Mild tremor - consider monitoring"
    return "danger", "Marked tremor - recommend follow-up"


def accuracy_score(dev_pct):
    """0-100 line accuracy from the mean deviation, higher = closer."""
    if dev_pct is None:
        return None
    x = 100.0 - (dev_pct - ACC_PERFECT_DEV) * ACC_PTS_PER_DEV
    return float(max(0.0, min(100.0, x)))


def accuracy_band(score):
    """(status_token, label) for a line-accuracy score. PROVISIONAL bands."""
    if score is None:
        return "info", "Accuracy unavailable"
    if score >= ACC_TYPICAL:
        return "success", "Traced close to the line"
    if score >= ACC_CONCERN:
        return "warning", "Drifted from the line - consider monitoring"
    return "danger", "Far from the line - recommend follow-up"


_RANK = {"success": 0, "warning": 1, "danger": 2}


# ── coverage / activity ──────────────────────────────────────────────────────

def compute_completion(xs, ys, sp_np, threshold=CLOSE_THRESHOLD):
    """Fraction of template points the fingertip came within `threshold` of."""
    n = len(sp_np)
    if n == 0 or len(xs) == 0:
        return 0.0
    visited = np.zeros(n, dtype=bool)
    for fx, fy in zip(xs, ys):
        d = np.sqrt(np.sum((sp_np - np.array([fx, fy], np.float32)) ** 2, axis=1))
        visited |= d < threshold
    return float(np.sum(visited) / n)


def compute_active_ratio(ts, xs, ys, threshold=IDLE_VEL_THRESHOLD):
    """Fraction of frames moving faster than `threshold` px/s."""
    prof = _speed_profile(ts, xs, ys)
    if prof is None:
        return 0.0
    speed = prof[4]
    if len(speed) == 0:
        return 0.0
    return float(np.mean(speed > threshold))


# ── orchestrator ─────────────────────────────────────────────────────────────

def compute_metrics(ts, xs, ys, dev_pct, sp_np, *, min_frames=MIN_FRAMES,
                    min_duration_s=MIN_DURATION_S, min_completion=MIN_COMPLETION,
                    blackouts=None, radius_px=None):
    """Score one self-paced spiral trace. Always returns a dict; `scoreable` is
    False with a specific human-readable `reason` when it can't be scored
    (mirrors core/tapping/metrics.compute_metrics).

    ts/xs/ys  : raw fingertip time + pixel path (jitter lives here).
    dev_pct   : per-frame radial deviation (% of radius) from the run loop, or [].
    sp_np     : (N,2) template points for the completion gate.
    radius_px : the spiral's outer radius, for the shake as a % of it; None
                takes it from sp_np (its first point is the centre).
    blackouts : (start, end) times the hand was part-way out of frame or lost
                (core/framing.py). Samples inside are dropped and the rest is
                scored as one trace, exactly as a run with a gap always has
                been. Scoring each clean stretch separately was tried and
                rejected: replaying 41 recorded runs with their bottom arcs
                blanked out, per-stretch SPARC landed a median 13 index points
                from the run's own clean score (short stretches bias it), the
                single bridged trace 3. None/[] leaves the input untouched.
    """
    skipped_pct = None
    if blackouts and len(ts) > 1:
        keep = [i for i, t in enumerate(ts)
                if not any(b0 <= t <= b1 for b0, b1 in blackouts)]
        total = float(ts[-1] - ts[0])
        inside = sum(max(0.0, min(b1, ts[-1]) - max(b0, ts[0]))
                     for b0, b1 in blackouts)
        skipped_pct = round(100.0 * min(1.0, inside / total), 1) if total > 0 else None
        ts = [ts[i] for i in keep]
        xs = [xs[i] for i in keep]
        ys = [ys[i] for i in keep]
        if dev_pct is not None and len(dev_pct) > 0:
            dev_pct = [dev_pct[i] for i in keep]
    n = len(ts)
    out: dict = {
        "scoreable": False, "reason": None, "frames": n, "duration_s": None,
        "sparc": None, "smoothness_index": None,
        "norm_jerk": None, "vel_mean_px_s": None, "vel_sd_px_s": None,
        "vel_cv_pct": None, "tremor_power_frac": None, "tremor_dominant_hz": None,
        "mean_dev_pct": None, "completion_pct": None, "active_ratio_pct": None,
        "accuracy_score": None, "accuracy_status": None,
        "tremor_score": None, "tremor_pct": None, "tremor_px": None,
        "tremor_status": None, "smoothness_status": None, "verdict_from": None,
        "status": None, "label": None, "engine_version": ENGINE_VERSION,
    }
    if skipped_pct is not None:
        out["skipped_pct"] = skipped_pct      # provenance, not part of the score

    if n < min_frames:
        out["reason"] = (f"Not enough data frames ({n} < {min_frames}). "
                         f"Keep your hand visible and try again.")
        return out
    duration = float(ts[-1] - ts[0])
    out["duration_s"] = round(duration, 2)
    if duration < min_duration_s:
        out["reason"] = (f"Trace was too short ({duration:.1f}s). Trace the whole "
                         f"spiral outward and try again.")
        return out

    completion = compute_completion(xs, ys, sp_np)
    out["completion_pct"] = completion * 100.0
    out["active_ratio_pct"] = compute_active_ratio(ts, xs, ys) * 100.0
    if completion < min_completion:
        out["reason"] = (f"Only {completion * 100:.0f}% of the spiral was traced. "
                         f"Follow the whole line from center to edge.")
        return out

    prof = _speed_profile(ts, xs, ys)
    if prof is None:
        out["reason"] = "Could not compute a motion profile from this trace."
        return out
    speed, fs = prof[4], prof[3]

    sal = sparc(speed, fs)
    out["sparc"] = sal
    out["smoothness_index"] = smoothness_index(sal)
    out["norm_jerk"] = compute_normalized_jerk(ts, xs, ys)
    vmean, vsd, vcv = compute_velocity_cv(ts, xs, ys)
    out["vel_mean_px_s"], out["vel_sd_px_s"], out["vel_cv_pct"] = vmean, vsd, vcv

    tremor = compute_tremor(ts, xs, ys)
    if tremor:
        out["tremor_power_frac"] = tremor["tremor_power_frac"]

    if radius_px is None and sp_np is not None and len(sp_np) > 1:
        pts = np.asarray(sp_np, dtype=np.float64)
        radius_px = float(np.max(np.hypot(*(pts - pts[0]).T)))
    trem = compute_tremor_amp(ts, xs, ys, radius_px)
    if trem:
        out["tremor_px"] = trem["tremor_px"]
        out["tremor_pct"] = trem["tremor_pct"]
        out["tremor_score"] = tremor_score(trem["tremor_pct"])
        if trem["tremor_pct"] >= TREMOR_MILD_PCT:
            out["tremor_dominant_hz"] = trem["tremor_peak_hz"]

    if dev_pct is not None and len(dev_pct) > 0:
        out["mean_dev_pct"] = float(np.mean(dev_pct))

    # Two scores; the worse decides the run's verdict. SPARC is a reading.
    out["smoothness_status"] = sparc_band(sal)[0]
    out["accuracy_score"] = accuracy_score(out["mean_dev_pct"])
    acc_st, acc_label = accuracy_band(out["accuracy_score"])
    tr_st, tr_label = tremor_band(out["tremor_pct"])
    out["accuracy_status"], out["tremor_status"] = acc_st, tr_st
    if acc_st == "info" and tr_st == "info":
        out["reason"] = "Could not measure this trace."
        return out
    if _RANK.get(tr_st, -1) > _RANK.get(acc_st, -1):
        st, label, out["verdict_from"] = tr_st, tr_label, "tremor"
    elif _RANK.get(acc_st, -1) > _RANK.get(tr_st, -1):
        st, label, out["verdict_from"] = acc_st, acc_label, "accuracy"
    elif acc_st == "success":
        st, label, out["verdict_from"] = "success", "Accurate tracing, no tremor", "both"
    else:                                    # both warning or both danger
        st, label, out["verdict_from"] = tr_st, tr_label, "both"
    out["status"], out["label"] = st, label
    out["scoreable"] = True
    return out
