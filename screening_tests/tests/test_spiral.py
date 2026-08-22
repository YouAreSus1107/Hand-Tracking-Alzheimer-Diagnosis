"""
Unit tests for the spiral engine (SPIRAL_TEST_PLAN.md §8): pure geometry +
metrics exercised against synthetic fingertip traces — no camera, no MediaPipe.

Run:  python -m pytest screening_tests/tests/test_spiral.py
 or:  python screening_tests/tests/test_spiral.py   (self-runs without pytest)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.spiral.geometry import scale_spiral_to_frame
from core.spiral.metrics import (compute_metrics, sparc, smoothness_index,
                                 sparc_band, compute_normalized_jerk,
                                 compute_velocity_cv, compute_tremor,
                                 compute_completion, SAL_TYPICAL, SAL_CONCERN)

FW, FH = 640, 480
SP, WU, CENTER, B = scale_spiral_to_frame(FW, FH)
SP_NP = np.array(SP, dtype=np.float32)

# Arc-length parameterization of the template, so a synthetic trace can follow
# it at a constant speed WITHOUT the integer-index staircase that would inject
# spurious high-frequency spectral content.
_TPL = np.array(SP, dtype=float)
_SEG = np.hypot(np.diff(_TPL[:, 0]), np.diff(_TPL[:, 1]))
_CUM = np.concatenate([[0.0], np.cumsum(_SEG)])
_TOTAL = _CUM[-1]


def make_trace(duration=20.0, fps=30.0, tremor_amp=0.0, tremor_hz=5.0,
               noise=0.0, coverage=1.0, seed=0):
    """Synthetic fingertip trace that follows the template at constant speed.
    tremor_amp adds a sinusoid (px); noise adds white jitter (px); coverage<1
    stops the trace partway along the spiral."""
    rng = np.random.default_rng(seed)
    n = int(duration * fps)
    ts = np.arange(n) / fps
    targets = np.linspace(0.0, _TOTAL * coverage, n)
    xs = np.interp(targets, _CUM, _TPL[:, 0])
    ys = np.interp(targets, _CUM, _TPL[:, 1])
    if tremor_amp > 0:
        xs = xs + tremor_amp * np.sin(2 * np.pi * tremor_hz * ts)
        ys = ys + tremor_amp * np.cos(2 * np.pi * tremor_hz * ts)
    if noise > 0:
        xs = xs + rng.normal(0, noise, n)
        ys = ys + rng.normal(0, noise, n)
    return ts.tolist(), xs.tolist(), ys.tolist()


# ── SPARC / smoothness ───────────────────────────────────────────────────────

def test_clean_trace_is_smooth_and_scoreable():
    ts, xs, ys = make_trace()
    m = compute_metrics(ts, xs, ys, [], SP_NP)
    assert m["scoreable"], m["reason"]
    assert m["sparc"] > SAL_TYPICAL           # clean → success band
    assert m["status"] == "success"
    assert m["smoothness_index"] > 70


def test_tremor_lowers_smoothness():
    _, xs_c, ys_c = make_trace()
    ts, xs_c2, ys_c2 = make_trace()
    clean = compute_metrics(ts, xs_c2, ys_c2, [], SP_NP)
    tsx, xt, yt = make_trace(tremor_amp=8.0, tremor_hz=5.0)
    shaky = compute_metrics(tsx, xt, yt, [], SP_NP)
    assert shaky["sparc"] < clean["sparc"]    # more negative = less smooth
    assert shaky["smoothness_index"] < clean["smoothness_index"]


def test_strong_tremor_reads_danger():
    ts, xs, ys = make_trace(tremor_amp=16.0, tremor_hz=6.0)
    m = compute_metrics(ts, xs, ys, [], SP_NP)
    assert m["sparc"] < SAL_CONCERN
    assert m["status"] == "danger"


def test_sparc_duration_invariance():
    # Same smooth motion sampled over 15 s vs 30 s → same smoothness band.
    a = compute_metrics(*make_trace(duration=15.0), dev_pct=[], sp_np=SP_NP)
    b = compute_metrics(*make_trace(duration=30.0), dev_pct=[], sp_np=SP_NP)
    assert a["status"] == b["status"] == "success"
    assert abs(a["sparc"] - b["sparc"]) < 1.0


def test_sparc_amplitude_invariance():
    # Scaling the whole path (bigger spiral, faster speed) leaves SPARC ~stable
    # because the magnitude spectrum is normalized.
    ts, xs, ys = make_trace()
    s1 = sparc(*_speed(ts, xs, ys))
    xs2 = list(np.array(xs) * 2.0)
    ys2 = list(np.array(ys) * 2.0)
    s2 = sparc(*_speed(ts, xs2, ys2))
    assert abs(s1 - s2) < 0.5


def _speed(ts, xs, ys):
    """(speed, fs) helper mirroring the engine's uniform profile."""
    ts = np.asarray(ts, float)
    n = len(ts)
    fs = (n - 1) / (ts[-1] - ts[0])
    tu = np.linspace(ts[0], ts[-1], n)
    xu = np.interp(tu, ts, xs)
    yu = np.interp(tu, ts, ys)
    speed = np.hypot(np.diff(xu), np.diff(yu)) * fs
    return speed, fs


