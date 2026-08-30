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

from core.gaze.calibrate import (GazeCalibrator, GazeMap, STAGES, STAGE_FRAMES,
                                 DEADBAND_MIN, DEADBAND_MAX)
from core.gaze.detector import (SaccadeEnvelope, SaccadeTrial, SettleGate,
                                TrialResult, MIN_LATENCY_MS, CONFIRM_MIN,
                                SETTLE_HOLD_S, SETTLE_SPREAD)
from core.gaze.fixation import (FixationAnalyzer, bcea, jitter_band,
                                JITTER_TYPICAL, JITTER_MONITOR, SETTLE_S)
from core.gaze.metrics import (compute_metrics, band, block_stats,
                               MIN_GAZE_RATIO, MIN_VALID_ANTI,
                               ERROR_TYPICAL_PCT)
from core.gaze.confidence import (block_quality, confidence, wilson_ci,
                                  SATURATION_TRIALS)
from core.gaze.tasks import TASKS
from core.gaze.openness import (OpennessGate, ABS_FLOOR, BLINK_FRAC,
                                NARROW_BASELINE, VERTICAL_FRAC)
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
    assert DEADBAND_MIN <= gm.deadband <= DEADBAND_MAX


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


# ── baseline-relative onset ──────────────────────────────────────────────────
def _offset_trial(target_dir, is_anti, deadband, onset_ms, move_dir, offset,
                  *, baseline=None, hold_s=1.0, jitter=0.0):
    """A trial whose gaze rests at `offset` rather than at a true zero — the
    ordinary case once the calibrated centre has drifted, or the eye has not
    quite come back from the last target."""
    t0 = 100.0
    trial = SaccadeTrial(t0, target_dir, deadband, is_anti, baseline=baseline)
    for i in range(int(hold_s * FPS)):
        t = t0 + i * DT
        wobble = jitter * (1 if i % 2 else -1)
        pos = offset + wobble
        if i * DT * 1000 >= onset_ms:
            pos = offset + move_dir * 0.9
        trial.update(t, pos)
    return trial.finalize()


def test_offset_start_still_scores_the_saccade():
    """The failure this rework exists for: the eye is parked well outside the
    deadband when the dot appears, then makes a clean, correct saccade. Against
    an absolute zero that was onset at 0 ms → 'anticipatory', and it was 21% of
    every trial in the recorded session history."""
    r = _offset_trial(target_dir=-1, is_anti=False, deadband=0.35,
                      onset_ms=200, move_dir=-1, offset=0.7)
    assert r.outcome == "correct"
    assert r.latency_ms >= MIN_LATENCY_MS
    assert abs(r.baseline - 0.7) < 0.01


def test_a_genuine_early_start_is_still_anticipatory():
    """Tolerance for a stale baseline must not become tolerance for jumping the
    gun: movement *away from the resting point* before 90 ms is still excluded."""
    r = _offset_trial(target_dir=-1, is_anti=False, deadband=0.35,
                      onset_ms=30, move_dir=-1, offset=0.7)
    assert r.outcome == "anticipatory"
    assert not r.valid


def test_baseline_falls_back_to_the_presaccadic_window():
    """No settle reading (the gate timed out) → the trial estimates its own
    baseline from the frames before MIN_LATENCY_MS, and an explicit baseline
    overrides that estimate."""
    fallback = _offset_trial(1, False, 0.35, 250, 1, offset=-0.5, baseline=None)
    assert abs(fallback.baseline + 0.5) < 0.01
    assert fallback.outcome == "correct"
    given = _offset_trial(1, False, 0.35, 250, 1, offset=-0.5, baseline=-0.5)
    assert given.baseline == -0.5
    assert given.outcome == "correct"


