"""
Unit tests for the walking test's seated tier (docs/tests/GAIT_TEST_PLAN.md
§11, stage V0): leg agility and sit-to-stand scored on synthetic signals with
known answers. No camera, no model.

A stamping leg is a knee lift of |sin| shape at a known rate, with tracker
noise; a sit-to-stand is the stand index going 0 -> 1 -> 0 on a known
schedule. The frame rate is 16 fps on purpose -- what the camera tests
actually get today.

Run:  python -m pytest screening_tests/tests/test_gait.py
 or:  python screening_tests/tests/test_gait.py   (self-runs without pytest)
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.gait import body, seated
from core.gait import metrics as gm
from core.gait.phases import BLOCKS, SEATED_ORDER

FPS = 16.0


def _frames(duration_s: float, fps: float = FPS):
    n = int(duration_s * fps)
    return [i / fps for i in range(n)]


def _stamp_leg(rate_hz=2.5, lift=0.25, fade=0.0, noise=0.01, duration=10.0,
               seed=3, fps=FPS):
    """Feed a synthetic stamping leg through LegRecorder; return it."""
    rng = random.Random(seed)
    rec = seated.LegRecorder()
    for t in _frames(duration, fps):
        amp = lift * (1.0 - fade * t / duration)
        d = amp * abs(math.sin(math.pi * rate_hz * t)) + rng.gauss(0, noise)
        rec.update(t, d)
    return rec


# ── Leg agility ────────────────────────────────────────────────────────────

def test_stamps_counted_at_known_rate():
    rec = _stamp_leg(rate_hz=2.5)
    cell = seated.analyse_leg(rec.stamps, rec.series)
    assert cell["scored"], cell
    # 2.5 Hz for 10 s is 25 stamps; allow the edges a stamp either way
    assert 23 <= cell["n_stamps"] <= 26, cell["n_stamps"]
    assert abs(cell["rate_hz"] - 2.5) < 0.15, cell["rate_hz"]
    assert cell["cv_pct"] < 12, cell["cv_pct"]


def test_lift_is_reported_in_percent_of_thigh():
    rec = _stamp_leg(lift=0.30, noise=0.0)
    cell = seated.analyse_leg(rec.stamps, rec.series)
    # the detector smooths (EMA) and 16 fps misses the exact peak
    assert 20 <= cell["amp_pct"] <= 31, cell["amp_pct"]


def test_fading_lift_shows_as_decrement():
    steady = seated.analyse_leg(*_attrs(_stamp_leg(fade=0.0, noise=0.0)))
    fading = seated.analyse_leg(*_attrs(_stamp_leg(fade=0.6, noise=0.0)))
    assert fading["scored"], fading
    assert fading["amp_decrement_pct"] < -25, fading["amp_decrement_pct"]
    assert abs(steady["amp_decrement_pct"]) < 10, steady["amp_decrement_pct"]


def test_fading_lift_is_still_counted():
    """The adaptive envelope is why this reuses TapDetector: a lift that
    shrinks to a third must not stop being counted halfway through."""
    rec = _stamp_leg(fade=0.65, noise=0.005)
    assert rec.stamps[-1] > 8.5, rec.stamps[-3:]


def test_still_leg_scores_nothing():
    rec = _stamp_leg(lift=0.0, noise=0.01)
    cell = seated.analyse_leg(rec.stamps, rec.series)
    assert not cell["scored"]
    assert cell["n_stamps"] < seated.MIN_STAMPS
    assert cell["reason"]


def test_interval_across_a_blackout_is_dropped():
    rec = _stamp_leg(rate_hz=2.0, noise=0.0)
    clean = seated.analyse_leg(rec.stamps, rec.series)
    a, b = rec.stamps[5], rec.stamps[6]
    cut = seated.analyse_leg(rec.stamps, rec.series, blackouts=[(a + 0.01, b - 0.01)])
    assert cut["intervals"] == clean["intervals"] - 1


def _attrs(rec):
    return rec.stamps, rec.series


def test_knee_lift_geometry():
    # image y grows downward: a knee 30 px above its rest, thigh 120 px
    assert abs(seated.knee_lift(270.0, 300.0, 120.0) - 0.25) < 1e-9
    assert seated.knee_lift(300.0, 300.0, 0.0) is None


# ── Sit-to-stand ───────────────────────────────────────────────────────────

def _sts(cycles, t_rise=1.0, t_up=0.6, t_down=1.0, t_sit=0.6, lead=0.8,
         hands_on=(), fail_at=None, fps=FPS):
    """Feed StandCounter a stand index built from `cycles` repetitions.
    Each repetition: rise, stand, lower, sit. `fail_at` inserts one aborted
    rise (peaks at 0.45) before that repetition."""
    sc = seated.StandCounter(t0=0.0)
    segs = [("seat", lead, 0.0, 0.0)]
    for i in range(cycles):
        if fail_at == i:
            segs += [("ramp", 0.5, 0.0, 0.45), ("ramp", 0.5, 0.45, 0.0),
                     ("seat", 0.4, 0.0, 0.0)]
        segs += [("ramp", t_rise, 0.0, 1.0), ("seat", t_up, 1.0, 1.0),
                 ("ramp", t_down, 1.0, 0.0), ("seat", t_sit, 0.0, 0.0)]
    t = 0.0
    rep = -1
    for kind, dur, a, b in segs:
        if kind == "ramp" and a == 0.0 and b == 1.0:
            rep += 1
        n = max(1, int(dur * fps))
        for k in range(n):
            s = a + (b - a) * (k / n)
            sc.update(t, s, lean=30.0 if 0.1 < s < 0.9 else 5.0,
                      hands=rep in hands_on and kind == "ramp")
            t += 1.0 / fps
    return sc


def test_five_stands_timed_from_the_beep():
    sc = _sts(5)
    assert sc.n_stands == 5 and sc.done
    cell = seated.analyse_sts(sc)
    assert cell["completed"]
    # whole frames: the 0.8 s lead is 12, each cycle 16+9+16+9 = 50, and the
    # fifth rise crosses STAND_AT on its 12th frame
    expected = (12 + 4 * 50 + 12) / FPS
    assert abs(cell["sts5_s"] - expected) < 1e-6, (cell["sts5_s"], expected)
    assert cell["sts5_sit_s"] > cell["sts5_s"]
    assert cell["failed_attempts"] == 0
    assert cell["hands_used"] == 0


def test_failed_attempt_is_counted_not_timed_as_a_stand():
    sc = _sts(5, fail_at=2)
    cell = seated.analyse_sts(sc)
    assert cell["n_stands"] == 5
    assert cell["failed_attempts"] == 1


def test_shifting_in_the_seat_is_not_an_attempt():
    sc = seated.StandCounter(0.0)
    for i in range(40):
        t = i / FPS
        sc.update(t, 0.2 * abs(math.sin(t * 3)))     # peaks 0.2 < ATTEMPT_MIN
    assert sc.failed == 0 and sc.n_stands == 0


def test_hands_used_on_the_rises_they_were_used():
    cell = seated.analyse_sts(_sts(5, hands_on=(0, 3)))
    assert cell["hands_used"] == 2


def test_four_stands_is_not_completed():
    cell = seated.analyse_sts(_sts(4))
    assert not cell["completed"] and "sts5_s" not in cell
    assert gm.band(None, False)[0] == "warning"


def test_no_stand_seen_is_unscored():
    cell = seated.analyse_sts(seated.StandCounter(0.0))
    assert not cell["scored"] and cell["reason"]


def test_stand_index_geometry():
    thigh = 100.0
    # seated with the knee 10 px above the hip (a low chair): offset -10
    assert abs(seated.stand_index(300, 290, thigh, -10.0)) < 1e-9
    # standing: knee a full thigh below the hip
    assert abs(seated.stand_index(200, 300, thigh, -10.0) - 1.0) < 1e-9
    # a degenerate reference is refused rather than divided by
    assert seated.stand_index(200, 300, thigh, 90.0) is None


def test_hands_low_line():
    # shoulder at 100, hip at 300: halfway line at 200
    assert not seated.hands_low([150, 170], 100, 300)      # arms crossed
    assert seated.hands_low([150, 280], 100, 300)          # one hand on the thigh
    assert not seated.hands_low([None, 150], 100, 300)


# ── Body / sides ───────────────────────────────────────────────────────────

def _pose(right_wrist_y=400.0, left_wrist_y=400.0):
    pts = [(300.0, 300.0)] * 33
    pts[body.NOSE] = (300.0, 100.0)
    pts[16] = (300.0, right_wrist_y)
    pts[15] = (300.0, left_wrist_y)
    pts[11], pts[12] = (290.0, 150.0), (310.0, 150.0)
    pts[23], pts[24] = (290.0, 300.0), (310.0, 300.0)
    return pts


def test_raised_side_names_the_model_label():
    assert body.raised_side(_pose(right_wrist_y=50)) == "right"
    assert body.raised_side(_pose(left_wrist_y=50)) == "left"
    assert body.raised_side(_pose(50, 50)) is None           # both up: ambiguous
    assert body.raised_side(_pose()) is None


def test_side_map_swaps_every_joint():
    straight, swapped = body.SideMap(False), body.SideMap(True)
    assert straight.idx("right", "knee") == 26
    assert swapped.idx("right", "knee") == 25
    assert swapped.person_side("left") == "right"
    assert not body.SideMap().checked and swapped.checked


def test_trunk_lean_upright_and_bent():
    p = _pose()
    assert body.trunk_lean_deg(p) < 1.0
    p[11], p[12] = (440.0, 160.0), (440.0, 160.0)            # shoulders 150 px ahead
    assert 40 < body.trunk_lean_deg(p) < 50


# ── Scoring ────────────────────────────────────────────────────────────────

def _cells(r_rate=2.5, l_rate=2.5, r_lift=0.25, l_lift=0.25, sts=5):
    legs = {"right": seated.analyse_leg(*_attrs(_stamp_leg(r_rate, r_lift))),
            "left": seated.analyse_leg(*_attrs(_stamp_leg(l_rate, l_lift)))}
    # a brisk healthy pace: ~2.2 s a repetition, five in about 10 s
    return legs, seated.analyse_sts(_sts(sts, t_rise=0.8, t_up=0.3,
                                         t_down=0.8, t_sit=0.3))


def test_bands_by_sts_time():
    assert gm.band(10.0, True)[0] == "success"
    assert gm.band(14.0, True)[0] == "warning"
    assert gm.band(18.0, True)[0] == "danger"


def test_weaker_leg_named_only_on_a_clear_difference():
    legs, sts = _cells(r_rate=2.5, l_rate=1.5)
    r = gm.compute_metrics(legs=legs, sts=sts, trusted_frac=1.0,
                           sides_checked=True, fps=16)
    assert r["weaker_leg"] == "left", r
    legs, sts = _cells(r_rate=2.5, l_rate=2.4)
    r = gm.compute_metrics(legs=legs, sts=sts, trusted_frac=1.0,
                           sides_checked=True, fps=16)
    assert r["weaker_leg"] is None, r


def test_clean_run_is_high_confidence():
    legs, sts = _cells()
    r = gm.compute_metrics(legs=legs, sts=sts, trusted_frac=0.97,
                           sides_checked=True, fps=16)
    assert r["scoreable"] and r["status"] == "success", r
    assert r["confidence_pct"] >= 75
    assert r["sts5_s"] is not None


def test_unchecked_sides_lower_confidence_and_say_why():
    legs, sts = _cells()
    r = gm.compute_metrics(legs=legs, sts=sts, trusted_frac=0.97,
                           sides_checked=False, fps=16)
    assert r["confidence_pct"] < 90
    assert any("swapped" in s for s in r["confidence_reasons"])


def test_missing_sts_is_unscoreable_but_keeps_the_legs():
    legs, _ = _cells()
    r = gm.compute_metrics(legs=legs, sts=seated.analyse_sts(seated.StandCounter(0.0)),
                           trusted_frac=1.0, sides_checked=True, fps=16)
    assert not r["scoreable"] and r["reason"]
    assert "weaker_leg" in r


def test_block_registry_is_consistent():
    assert set(SEATED_ORDER) <= set(BLOCKS)
    for k in SEATED_ORDER:
        blk = BLOCKS[k]
        assert blk.key == k and blk.instructions and blk.cue
        if blk.kind == "leg_agility":
            assert blk.side in body.SIDES


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