# ── tremor spectral readout ──────────────────────────────────────────────────

def test_tremor_frequency_detected():
    ts, xs, ys = make_trace(duration=20.0, fps=30.0, tremor_amp=8.0, tremor_hz=5.0)
    tr = compute_tremor(ts, xs, ys)
    assert tr is not None
    assert abs(tr["tremor_dominant_hz"] - 5.0) < 1.0
    clean = compute_tremor(*make_trace())
    assert tr["tremor_power_frac"] > clean["tremor_power_frac"]


def test_tremor_none_when_fps_cannot_resolve_band():
    # 3 fps → Nyquist 1.5 Hz < tremor band start (2 Hz) → no readout.
    ts, xs, ys = make_trace(duration=20.0, fps=3.0)
    assert compute_tremor(ts, xs, ys) is None


# ── velocity CV / jerk ───────────────────────────────────────────────────────

def test_velocity_cv_low_for_constant_speed():
    ts, xs, ys = make_trace()
    _, _, cv = compute_velocity_cv(ts, xs, ys)
    assert cv is not None and cv < 25.0        # constant-speed trace


def test_jerk_higher_with_tremor():
    clean = compute_normalized_jerk(*make_trace())
    shaky = compute_normalized_jerk(*make_trace(tremor_amp=8.0))
    assert shaky > clean > 0


# ── gates / robustness ───────────────────────────────────────────────────────

def test_unscoreable_too_few_frames():
    ts, xs, ys = make_trace(duration=0.5, fps=30.0)
    m = compute_metrics(ts, xs, ys, [], SP_NP)
    assert not m["scoreable"] and "frames" in m["reason"].lower()


def test_unscoreable_low_completion():
    ts, xs, ys = make_trace(duration=20.0, coverage=0.05)
    m = compute_metrics(ts, xs, ys, [], SP_NP)
    assert not m["scoreable"] and "spiral" in m["reason"].lower()


def test_degenerate_trace_returns_none_not_crash():
    ts = [0.0, 0.1, 0.2, 0.3]
    xs = [100.0] * 4
    ys = [100.0] * 4
    assert sparc(*_speed(ts, xs, ys)) is None or isinstance(
        sparc(*_speed(ts, xs, ys)), float)
    assert compute_normalized_jerk(ts, xs, ys) is None
    m = compute_metrics(ts, xs, ys, [], SP_NP)
    assert not m["scoreable"]


def test_smoothness_index_bounds_and_bands():
    assert smoothness_index(-1.5) == 100.0
    assert smoothness_index(-6.0) == 0.0
    assert smoothness_index(None) is None
    assert sparc_band(-2.0)[0] == "success"
    assert sparc_band(-3.8)[0] == "warning"
    assert sparc_band(-5.0)[0] == "danger"
    assert sparc_band(None)[0] == "info"


def test_completion_full_vs_partial():
    _, xs, ys = make_trace(coverage=1.0)
    full = compute_completion(xs, ys, SP_NP)
    _, xp, yp = make_trace(coverage=0.5)
    partial = compute_completion(xp, yp, SP_NP)
    assert full > 0.8
    assert partial < full


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:                 # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