def test_a_still_eye_manufactures_no_saccade_at_the_floor():
    """The CONFIRM_MIN guard: even at the most forgiving threshold the engine
    will ever use, tracker wobble around a resting eye is not a response."""
    r = _offset_trial(1, False, CONFIRM_MIN, onset_ms=1e9, move_dir=1,
                      offset=-0.6, jitter=0.05)
    assert r.outcome == "no_response"


def test_onset_opens_below_confirm_but_needs_the_full_excursion():
    """Two-tier: a wobble that clears the onset threshold but never reaches the
    confirm threshold is not a saccade, while one that reaches it is — and its
    latency is stamped where the movement began, not where it was confirmed."""
    # 0.4 · 0.9 = 0.36: past the 0.20 onset threshold, short of the 0.40
    # confirm threshold, so it never becomes a saccade.
    small = _offset_trial(1, False, 0.40, 200, 0.4, offset=0.0)
    assert small.outcome == "no_response"
    full = _offset_trial(1, False, 0.40, 200, 1, offset=0.0)
    assert full.outcome == "correct"
    assert abs(full.latency_ms - 200) < 2 * (1000 * DT)


def test_envelope_follows_a_shrinking_excursion_down_to_the_floor():
    """The amplitude a person produces is not constant across a block; a frozen
    threshold read one recorded anti block (peaks 0.3–0.7) as 18 no-responses."""
    env = SaccadeEnvelope(seed=0.40)
    assert env.confirm_threshold() == 0.40          # seed until it has evidence
    for _ in range(SaccadeEnvelope.MIN_TRIALS):
        env.observe(_offset_trial(1, False, 0.40, 200, 1, offset=0.0))
    shrunk = env.confirm_threshold()
    assert CONFIRM_MIN <= shrunk < 0.40, shrunk

    floored = SaccadeEnvelope(seed=0.40)
    for _ in range(6):
        floored.observe(TrialResult(1, 1, 200.0, "correct", False, peak=0.20))
    assert floored.confirm_threshold() == CONFIRM_MIN   # 0.40 · 0.20 < the floor


def _feed_settle(pos_fn, dur_s=1.2):
    gate = SettleGate()
    t = 0.0
    for i in range(int(dur_s * FPS)):
        t = i * DT
        gate.update(t, pos_fn(t))
    return gate


def test_gate_settles_on_a_steady_eye_wherever_it_is_resting():
    """It tests steadiness, never nearness to zero. An eye resting calmly on
    the cross whose map has drifted to -0.7 has to pass, because that offset is
    precisely what the baseline exists to absorb - gating on |pos| would stall
    the run exactly when drift is worst."""
    gate = _feed_settle(lambda t: -0.7 + 0.01 * (1 if int(t * 100) % 2 else -1))
    assert gate.settled
    assert abs(gate.baseline() + 0.7) < 0.05


def test_gate_does_not_settle_on_a_wandering_eye_and_offers_no_baseline():
    """A gate that timed out must answer None, not the median of a moving eye:
    the trial's own pre-saccadic window is the better estimate, and a wandering
    median would be worse than no answer."""
    gate = _feed_settle(lambda t: -1.0 + 1.6 * t)      # sweeping across the range
    assert not gate.settled
    assert gate.baseline() is None


def test_gate_is_not_latched_by_an_early_settle():
    """Steady for a moment, then drifting: the gate must report the eye as it
    is now, not hand over the reading it had a second ago."""
    gate = _feed_settle(lambda t: 0.0 if t < 0.5 else (t - 0.5) * 1.5, dur_s=1.2)
    assert not gate.settled
    assert gate.baseline() is None


def test_gate_accepts_a_new_resting_point():
    """The flip side: an eye that moves and then genuinely comes to rest
    somewhere else is resting *there*, and that is the baseline to hand over."""
    gate = _feed_settle(lambda t: 0.0 if t < 0.5 else 0.9, dur_s=1.2)
    assert gate.settled
    assert abs(gate.baseline() - 0.9) < 0.01


