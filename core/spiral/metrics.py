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

def sparc(speed, fs, padlevel=4, fc=10.0, amp_th=0.05):
    """Spectral Arc Length of a speed profile. Returns a negative scalar (nearer
    zero = smoother), or None when it can't be computed. Canonical formulation:
    normalized magnitude spectrum, adaptive amplitude cutoff, arc length."""
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

    sel = np.where(f <= fc)[0]
    if len(sel) < 2:
        return None
    f_sel, Mf_sel = f[sel], Mf[sel]

    inx = np.where(Mf_sel >= amp_th)[0]
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
                    blackouts=None):
    """Score one self-paced spiral trace. Always returns a dict; `scoreable` is
    False with a specific human-readable `reason` when it can't be scored
    (mirrors core/tapping/metrics.compute_metrics).

    ts/xs/ys  : raw fingertip time + pixel path (jitter lives here).
    dev_pct   : per-frame radial deviation (% of radius) from the run loop, or [].
    sp_np     : (N,2) template points for the completion gate.
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
        "status": None, "label": None,
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
        out["tremor_dominant_hz"] = tremor["tremor_dominant_hz"]

    if dev_pct is not None and len(dev_pct) > 0:
        out["mean_dev_pct"] = float(np.mean(dev_pct))

    if sal is None:
        out["reason"] = "Could not compute smoothness from this trace."
        return out
    out["status"], out["label"] = sparc_band(sal)
    out["scoreable"] = True
    return out
