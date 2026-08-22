"""
Unit tests for the gaze engine (OCULOMOTOR_TEST_PLAN.md §7 phase 2): pure
logic exercised against synthetic gaze traces — no camera, no MediaPipe.

Run:  python -m pytest screening_tests/tests/test_gaze.py
 or:  python screening_tests/tests/test_gaze.py   (self-runs without pytest)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.gaze.calibrate import GazeCalibrator, GazeMap, STAGES, STAGE_FRAMES
from core.gaze.detector import SaccadeTrial, MIN_LATENCY_MS
from core.gaze.fixation import (FixationAnalyzer, bcea, jitter_band,
                                JITTER_TYPICAL, JITTER_MONITOR, SETTLE_S)
from core.gaze.metrics import compute_metrics, band, block_stats
from core.gaze.tasks import build_directions


FPS = 60.0
DT = 1.0 / FPS


def _feed_trial(target_dir, is_anti, deadband, onset_ms, move_dir,
                *, hold_s=1.0, correct_after_ms=None, missing=False):
    """Build and finalize one SaccadeTrial from a synthetic gaze trace.

    move_dir is the sign the gaze moves to after `onset_ms`; correct_after_ms,
    if set, is when it then crosses to the opposite (correct) side.
    """
    t0 = 100.0
    trial = SaccadeTrial(t0, target_dir, deadband, is_anti)
    n = int(hold_s * FPS)
    for i in range(n):
        t = t0 + i * DT
        ms = i * DT * 1000
        if missing:
            pos = None
        elif correct_after_ms is not None and ms >= correct_after_ms:
            pos = -move_dir * 0.9
        elif ms >= onset_ms:
            pos = move_dir * 0.9
        else:
            pos = 0.0
        trial.update(t, pos)
    return trial.finalize()


# ── calibration ────────────────────────────────────────────────────────────

def test_calibration_maps_and_deadband():
    ratios = {"center": 0.5, "left": 0.35, "right": 0.65}
    cal = GazeCalibrator(0.0)
    t = 0.0
    while not (cal.done or cal.failed):
        t += DT
        cal.update(t, ratios[cal.stage] + (0.001 if int(t * 100) % 2 else -0.001))
        assert t < 60, "calibration never completed"
    assert cal.done and not cal.failed
    gm = cal.result()
    assert abs(gm.position(0.65) - 1.0) < 0.05      # right target → +1
    assert abs(gm.position(0.35) + 1.0) < 0.05      # left target → −1
    assert abs(gm.position(0.5)) < 0.05             # center → 0
    assert 0.30 <= gm.deadband <= 0.55


def test_calibration_fails_on_tiny_movement():
    cal = GazeCalibrator(0.0)
    t = 0.0
    while not (cal.done or cal.failed):
        t += DT
        cal.update(t, 0.5)          # no separation between center/left/right
        assert t < 60
    assert cal.failed and cal.fail_reason


def test_settle_ignores_early_samples():
    # samples inside the settle window must not count toward a stage
    cal = GazeCalibrator(0.0)
    cal.update(0.1, 0.5)            # within SETTLE_S → ignored
    assert cal.stage_progress == 0.0


# ── deadband / position mapping ──────────────────────────────────────────────

def test_gazemap_position_clamped_and_signed():
    gm = GazeMap(center=0.5, left=0.35, right=0.65, deadband=0.35)
    assert gm.position(0.8) == 1.5          # beyond right target, clamped
    assert gm.position(0.2) == -1.5
    assert gm.position(0.575) > 0           # halfway to right


# ── saccade detection ────────────────────────────────────────────────────────

def test_prosaccade_correct():
    r = _feed_trial(target_dir=1, is_anti=False, deadband=0.35,
                    onset_ms=200, move_dir=1)
    assert r.outcome == "correct"
    assert r.direction == 1
    assert 150 < r.latency_ms < 260


def test_prosaccade_error_wrong_way():
    r = _feed_trial(target_dir=1, is_anti=False, deadband=0.35,
                    onset_ms=200, move_dir=-1)
    assert r.outcome == "error_uncorrected"


def test_antisaccade_correct_looks_away():
    # target right (+1), gaze goes left (−1) = correct anti
    r = _feed_trial(target_dir=1, is_anti=True, deadband=0.35,
                    onset_ms=250, move_dir=-1)
    assert r.outcome == "correct"


def test_antisaccade_uncorrected_error():
    # target right, gaze goes right (toward) and stays = uncorrected error
    r = _feed_trial(target_dir=1, is_anti=True, deadband=0.35,
                    onset_ms=250, move_dir=1)
    assert r.outcome == "error_uncorrected"
    assert r.is_error and not r.corrected


def test_antisaccade_corrected_error():
    # toward first, then crosses to correct side → corrected error
    r = _feed_trial(target_dir=1, is_anti=True, deadband=0.35,
                    onset_ms=200, move_dir=1, correct_after_ms=500)
    assert r.outcome == "error_corrected"
    assert r.is_error and r.corrected


def test_anticipatory_excluded():
    r = _feed_trial(target_dir=1, is_anti=False, deadband=0.35,
                    onset_ms=30, move_dir=1)   # < 90 ms
    assert r.outcome == "anticipatory"
    assert not r.valid


def test_no_response_excluded():
    r = _feed_trial(target_dir=1, is_anti=False, deadband=0.35,
                    onset_ms=9999, move_dir=1)  # never moves
    assert r.outcome == "no_response"
    assert not r.valid


def test_face_lost_excluded():
    r = _feed_trial(target_dir=1, is_anti=False, deadband=0.35,
                    onset_ms=200, move_dir=1, missing=True)
    assert r.outcome == "face_lost"
    assert not r.valid


def test_debounce_rejects_single_frame_noise():
    t0 = 100.0
    trial = SaccadeTrial(t0, 1, 0.35, is_anti=False)
    for i in range(60):
        t = t0 + i * DT
        # single-frame spike out of deadband at frame 10, else centered
        pos = 0.9 if i == 10 else 0.0
        trial.update(t, pos)
    r = trial.finalize()
    assert r.outcome == "no_response"   # one-frame spike must not trigger onset


# ── run metrics ──────────────────────────────────────────────────────────────

def _valid_correct(is_anti, latency):
    move = -1 if is_anti else 1
    return _feed_trial(1, is_anti, 0.35, latency, move)


def _valid_error(is_anti):
    move = 1  # toward target
    return _feed_trial(1, is_anti, 0.35, 180, move)


def test_metrics_scoreable_and_error_rate():
    pro = [_valid_correct(False, 220) for _ in range(16)]
    # 24 anti: 6 errors → 25%
    anti = [_valid_error(True) for _ in range(6)] + \
           [_valid_correct(True, 300) for _ in range(18)]
    m = compute_metrics(pro, anti, face_visible_ratio=1.0)
    assert m["scoreable"]
    assert abs(m["error_rate_pct"] - 25.0) < 0.01
    assert m["status"] == "warning"      # 20–40% band
    # anti latency (300) > pro latency (220): positive difference
    assert m["anti_minus_pro_ms"] > 0


def test_metrics_unscoreable_too_few_valid():
    pro = [_valid_correct(False, 220) for _ in range(16)]
    anti = [_valid_correct(True, 300) for _ in range(5)]  # < MIN_VALID_ANTI
    m = compute_metrics(pro, anti, face_visible_ratio=1.0)
    assert not m["scoreable"]
    assert "valid anti-saccade" in m["reason"]


def test_metrics_unscoreable_face_lost():
    pro = [_valid_correct(False, 220) for _ in range(16)]
    anti = [_feed_trial(1, True, 0.35, 200, -1, missing=True) for _ in range(24)]
    m = compute_metrics(pro, anti, face_visible_ratio=0.3)
    assert not m["scoreable"]
    assert "face" in m["reason"].lower()


def test_band_thresholds():
    assert band(10)[0] == "success"
    assert band(30)[0] == "warning"
    assert band(50)[0] == "danger"


# ── fixation stability ───────────────────────────────────────────────────────

def _feed_fixation(pos_fn, *, deadband=0.35, dur_s=4.0, rxy_fn=None):
    """Feed a synthetic fixation hold at 60 fps. pos_fn(i)->pos|None; rxy_fn,
    if given, provides the raw (rx, ry) iris cloud for BCEA."""
    t0 = 100.0
    fa = FixationAnalyzer(t0, deadband)
    for i in range(int(dur_s * FPS)):
        pos = pos_fn(i)
        rx, ry = (rxy_fn(i) if (rxy_fn and pos is not None) else (None, None))
        fa.update(t0 + i * DT, pos, rx, ry)
    return fa.finalize()


def test_fixation_steady_is_scoreable_and_low_jitter():
    r = _feed_fixation(lambda i: 0.01 * (1 if i % 2 else -1),
                       rxy_fn=lambda i: (0.5 + 0.001 * (i % 2), 0.001 * (i % 3)))
    assert r.scoreable
    assert r.rms_jitter < JITTER_TYPICAL
    assert r.status == "success"
    assert r.intrusion_count == 0
    assert r.bcea is not None and r.bcea >= 0.0


def test_fixation_jitter_bands():
    mild = _feed_fixation(lambda i: 0.12 * (1 if i % 2 else -1))
    assert mild.scoreable and mild.status == "warning"     # 0.08–0.16
    bad = _feed_fixation(lambda i: 0.24 * (1 if i % 2 else -1))
    assert bad.scoreable and bad.status == "danger"        # > 0.16, < deadband


def test_fixation_counts_intrusions():
    def pf(i):
        for start in (60, 120, 180):
            if start <= i < start + 5:      # 5-frame excursion beyond deadband
                return 0.9
        return 0.0
    r = _feed_fixation(pf)
    assert r.scoreable
    assert r.intrusion_count == 3           # each debounced excursion counts once
    assert r.intrusion_rate_per_min > 0


def test_fixation_single_frame_spike_not_an_intrusion():
    r = _feed_fixation(lambda i: 0.9 if i == 100 else 0.0)
    assert r.intrusion_count == 0           # one frame is below the debounce


def test_fixation_unscoreable_when_untracked():
    r = _feed_fixation(lambda i: None)
    assert not r.scoreable and r.reason
    assert r.rms_jitter is None


def test_bcea_grows_with_spread():
    import random
    rng = random.Random(0)
    tight = ([0.5 + rng.gauss(0, 0.001) for _ in range(200)],
             [0.0 + rng.gauss(0, 0.001) for _ in range(200)])
    wide = ([0.5 + rng.gauss(0, 0.01) for _ in range(200)],
            [0.0 + rng.gauss(0, 0.01) for _ in range(200)])
    assert bcea(*wide) > bcea(*tight) > 0.0
    assert bcea([0.5] * 200, [0.0] * 200) == 0.0     # zero spread → zero area


def test_jitter_band_thresholds():
    assert jitter_band(0.04)[0] == "success"
    assert jitter_band(0.12)[0] == "warning"
    assert jitter_band(0.20)[0] == "danger"


# ── task schedule ────────────────────────────────────────────────────────────

def test_build_directions_balanced_no_long_runs():
    import random
    for seed in range(20):
        dirs = build_directions(24, random.Random(seed))
        assert len(dirs) == 24
        assert abs(sum(dirs)) <= 1           # count-balanced (±1 for odd n)
        run = longest = 1
        for i in range(1, len(dirs)):
            run = run + 1 if dirs[i] == dirs[i - 1] else 1
            longest = max(longest, run)
        assert longest <= 3, f"seed {seed} had a run of {longest}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