def test_gate_treats_a_blink_as_not_steady():
    gate = SettleGate()
    for i in range(int(1.0 * FPS)):
        t = i * DT
        gate.update(t, 0.1)
    assert gate.settled
    gate.update(1.0, None)
    assert not gate.settled and gate.baseline() is None


def test_envelope_never_loosens_past_calibration():
    """It may only make the test more forgiving than calibration, never less —
    a big warm-up excursion must not raise the bar on the trials that follow."""
    env = SaccadeEnvelope(seed=0.25)
    for _ in range(6):
        env.observe(TrialResult(1, 1, 200.0, "correct", False, peak=2.0))
    assert env.confirm_threshold() == 0.25


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

# ── adaptive lid-openness gate ────────────────────────────────────────────
def _feed_gate(gate, values, t0=100.0):
    """Feed a sequence of per-frame openness values; return the last state."""
    st = None
    for i, v in enumerate(values):
        st = gate.update(t0 + i * DT, v)
    return st


def test_narrow_eyes_stay_open():
    """The bug this gate exists for: a narrow palpebral fissure sits below the
    old fixed 0.14 threshold, and every frame of the run was thrown away."""
    gate = OpennessGate()
    st = _feed_gate(gate, [0.12] * 120)
    assert st.open, "a steadily narrow eye must not read as a blink"
    assert st.vertical_ok
    assert st.narrow, "it should still be flagged as a narrow aperture"
    assert st.open_frac > 0.9


def test_wide_eyes_open_and_not_flagged_narrow():
    gate = OpennessGate()
    st = _feed_gate(gate, [0.32] * 120)
    assert st.open and st.vertical_ok
    assert not st.narrow
    assert st.baseline > NARROW_BASELINE


def test_blink_detected_for_narrow_and_wide_eyes():
    """A blink is a collapse relative to that person's own baseline, so it is
    caught at both ends of the anatomical range."""
    for base in (0.12, 0.32):
        gate = OpennessGate()
        _feed_gate(gate, [base] * 120)
        t = 100.0 + 120 * DT
        st = gate.update(t, base * 0.2)          # mid-blink
        assert not st.open, f"blink missed at baseline {base}"
        st = gate.update(t + DT, 0.005)          # fully shut
        assert not st.open


def test_partial_squint_blocks_vertical_but_not_horizontal():
    """A lowered lid crops the iris from above: iris-y goes first, and the
    horizontal saccade signal should survive it."""
    gate = OpennessGate()
    _feed_gate(gate, [0.30] * 120)
    t = 100.0 + 120 * DT
    frac = (BLINK_FRAC + VERTICAL_FRAC) / 2
    st = gate.update(t, 0.30 * frac)
    assert st.open, "horizontal gaze should survive a partial squint"
    assert not st.vertical_ok, "the vertical proxy should not"


def test_short_squint_stays_closed_long_one_is_adopted():
    """The baseline must not chase a blink or a brief squint. A squint that
    holds for several seconds *is* adopted — the person's new resting aperture
    should be measured noisily rather than produce nothing for the rest of the
    run — but the vertical proxy stays gated and the frames stay counted."""
    gate = OpennessGate()
    _feed_gate(gate, [0.30] * 120)
    t1 = 100.0 + 120 * DT
    st = _feed_gate(gate, [0.30 * 0.4] * 60, t0=t1)          # 1 s
    assert not st.open, "a 1 s squint must still read as closed"
    st = _feed_gate(gate, [0.30 * 0.4] * 480, t0=t1 + 60 * DT)   # 8 s more
    assert st.open, "a held aperture should be adopted rather than blank the run"
    assert st.baseline < 0.30


def test_baseline_rises_quickly_when_eyes_open():
    gate = OpennessGate()
    st = _feed_gate(gate, [0.30] * 10)
    assert st.open and st.open_frac > 0.9, "no warm-up gap at the start"


