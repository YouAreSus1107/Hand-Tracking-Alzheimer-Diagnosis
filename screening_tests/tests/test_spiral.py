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
from core.spiral import practice as pr
from core.spiral.progress import SpiralProgress
from core.spiral.metrics import (compute_metrics, sparc, smoothness_index,
                                 sparc_band, compute_normalized_jerk,
                                 compute_velocity_cv, compute_tremor,
                                 compute_completion, SAL_TYPICAL, SAL_CONCERN,
                                 TREMOR_MILD_PCT, TREMOR_MARKED_PCT,
                                 accuracy_score, accuracy_band)

FW, FH = 640, 480
SP, PRACTICE_SP, CENTER, B = scale_spiral_to_frame(FW, FH)
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


def test_tracker_jitter_does_not_collapse_sparc():
    # A perfect trace with white jitter at the frame rates the suite really
    # runs at. 1.5 px puts the speed spectrum's noise floor where recorded runs
    # have it (1-3 % of DC; real tracker noise is heavier-tailed than a
    # Gaussian of the same step size). The canonical 5 % cutoff let one noise
    # bump stretch the arc across the whole floor: -6 to -9 (index 0) on most
    # seeds at 13-20 fps, which is what clean recorded runs scored.
    # (No tremor-peak check here: this constant-speed trace has almost no
    # slow movement, so noise is a large share of its tremor fraction.)
    for fps in (13.0, 20.0, 30.0):
        for seed in range(6):
            ts, xs, ys = make_trace(duration=35.0, fps=fps, noise=1.5,
                                    seed=seed)
            m = compute_metrics(ts, xs, ys, [], SP_NP)
            # SPARC is a reading since engine 4; its own band is what this
            # regression is about (1.5 px is also enough to register a little
            # "tremor", which is the tremor score's business, not SPARC's)
            assert m["smoothness_status"] == "success", (fps, seed, m["sparc"])


def test_no_tremor_peak_without_tremor():
    # Below the Mild tremor band the "peak" is noise and its Hz is random.
    m = compute_metrics(*make_trace(), [], SP_NP)
    assert m["tremor_pct"] is not None and m["tremor_pct"] < TREMOR_MILD_PCT
    assert m["tremor_score"] == 0.0
    assert m["tremor_status"] == "success"
    assert m["tremor_dominant_hz"] is None


