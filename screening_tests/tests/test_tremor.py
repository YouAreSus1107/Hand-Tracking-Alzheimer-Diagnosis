"""
Unit tests for the hand tremor engine (docs/tests/TREMOR_TEST_PLAN.md §6):
spectral scoring exercised on synthetic hands, plus the glove IMU window the
tool records beside the camera. No camera, no board.

A synthetic hand is four landmarks with tracker-level white noise on every
coordinate; a tremor is a sinusoid added to all four. Known frequency and
amplitude in, known peak and RMS out.

Run:  python -m pytest screening_tests/tests/test_tremor.py
 or:  python screening_tests/tests/test_tremor.py   (self-runs without pytest)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.tremor import metrics as tm
from core.tremor.phases import PHASES, PHASE_ORDER, HANDS

RNG = np.random.default_rng(11)
L_PX = 80.0                     # hand length in pixels: a small, far hand
BASE = np.array([[320, 300], [290, 250], [315, 220], [330, 215]], float)


def _hand(fs=30.0, dur=18.0, noise_px=0.8, hz=None, amp_frac=0.0,
          drift_px_s=0.0, uneven=False):
    """(ts, pts, lens) for one hand. `amp_frac` is the tremor's peak
    amplitude in hand lengths along x; `uneven` mimics a CPU-bound camera
    whose frame intervals wander between 1x and 1.6x the nominal one."""
    n = int(dur * fs)
    if uneven:
        dt = (1.0 / fs) * RNG.uniform(1.0, 1.6, n)
        ts = np.cumsum(dt)
    else:
        ts = np.arange(n) / fs
    pts = []
    for t in ts:
        p = BASE + RNG.normal(0, noise_px, BASE.shape)
        if hz:
            p[:, 0] += amp_frac * L_PX * math.sin(2 * math.pi * hz * t)
        p[:, 0] += drift_px_s * t
        pts.append(p)
    return list(ts), pts, [L_PX] * n


def _run(cells_by_phase):
    return tm.compute_metrics(cells_by_phase, phase_order=PHASE_ORDER,
                              hands=HANDS)


# ── one hand ──────────────────────────────────────────────────────────────

def test_still_hand_with_tracker_noise_reads_no_tremor():
    for fs in (16.0, 30.0):
        for noise in (0.8, 2.0):
            for _ in range(10):
                r = tm.analyse_hand(*_hand(fs=fs, noise_px=noise))
                assert r["scored"], r
                assert r["verdict"] == tm.NONE, (fs, noise, r["prominence"],
                                                 r["amp_pct"])


def test_rest_tremor_is_found_at_its_frequency_at_16_and_30_fps():
    for fs in (16.0, 30.0):
        r = tm.analyse_hand(*_hand(fs=fs, hz=5.0, amp_frac=0.05))
        assert r["verdict"] == tm.DETECTED, r
        assert abs(r["peak_hz"] - 5.0) <= 0.3, r["peak_hz"]


def test_amplitude_is_the_rms_displacement_in_hand_lengths():
    # peak amplitude 5% of hand length along x → 2-D RMS 5/√2 = 3.54 %
    r = tm.analyse_hand(*_hand(fs=30.0, hz=5.0, amp_frac=0.05))
    assert abs(r["amp_pct"] - 3.54) < 0.3, r["amp_pct"]
    # and the centimetre estimate is peak-to-peak on the assumed palm
    assert abs(r["amp_pp_cm_est"] - 2 * 0.05 * tm.PALM_LEN_CM) < 0.15


def test_uneven_frame_timing_does_not_move_the_peak():
    # CPU-bound capture: 1/median(dt) would overstate the rate and shift the
    # peak. The mean-rate, per-window spacing keeps it where it is.
    r = tm.analyse_hand(*_hand(fs=24.0, hz=5.0, amp_frac=0.05, uneven=True))
    assert r["scored"], r
    assert abs(r["peak_hz"] - 5.0) <= 0.4, r["peak_hz"]


def test_faster_tremor_is_found_when_the_rate_resolves_it():
    r = tm.analyse_hand(*_hand(fs=30.0, hz=9.0, amp_frac=0.04))
    assert r["verdict"] == tm.DETECTED and abs(r["peak_hz"] - 9.0) <= 0.3


def test_small_clean_tremor_is_only_possible():
    # A tiny but clean peak — physiological tremor in the arms-out hold —
    # is not reported as a tremor.
    r = tm.analyse_hand(*_hand(fs=30.0, hz=6.0, amp_frac=0.012))
    assert r["verdict"] in (tm.POSSIBLE, tm.NONE), r


def test_low_frame_rate_refuses_rather_than_guessing():
    r = tm.analyse_hand(*_hand(fs=10.0, hz=5.0, amp_frac=0.05))
    assert not r["scored"] and r["why"] == "low_fps"


def test_voluntary_drift_windows_are_dropped():
    # 10 px/s is ~12% of the hand length a second: the hand is being moved.
    r = tm.analyse_hand(*_hand(fs=30.0, drift_px_s=10.0))
    assert not r["scored"] and r["why"] == "moving", r


def test_arms_out_sway_is_kept_under_the_postural_gate():
    # Live run 2026-09-24: arms held out swayed 15-42% of a hand length per
    # window and the rest-hold gate threw every window away. ~0.3 Hz sway of
    # 20% must be kept under the postural gate, and a tremor still found.
    from core.tremor.phases import PHASES
    ts, pts, lens = _hand(fs=16.0, hz=5.0, amp_frac=0.05)
    for t, p in zip(ts, pts):
        p[:, 1] += 0.20 * L_PX * math.sin(2 * math.pi * 0.3 * t)
    assert tm.analyse_hand(ts, pts, lens)["why"] == "moving"
    r = tm.analyse_hand(ts, pts, lens, move_max=PHASES["postural"].move_max)
    assert r["scored"] and r["verdict"] == tm.DETECTED
    assert abs(r["peak_hz"] - 5.0) <= 0.3


def test_frame_rate_does_not_lower_confidence():
    # The camera's reach is the machine's, not the recording's.
    for fs in (16.0, 30.0):
        cells = {p: {h: tm.analyse_hand(*_hand(fs=fs)) for h in HANDS}
                 for p in PHASE_ORDER}
        m = _run(cells)
        assert m["confidence_level"] == "high", (fs, m["confidence_pct"])


def test_a_blackout_splits_the_recording_without_a_false_peak():
    ts, pts, lens = _hand(fs=30.0, dur=20.0)
    keep = [i for i, t in enumerate(ts) if not (8.0 <= t < 11.0)]
    r = tm.analyse_hand([ts[i] for i in keep], [pts[i] for i in keep],
                        [lens[i] for i in keep])
    assert r["scored"] and r["verdict"] == tm.NONE, r
    assert r["valid_s"] < 18.0


def test_too_few_frames_is_no_data():
    r = tm.analyse_hand([0.0, 0.03], [BASE, BASE], [L_PX, L_PX])
    assert not r["scored"] and r["why"] == "no_data"


def test_hand_length_and_select_read_the_right_landmarks():
    pts = [(0.0, 0.0)] * 21
    pts[0], pts[9] = (100.0, 200.0), (100.0, 120.0)
    assert tm.hand_length(pts) == 80.0
    assert len(tm.select(pts)) == len(tm.LANDMARKS)
    assert tm.hand_length(None) is None


# ── the whole run ─────────────────────────────────────────────────────────

def test_one_sided_rest_tremor_is_flagged_and_asymmetric():
    cells = {p: {"left": tm.analyse_hand(*_hand()),
                 "right": tm.analyse_hand(*_hand())} for p in PHASE_ORDER}
    cells["rest"]["right"] = tm.analyse_hand(*_hand(hz=5.0, amp_frac=0.05))
    m = _run(cells)
    assert m["scoreable"] and m["status"] == "danger"
    assert m["tremor_where"] == "rest:right"
    assert abs(m["tremor_peak_hz"] - 5.0) <= 0.3
    assert m["asymmetry_ratio"] > 3.0
    assert m["detected_cells"] == 1 and m["scored_cells"] == 6


def test_clean_run_reads_no_tremor_with_high_confidence():
    cells = {p: {h: tm.analyse_hand(*_hand()) for h in HANDS}
             for p in PHASE_ORDER}
    m = _run(cells)
    assert m["scoreable"] and m["status"] == "success"
    assert m["confidence_level"] == "high", m["confidence_pct"]
    # no peak, so no peak frequency: the tallest noise bin is not a finding
    assert m["tremor_peak_hz"] is None and m["rest_peak_hz"] is None
    assert m["tremor_amp_pct"] is not None


def test_emergence_under_counting_is_reported():
    cells = {p: {h: tm.analyse_hand(*_hand()) for h in HANDS}
             for p in PHASE_ORDER}
    cells["rest_count"]["left"] = tm.analyse_hand(*_hand(hz=5.0, amp_frac=0.05))
    m = _run(cells)
    assert m["emergence_ratio"] > 2.0


def test_nothing_scoreable_explains_itself():
    lo = {p: {h: tm.analyse_hand(*_hand(fs=10.0)) for h in HANDS}
          for p in PHASE_ORDER}
    m = _run(lo)
    assert not m["scoreable"] and "frame rate" in m["reason"]
    m = _run({p: {h: None for h in HANDS} for p in PHASE_ORDER})
    assert not m["scoreable"] and "No hands" in m["reason"]


def test_missing_hand_lowers_confidence_but_still_scores():
    cells = {p: {"left": tm.analyse_hand(*_hand()), "right": None}
             for p in PHASE_ORDER}
    m = _run(cells)
    assert m["scoreable"] and m["asymmetry_ratio"] is None
    assert m["confidence_pct"] <= 50.0


def test_every_phase_is_registered_in_order():
    assert PHASE_ORDER == tuple(PHASES)
    for p in PHASES.values():
        assert p.scored_s > tm.WIN_S * 2, p.key
        assert p.instructions and p.cue


# ── glove ─────────────────────────────────────────────────────────────────

def _imu_series(fs=100.0, dur=10.0, hz=5.0):
    n = int(fs * dur)
    t = [i / fs for i in range(n)]
    gyro = [(0.0, 0.0, 20.0 * math.sin(2 * math.pi * hz * ti) + 1.0) for ti in t]
    accel = [(0.0, 0.0, 1.0 + 0.01 * math.sin(2 * math.pi * hz * ti)) for ti in t]
    return {"fs": fs, "t": t, "accel": accel, "gyro": gyro}


def test_glove_gyro_peak_matches_the_tremor():
    g = tm.analyse_glove(_imu_series(hz=5.0))
    assert abs(tm.glove_peak_hz(g) - 5.0) < 0.3


def test_glove_disagreement_is_the_validation_number():
    cells = {p: {h: tm.analyse_hand(*_hand()) for h in HANDS}
             for p in PHASE_ORDER}
    cells["rest"]["left"] = tm.analyse_hand(*_hand(hz=5.0, amp_frac=0.05))
    m = tm.compute_metrics(cells, phase_order=PHASE_ORDER, hands=HANDS,
                           glove={"rest": tm.analyse_glove(_imu_series(hz=5.0))})
    assert m["glove_rest_peak_hz"] is not None
    assert m["cam_glove_hz_diff"] < 0.5


def test_empty_glove_window_is_none_not_zero():
    assert tm.analyse_glove(None) is None
    assert tm.analyse_glove({"fs": 0.0, "t": [], "accel": [], "gyro": []}) is None


def test_reader_imu_series_selects_by_host_time_in_physical_units():
    import tempfile
    from core.glove.protocol import GloveFrame
    from core.glove.serial_io import GloveReader
    banner = ("#GLOVE fw=0.5.0 proto=1 board=nano33ble rate=100 adc_bits=12 "
              "adc_ref_mv=3300 vdiv_mv=3300 r_fixed=10000 imu=BMI270_BMM150 "
              "imu_scale=1000 emg=0 cols=seq,t_us,p0,ax,ay,az,gx,gy,gz "
              "chan=p0:fsr:10000,ax:accel,ay:accel,az:accel,"
              "gx:gyro,gy:gyro,gz:gyro")
    reader = GloveReader(tempfile.gettempdir())
    reader._acc.feed(banner)
    for i in range(30):
        f = GloveFrame(seq=i, t_us=i * 10_000,
                       values=(100, 0, 0, 1000, 0, 0, 2500))
        reader._frames.append((f, 1000.0 + i * 0.01))
    s = reader.imu_series(1000.05, 1000.149)
    assert len(s["t"]) == 10
    assert s["accel"][0] == (0.0, 0.0, 1.0)
    assert s["gyro"][0] == (0.0, 0.0, 2.5)
    assert s["fs"] > 0
    assert reader.imu_name() == "BMI270_BMM150"


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