def test_absolute_floor_catches_a_shut_eye_from_the_first_frame():
    """Starting mid-blink, the baseline has nothing to compare against, so the
    absolute floor has to carry it."""
    gate = OpennessGate()
    st = gate.update(100.0, ABS_FLOOR * 0.5)
    assert not st.open


def test_low_gaze_ratio_names_the_eyelids_not_the_framing():
    trials = [_feed_trial(1, True, 0.3, 200, -1) for _ in range(4)]
    out = compute_metrics([], trials, face_visible_ratio=1.0,
                          gaze_valid_ratio=MIN_GAZE_RATIO - 0.1)
    assert not out["scoreable"]
    assert "eyes could only be read" in out["reason"]
    assert out["gaze_valid_ratio"] == round(MIN_GAZE_RATIO - 0.1, 3)


# ── confidence + the lowered floor ────────────────────────────────────────
def _anti(n_correct, n_error=0, n_antic=0, n_lost=0):
    """A finished anti block with the given outcome mix."""
    def T(outcome):
        return _feed_trial(1, True, 0.3, 200,
                           -1 if outcome == "correct" else 1,
                           missing=(outcome == "lost"))
    trials = []
    trials += [_feed_trial(1, True, 0.3, 200, -1) for _ in range(n_correct)]
    trials += [_feed_trial(1, True, 0.3, 200, 1) for _ in range(n_error)]
    trials += [_feed_trial(1, True, 0.3, 40, -1) for _ in range(n_antic)]
    trials += [_feed_trial(1, True, 0.3, 200, -1, missing=True)
               for _ in range(n_lost)]
    return trials


def test_wilson_interval_survives_a_perfect_score():
    """Wald collapses to zero width at p=0, and 0 errors of 15 is the common
    healthy result — the interval has to keep an honest upper bound."""
    lo, hi = wilson_ci(0, 15)
    assert lo == 0.0
    assert 15 < hi < 30, hi
    lo, hi = wilson_ci(3, 15)
    assert lo < 20.0 < hi, "3/15 sits on the band edge; the CI must span it"
    assert wilson_ci(0, 0) is None


def test_wider_blocks_give_tighter_intervals():
    narrow = wilson_ci(3, 15)
    wide = wilson_ci(12, 60)          # same 20% rate, four times the trials
    assert (wide[1] - wide[0]) < (narrow[1] - narrow[0])


def test_six_valid_anti_trials_score_and_five_refuse():
    """The tapping floor, ported: a thin run is reported with its confidence
    rather than thrown away after three minutes of the patient's time."""
    out = compute_metrics([], _anti(4, 2))
    assert out["scoreable"], out["reason"]
    assert abs(out["error_rate_pct"] - 2 / 6 * 100) < 1e-9
    assert out["confidence_level"] == "low", out["confidence_pct"]
    thin = compute_metrics([], _anti(3, 2))
    assert not thin["scoreable"]
    assert str(MIN_VALID_ANTI) in thin["reason"]


def test_anticipation_gets_its_own_reason_not_the_generic_one():
    out = compute_metrics([], _anti(2, 0, n_antic=12))
    assert not out["scoreable"]
    assert "started before the dot" in out["reason"]
    assert "valid anti-saccade trials" not in out["reason"]


def test_heavy_anticipation_costs_confidence_not_the_run():
    """The whole point of the change: an anticipator gets a scored run whose
    confidence says how compromised it is."""
    out = compute_metrics([], _anti(8, 2, n_antic=5), gaze_valid_ratio=0.95)
    assert out["scoreable"]
    assert out["confidence_pct"] < 60, out["confidence_pct"]
    assert any("started before the dot" in r
               for r in out["confidence_reasons"])
    assert abs(out["anticipatory_rate_pct"] - 100 * 5 / 15) < 1e-9


def test_clean_full_block_is_high_confidence():
    out = compute_metrics([], _anti(14, 1), gaze_valid_ratio=0.95)
    assert out["scoreable"]
    assert out["confidence_pct"] >= 75, out["confidence_pct"]
    assert out["confidence_level"] == "high"