def _irregular_tremor(n, fps, amp_px, lo=4.5, hi=7.5, seed=1):
    """Band-limited random wobble: an irregular tremor with no single steady
    line, which SPARC's noise-aware cutoff read as noise."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(2):
        F = np.fft.rfft(rng.normal(0, 1, n))
        f = np.fft.rfftfreq(n, 1.0 / fps)
        F[(f < lo) | (f > hi)] = 0
        sig = np.fft.irfft(F, n)
        out.append(sig / np.sqrt(np.mean(sig ** 2)) * amp_px / np.sqrt(2))
    return out


RADIUS = float(np.max(np.hypot(*(SP_NP - SP_NP[0]).T)))


def test_irregular_tremor_sets_the_verdict():
    # Engine 4: tremor is its own score and decides the verdict when it is the
    # worse of the two, even though the line is followed perfectly.
    fps = 25.0
    ts, xs, ys = make_trace(duration=30.0, fps=fps, noise=0.5)
    dev = [2.0] * len(ts)                      # right on the line
    for pct, want in ((0.8, "warning"), (1.6, "danger")):
        dx, dy = _irregular_tremor(len(ts), fps, pct / 100 * RADIUS)
        m = compute_metrics(ts, list(np.array(xs) + dx),
                            list(np.array(ys) + dy), dev, SP_NP)
        assert m["tremor_status"] == want, (pct, m["tremor_pct"])
        assert m["accuracy_status"] == "success"
        assert m["status"] == want and m["verdict_from"] == "tremor"
        assert abs(m["tremor_pct"] - pct) < 0.35 * pct
        assert 4.0 <= m["tremor_dominant_hz"] <= 8.0
    clean = compute_metrics(ts, xs, ys, dev, SP_NP)
    assert clean["status"] == "success" and clean["verdict_from"] == "both"
    assert clean["label"] == "Accurate tracing, no tremor"


def test_slow_wobble_is_not_tremor():
    # A 2-3 Hz wobble (what an imitated tremor usually is) is below the
    # pathological tremor band, so it does not score as tremor.
    fps = 25.0
    ts, xs, ys = make_trace(duration=30.0, fps=fps, noise=0.5)
    dx, dy = _irregular_tremor(len(ts), fps, 1.5 / 100 * RADIUS, lo=2.0, hi=3.0)
    m = compute_metrics(ts, list(np.array(xs) + dx), list(np.array(ys) + dy),
                        [], SP_NP)
    assert m["tremor_pct"] < TREMOR_MILD_PCT, m["tremor_pct"]


def test_tracking_jumps_do_not_read_as_tremor():
    # One-frame teleports every couple of seconds: an RMS turned these into
    # "tremor"; the robust amplitude does not.
    fps = 25.0
    ts, xs, ys = make_trace(duration=30.0, fps=fps, noise=0.5)
    xs = list(xs)
    for i in range(20, len(xs), 50):
        xs[i] += 60.0
    m = compute_metrics(ts, xs, ys, [], SP_NP)
    assert m["tremor_pct"] < TREMOR_MILD_PCT, m["tremor_pct"]


def test_line_accuracy_score_and_bands():
    assert accuracy_score(2.0) == 100.0
    assert accuracy_score(7.0) == 60.0
    assert accuracy_score(10.0) == 30.0
    assert accuracy_score(20.0) == 0.0
    assert accuracy_band(60.0)[0] == "success"
    assert accuracy_band(59.9)[0] == "warning"
    assert accuracy_band(29.9)[0] == "danger"
    # a clean trace that wandered off the line: accuracy decides
    ts, xs, ys = make_trace()
    m = compute_metrics(ts, xs, ys, [11.0] * len(ts), SP_NP)
    assert m["accuracy_status"] == "danger" and m["tremor_status"] == "success"
    assert m["status"] == "danger" and m["verdict_from"] == "accuracy"


def test_tremor_through_jitter_still_reads_danger():
    # The noise-aware cutoff must not hide a real tremor behind the jitter.
    ts, xs, ys = make_trace(duration=35.0, fps=20.0, noise=1.5,
                            tremor_amp=4.0, tremor_hz=5.0)
    m = compute_metrics(ts, xs, ys, [], SP_NP)
    assert m["status"] == "danger", m["sparc"]
    assert m["tremor_dominant_hz"] is not None
    assert abs(m["tremor_dominant_hz"] - 5.0) < 1.0


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


# ── Practice spiral coaching (core/spiral/practice.py) ──────────────────────

def test_practice_spiral_is_smaller_and_shares_the_centre():
    assert pr.arc_length(PRACTICE_SP) < pr.arc_length(SP)
    r_test = max(np.hypot(x - CENTER[0], y - CENTER[1]) for x, y in SP)
    r_prac = max(np.hypot(x - CENTER[0], y - CENTER[1]) for x, y in PRACTICE_SP)
    assert r_prac < r_test
    assert PRACTICE_SP[0] == SP[0] == tuple(CENTER)


def test_target_speed_traces_the_test_spiral_in_target_time():
    v = pr.target_speed_px_s(SP)
    assert abs(pr.arc_length(SP) / v - pr.TARGET_TRACE_S) < 1e-6
    assert pr.recommended_time_s(PRACTICE_SP, v) < pr.TARGET_TRACE_S


def test_pace_band_edges():
    t = 100.0
    assert pr.pace_band(None, t) is None
    assert pr.pace_band(100.0, t) == "good"
    assert pr.pace_band(61.0, t) == "good"
    assert pr.pace_band(139.0, t) == "good"
    assert pr.pace_band(55.0, t) == "slow"
    assert pr.pace_band(150.0, t) == "fast"


def test_progress_speed_needs_enough_history():
    assert pr.progress_speed([], 1.0) is None
    assert pr.progress_speed([(0.9, 0.0), (1.0, 10.0)], 1.0) is None
    hist = [(i / 30.0, 50.0 * i / 30.0) for i in range(61)]   # 50 px/s, 2 s
    v = pr.progress_speed(hist, 2.0)
    assert abs(v - 50.0) < 1e-6
    # progress never runs backwards, so a stalled hand reads as zero, not less
    stalled = [(i / 30.0, 40.0) for i in range(61)]
    assert pr.progress_speed(stalled, 2.0) == 0.0


def test_expected_index_starts_at_zero_and_is_monotonic():
    n, total, v = 600, 900.0, 90.0
    assert pr.expected_index(0.0, v, total, n) == 0
    idx = [pr.expected_index(t / 10.0, v, total, n) for t in range(150)]
    assert all(b >= a for a, b in zip(idx, idx[1:]))
    assert idx[-1] == n - 1                       # clamps at the rim
    assert pr.expected_index(5.0, v, total, n) == round(0.5 * (n - 1))


def test_coach_priority_line_then_pace_then_smoothness():
    assert pr.coach_message("good", False, "success")[0] == pr.MSG_OFF_LINE
    assert pr.coach_message(None, True, "danger")[0] == pr.MSG_START
    assert pr.coach_message("fast", True, "danger")[0] == pr.MSG_SLOWER
    assert pr.coach_message("slow", True, "danger")[0] == pr.MSG_FASTER
    assert pr.coach_message("good", True, "danger")[0] == pr.MSG_SMOOTHER
    msg, status = pr.coach_message("good", True, "success")
    assert msg == pr.MSG_GOOD and status == "success"


def test_practice_summary_takeaways():
    good = pr.practice_summary(10.0, 10.0, ["good"] * 5, [True] * 50)
    assert good["takeaway"] == pr.TAKE_GOOD and good["good_pace_pct"] == 100.0
    assert pr.practice_summary(25.0, 10.0, ["slow"], [True])["takeaway"]         == pr.TAKE_FASTER
    assert pr.practice_summary(5.0, 10.0, ["fast"], [True])["takeaway"]         == pr.TAKE_SLOWER
    off = pr.practice_summary(10.0, 10.0, ["good"], [False] * 6 + [True] * 4)
    assert off["takeaway"] == pr.TAKE_LINE
    empty = pr.practice_summary(10.0, 10.0, [None], [])
    assert empty["good_pace_pct"] is None and empty["on_line_pct"] is None


# ── Swept-angle progress (core/spiral/progress.py) ──────────────────────────

import math as _m

_TURNS, _N = 3.5, len(SP)
_GAP = 2 * _m.pi * B


def _pt(theta, dr=0.0):
    """Point at swept angle theta, pushed dr px radially outward."""
    r = B * theta + dr
    return CENTER[0] + r * _m.cos(theta), CENTER[1] - r * _m.sin(theta)


def _outside_centre(thetas, out):
    """Deviations outside the centre dead-zone, where the angle is defined."""
    from core.spiral.progress import ANGLE_MIN_RADIUS
    return [o[0] for th, o in zip(thetas, out) if B * th > ANGLE_MIN_RADIUS + 2]


def _run(thetas, drs=None, fps=30.0):
    tr = SpiralProgress(CENTER, B, _TURNS, _N)
    out = []
    for i, th in enumerate(thetas):
        x, y = _pt(th, drs[i] if drs else 0.0)
        out.append(tr.update(x, y, i / fps))
    return tr, out


def test_index_at_matches_the_resampled_template():
    tr = SpiralProgress(CENTER, B, _TURNS, _N)
    for frac in (0.1, 0.35, 0.6, 0.9):
        th = frac * _TURNS * 2 * _m.pi
        x, y = SP[tr.index_at(th)]
        ex, ey = _pt(th)
        assert _m.hypot(x - ex, y - ey) < 3.0


def test_clean_trace_reaches_the_end():
    thetas = np.linspace(0.0, _TURNS * 2 * _m.pi, 900)
    tr, out = _run(thetas)
    assert tr.progress >= 0.985
    assert tr.off_arm_frames == 0 and tr.glitch_frames == 0
    assert max(_outside_centre(thetas, out)) < 1.0   # deviation stays tiny


def test_drift_onto_next_arm_does_not_skip_a_layer():
    """Half-way round turn 2, drift a full gap outward and keep circling. The
    old nearest-point progress jumped a whole turn here; this must freeze."""
    t1 = np.linspace(0.0, 1.5 * 2 * _m.pi, 300)
    t2 = np.linspace(t1[-1], t1[-1] + 0.5 * 2 * _m.pi, 100)
    thetas = np.concatenate([t1, t2[1:]])
    drs = [0.0] * len(t1) + [min(1.0, i / 30) * _GAP for i in range(1, len(t2))]
    tr, out = _run(thetas, drs)
    frozen_at = SpiralProgress(CENTER, B, _TURNS, _N).index_at(t1[-1])
    assert tr.max_idx < frozen_at + 0.05 * _N    # held near where it left
    assert tr.off_arm_frames > 0
    # the old logic, for contrast: nearest template point to the last sample
    x, y = _pt(thetas[-1], drs[-1])
    old = int(np.argmin(np.hypot(SP_NP[:, 0] - x, SP_NP[:, 1] - y)))
    assert old > tr.max_idx + 0.15 * _N


def test_single_frame_teleport_is_a_glitch():
    thetas = list(np.linspace(0.0, 2 * 2 * _m.pi, 400))
    tr = SpiralProgress(CENTER, B, _TURNS, _N)
    for i, th in enumerate(thetas[:200]):
        tr.update(*_pt(th), i / 30.0)
    before = tr.max_idx
    ex, ey = _pt(thetas[199], 0.0)
    _, idx, _, glitch = tr.update(ex + 300.0, ey + 200.0, 200 / 30.0)
    assert glitch and idx == before and tr.glitch_frames == 1
    for i, th in enumerate(thetas[200:], start=201):
        tr.update(*_pt(th), i / 30.0)
    assert tr.index_at(thetas[-1]) - 2 <= tr.max_idx   # carries on normally


def test_hand_drop_mid_turn_resyncs_without_a_phantom_gap():
    """Hidden for a third of a turn: the angle swept out of view is recovered
    rather than leaving a permanent lag that reads as deviation."""
    thetas = np.linspace(0.0, 3.0 * 2 * _m.pi, 900)
    tr = SpiralProgress(CENTER, B, _TURNS, _N)
    devs = []
    for i, th in enumerate(thetas):
        if 400 <= i < 440:                       # hand out of frame
            if i == 400:
                tr.reset_angle()
            continue
        dev, *_ = tr.update(*_pt(th), i / 30.0)
        if i >= 440:
            devs.append(dev)
    assert max(devs) < 1.0
    assert tr.off_arm_frames == 0


def test_seed_uses_the_real_exit_direction():
    """Leaving the centre dead-zone off-angle must not bias the whole run: the
    seed snaps to the wrap of the real angle, so deviation stays tiny."""
    thetas = np.linspace(0.0, 2 * 2 * _m.pi, 600)
    tr, out = _run(thetas)
    assert max(_outside_centre(thetas, out)) < 1.0


def test_untrusted_stretch_keeps_the_angle_and_can_be_skipped():
    """Hand clipped for a 200-degree stretch of the bottom: nothing counts
    there, but the angle is followed, so progress resumes on the right arm
    rather than sticking (a reset would lose more than half a turn)."""
    thetas = np.linspace(0.0, 3.0 * 2 * _m.pi, 900)
    tr = SpiralProgress(CENTER, B, _TURNS, _N)
    hidden = range(500, 560)                     # ~200 degrees of sweep
    for i, th in enumerate(thetas):
        _, idx, _, _ = tr.update(*_pt(th), i / 30.0, trusted=i not in hidden)
        if i == 559:
            held = idx
    assert held == tr.index_at(thetas[499])      # frozen while untrusted
    assert tr.max_idx >= tr.index_at(thetas[-1]) - 2   # and carried on after
    assert tr.off_arm_frames == 0


def test_no_blackouts_scores_exactly_as_before():
    t, x, y = make_trace()
    a = compute_metrics(t, x, y, [], SP_NP)
    assert compute_metrics(t, x, y, [], SP_NP, blackouts=None) == a
    assert compute_metrics(t, x, y, [], SP_NP, blackouts=[]) == a
    assert "skipped_pct" not in a


def test_blackout_samples_are_dropped_and_reported():
    t, x, y = make_trace(duration=20.0)
    bo = [(8.0, 11.0)]
    m = compute_metrics(t, x, y, [], SP_NP, blackouts=bo)
    keep = [i for i, tt in enumerate(t) if not 8.0 <= tt <= 11.0]
    ref = compute_metrics([t[i] for i in keep], [x[i] for i in keep],
                          [y[i] for i in keep], [], SP_NP)
    assert m["sparc"] == ref["sparc"] and m["frames"] == ref["frames"]
    assert abs(m["skipped_pct"] - 15.0) < 0.5


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