def test_confidence_ranks_recordings_not_results():
    """A clean block scores the same whether the patient erred a lot or not —
    the error bar carries that story, and folding it into the score would
    relabel every elevated result as untrustworthy."""
    clean_low = compute_metrics([], _anti(15, 0), gaze_valid_ratio=0.95)
    clean_high = compute_metrics([], _anti(9, 6), gaze_valid_ratio=0.95)
    assert clean_low["confidence_pct"] == clean_high["confidence_pct"]
    assert (clean_high["error_ci_high_pct"] - clean_high["error_ci_low_pct"]
            > clean_low["error_ci_high_pct"] - clean_low["error_ci_low_pct"])


def test_band_edge_flags_the_boundary_case():
    edge = compute_metrics([], _anti(12, 3), gaze_valid_ratio=0.95)
    assert edge["error_rate_pct"] == 20.0
    assert edge["band_edge"] == 1, "3/15 lands exactly on the 20% edge"
    # A perfect block is nowhere near the edge on a 1-SE view, even though
    # its 95% interval reaches past 20% — which is why the flag is not tested
    # against the interval the screen reports.
    clear = compute_metrics([], _anti(15, 0), gaze_valid_ratio=0.95)
    assert clear["band_edge"] == 0
    assert clear["error_ci_high_pct"] > ERROR_TYPICAL_PCT


def test_quality_factors_move_independently():
    base = dict(support=1.0, excluded_frac=0.0, gaze_valid_ratio=0.95)
    good = block_quality(**base)
    assert good["quality_pct"] == 100.0
    assert block_quality(**{**base, "gaze_valid_ratio": 0.80})["quality_pct"] \
        < good["quality_pct"]
    assert block_quality(**{**base, "excluded_frac": 0.2})["quality_pct"] \
        < good["quality_pct"]
    assert block_quality(**{**base, "support": 0.5})["quality_pct"] \
        < good["quality_pct"]


def test_blinking_alone_does_not_cost_tracking_marks():
    """gaze_valid_ratio cannot reach 1.0 — involuntary blinks eat ~4% of
    frames — so a normal run must still read as fully tracked."""
    assert block_quality(support=1.0, gaze_valid_ratio=0.94)["quality_pct"] \
        == 100.0


def test_confidence_saturates_at_the_block_length():
    full = confidence(n_valid=SATURATION_TRIALS, errors=2, band_width_pct=20.0,
                      attempted=SATURATION_TRIALS, gaze_valid_ratio=0.95)
    over = confidence(n_valid=SATURATION_TRIALS + 5, errors=3,
                      band_width_pct=20.0, attempted=SATURATION_TRIALS + 5,
                      gaze_valid_ratio=0.95)
    assert full["confidence_pct"] == over["confidence_pct"] == 100.0


# ── block extension ───────────────────────────────────────────────────────
def test_both_blocks_extend_only_when_short_of_usable_trials():
    for key in ("pro", "anti"):
        task = TASKS[key]
        assert task.extends, key
        assert task.target_valid < task.n_trials < task.max_trials, key


def test_replacement_segment_stays_count_balanced():
    """Two balanced segments, not one long schedule truncated early: any
    stopping point then stays within ±1 of balanced."""
    import random
    task = TASKS["anti"]
    for seed in range(20):
        rng = random.Random(seed)
        dirs = build_directions(task.n_trials, rng)
        dirs += build_directions(task.max_trials - task.n_trials, rng)
        assert len(dirs) == task.max_trials
        # Each segment is count-balanced to ±1, and a partial second segment
        # can lean by at most the 3-in-a-row cap build_directions allows — so
        # any stopping point stays within ±4 of even, on 20 trials.
        for stop in range(task.n_trials, task.max_trials + 1):
            assert abs(sum(dirs[:stop])) <= 4, (seed, stop, sum(dirs[:stop]))


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
