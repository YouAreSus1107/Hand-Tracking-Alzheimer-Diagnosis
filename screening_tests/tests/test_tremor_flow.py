"""
Unit tests for the optical-flow tremor signal (core/tremor/flow.py) on
synthetic video. No camera.

A synthetic hand is a patch of skin-like texture inside a hand-shaped
polygon, over a plain background, with 21 "landmarks" on the polygon.
Each frame shifts the whole picture by a known sub-pixel offset
(cv2.warpAffine, bilinear) and adds sensor noise, so the true motion is
known to the micron. The flow track then goes through
core/tremor/metrics.analyse_hand exactly as the live test sends it.

Run:  python -m pytest screening_tests/tests/test_tremor_flow.py
 or:  python screening_tests/tests/test_tremor_flow.py   (self-runs)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.tremor import flow as fl
from core.tremor import metrics as tm

W, H = 640, 480
RNG = np.random.default_rng(5)

# 21 landmark-like points: wrist (0), knuckles, fingertips. Hand length
# (0 -> 9) is ~115 px, a hand in the lap seen by a 640x480 camera.
_LM = np.array([
    [320, 380],                                   # 0 wrist
    [285, 355], [265, 330], [252, 305], [242, 282],   # thumb 1-4
    [295, 290], [290, 255], [287, 232], [285, 212],   # index 5-8
    [320, 285], [320, 245], [320, 220], [320, 198],   # middle 9-12
    [345, 290], [350, 255], [352, 232], [354, 214],   # ring 13-16
    [368, 300], [378, 275], [384, 258], [388, 243],   # pinky 17-20
], np.float32)


def _scene():
    """Background, and a textured hand inside the landmarks' hull."""
    bg = np.full((H, W), 90, np.uint8)
    tex = RNG.normal(150, 25, (H, W)).astype(np.float32)
    tex = cv2.GaussianBlur(tex, (0, 0), 1.6)              # skin: soft texture
    mask = fl.hand_mask((H, W), _LM, 6)
    img = np.where(mask > 0, np.clip(tex, 0, 255), bg).astype(np.float32)
    return img


def _video(fs=60.0, dur=18.0, hz=None, amp_px=0.0, noise=2.0, drift_px_s=0.0):
    """Frames of the scene shifted by x(t) = amp sin(2 pi hz t) (+ drift)."""
    scene = _scene()
    n = int(dur * fs)
    t = np.arange(n) / fs
    dx = np.zeros(n)
    if hz:
        dx += amp_px * np.sin(2 * math.pi * hz * t)
    dx += drift_px_s * t
    dy = 0.4 * dx                                         # a slightly oblique tremor
    for i in range(n):
        m = np.float32([[1, 0, dx[i]], [0, 1, dy[i]]])
        f = cv2.warpAffine(scene, m, (W, H), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE)
        f = f + RNG.normal(0, noise, f.shape)
        yield t[i], np.clip(f, 0, 255).astype(np.uint8), _LM + [dx[i], dy[i]]


def _track(**kw):
    hf = fl.HandFlow()
    out = []
    for t, gray, lm in _video(**kw):
        s = hf.update(gray, t, lm)
        if s is not None:
            out.append(s)
    return hf, np.array(out)


def _analyse(track, move_max=0.15):
    ts = track[:, 0]
    pts = track[:, 1:3][:, None, :]
    length = float(np.hypot(*(_LM[9] - _LM[0])))
    return tm.analyse_hand(ts, pts, np.full(len(ts), length), move_max=move_max)


def test_follows_a_subpixel_tremor_and_its_frequency():
    # 0.3 px peak in a 115 px hand: 0.18 % RMS along x -- far below what
    # MediaPipe's landmark jitter lets the camera see.
    hf, tr = _track(hz=6.0, amp_px=0.3)
    assert len(tr) > 0.95 * hf.frames, f"too many gaps: {hf.gaps}"
    r = _analyse(tr)
    assert r["scored"], r
    assert abs(r["peak_hz"] - 6.0) <= 0.25, r["peak_hz"]
    assert r["prominence"] > 20, r["prominence"]


def test_recovers_amplitude_within_ten_percent():
    amp = 2.0                                  # px peak along x
    _, tr = _track(hz=5.0, amp_px=amp)
    r = _analyse(tr)
    length = float(np.hypot(*(_LM[9] - _LM[0])))
    # 2-D RMS of x = a sin, y = 0.4 a sin
    want = amp * math.sqrt(1 + 0.4 ** 2) / math.sqrt(2) / length * 100
    assert abs(r["amp_pct"] - want) / want < 0.10, (r["amp_pct"], want)


def test_sees_a_tremor_above_the_old_camera_band():
    # 10 Hz is invisible at 16 fps (band top ~7.6 Hz); at 60 fps it is not.
    _, tr = _track(hz=10.0, amp_px=0.5)
    r = _analyse(tr)
    assert r["band"][1] >= 12.0 - 1e-9, r["band"]
    assert abs(r["peak_hz"] - 10.0) <= 0.25, r["peak_hz"]


def test_still_hand_noise_floor_is_far_below_landmarks():
    # The recorded MediaPipe rest floor is 0.11-0.81 % RMS in band
    # (docs/research/09-tremor-validation-datasets.md, C0).
    _, tr = _track(noise=3.0)
    r = _analyse(tr)
    assert r["scored"]
    assert r["amp_pct"] < 0.05, r["amp_pct"]
    assert r["verdict"] == tm.NONE


def test_drift_is_posture_not_tremor():
    _, tr = _track(hz=5.0, amp_px=0.5, drift_px_s=1.0)
    r = _analyse(tr, move_max=0.60)
    assert r["scored"]
    assert abs(r["peak_hz"] - 5.0) <= 0.25


def test_reseeding_leaves_no_jump():
    # Starve the tracker of points half-way: every point is thrown away and
    # re-seeded. Position is summed from increments, so the trace must not step.
    hf = fl.HandFlow()
    xs = []
    for i, (t, gray, lm) in enumerate(_video(dur=4.0)):
        if i == 120:
            hf.pts = hf.pts[:3]
        s = hf.update(gray, t, lm)
        if s is not None:
            xs.append(s[1])
    steps = np.abs(np.diff(xs))
    assert steps.max() < 0.2, steps.max()


def test_no_seeds_no_samples():
    hf = fl.HandFlow()
    for t, gray, _lm in _video(dur=1.0):
        assert hf.update(gray, t, None) is None


# ── engine 4: a flat, spread hand in the lap (TREMOR_TEST_PLAN.md §3c) ──────

_SPREAD = np.array([
    [320, 400], [280, 380], [250, 350], [228, 322], [210, 298],
    [290, 300], [270, 262], [258, 238], [248, 216],
    [320, 292], [320, 248], [320, 222], [320, 198],
    [350, 300], [370, 262], [382, 240], [392, 220],
    [375, 318], [405, 292], [422, 276], [436, 262]], np.float32)


def _lap_track(shape: bool, hz=5.0, amp=0.6, fs=60.0, dur=12.0):
    """A textured hand with its fingers spread, trembling over a textured
    lap that does not move. Returns (measured amp_pct, true amp_pct)."""
    rng = np.random.default_rng(7)
    lap = cv2.GaussianBlur(rng.normal(110, 30, (H, W)).astype(np.float32), (0, 0), 1.2)
    skin = cv2.GaussianBlur(rng.normal(160, 20, (H, W)).astype(np.float32), (0, 0), 1.6)
    hand = fl.hand_shape_mask((H, W), _SPREAD).astype(np.float32) / 255.0
    length = float(np.hypot(*(_SPREAD[9] - _SPREAD[0])))
    hf = fl.HandFlow(shape=shape)
    out = []
    for i in range(int(dur * fs)):
        t = i / fs
        dx = amp * math.sin(2 * math.pi * hz * t)
        m = np.float32([[1, 0, dx], [0, 1, 0.4 * dx]])
        sk = cv2.warpAffine(skin, m, (W, H), borderMode=cv2.BORDER_REPLICATE)
        mk = cv2.warpAffine(hand, m, (W, H))
        f = lap * (1 - mk) + sk * mk + rng.normal(0, 2, (H, W))
        s = hf.update(np.clip(f, 0, 255).astype(np.uint8), t, _SPREAD + [dx, 0.4 * dx])
        if s is not None:
            out.append(s)
    a = np.array(out)
    r = tm.analyse_hand(a[:, 0], a[:, 1:3][:, None, :], np.full(len(a), length),
                        exact_times=True, instrument="flow")
    return r["amp_pct"], amp * math.sqrt(1 + 0.4 ** 2) / math.sqrt(2) / length * 100


def test_hand_shape_excludes_the_lap_between_spread_fingers():
    assert fl.hull_extra_frac((H, W), _SPREAD) > 0.4


def test_hand_shaped_mask_reads_the_true_amplitude_over_a_lap():
    got, want = _lap_track(shape=True)
    assert abs(got - want) / want < 0.10, (got, want)


def test_convex_hull_under_reads_over_a_lap():
    # what engines 1-3 did: still lap points pull the median toward zero
    hull, want = _lap_track(shape=False)
    shape, _ = _lap_track(shape=True)
    assert hull < shape, (hull, shape)
    assert hull < 0.85 * want, (hull, want)


def test_landmark_smoother_holds_a_jittering_hand_still():
    sm = fl.LandmarkSmoother()
    rng = np.random.default_rng(1)
    out = None
    for i in range(60):                      # 1 s at 60 fps, 2 px jitter
        out = sm.update(i / 60, _SPREAD + rng.normal(0, 2.0, _SPREAD.shape))
    assert np.abs(out - _SPREAD).max() < 1.5
    assert sm.update(5.0, None) is None      # nothing seen for 0.3 s


def test_scene_flow_reads_camera_shake_and_skips_the_hands():
    # the whole picture shakes at 5.5 Hz (a camera on a bed); the hands also
    # tremble on their own at 4 Hz. The scene must report 5.5 Hz, not 4.
    rng = np.random.default_rng(9)
    room = cv2.GaussianBlur(rng.normal(120, 30, (H, W)).astype(np.float32), (0, 0), 1.3)
    skin = cv2.GaussianBlur(rng.normal(160, 20, (H, W)).astype(np.float32), (0, 0), 1.6)
    hand = fl.hand_shape_mask((H, W), _SPREAD).astype(np.float32) / 255.0
    sf = fl.SceneFlow()
    out = []
    fs = 60.0
    for i in range(int(12 * fs)):
        t = i / fs
        shake = 0.5 * math.sin(2 * math.pi * 5.5 * t)
        trem = 1.5 * math.sin(2 * math.pi * 4.0 * t)
        m_hand = np.float32([[1, 0, shake + trem], [0, 1, 0]])
        m_room = np.float32([[1, 0, shake], [0, 1, 0]])
        sk = cv2.warpAffine(skin, m_hand, (W, H), borderMode=cv2.BORDER_REPLICATE)
        mk = cv2.warpAffine(hand, m_hand, (W, H))
        rm = cv2.warpAffine(room, m_room, (W, H), borderMode=cv2.BORDER_REPLICATE)
        f = rm * (1 - mk) + sk * mk + rng.normal(0, 2, (H, W))
        s = sf.update(np.clip(f, 0, 255).astype(np.uint8), t, [_SPREAD + [shake + trem, 0]])
        if s is not None:
            out.append(s)
    a = np.array(out)
    length = float(np.hypot(*(_SPREAD[9] - _SPREAD[0])))
    r = tm.analyse_hand(a[:, 0], a[:, 1:3][:, None, :], np.full(len(a), length),
                        exact_times=True, instrument="flow")
    assert abs(r["peak_hz"] - 5.5) <= 0.25, r
    want = 0.5 / math.sqrt(2) / length * 100
    assert abs(r["amp_pct"] - want) / want < 0.15, (r["amp_pct"], want)


def _view_trace(hz=None, amp_px=0.0):
    from core.tremor.flow_view import LiveFlowView
    view = LiveFlowView(hands=("right",))
    t_last = 0.0
    for i, (t, gray, lm) in enumerate(_video(fs=60.0, dur=4.0, hz=hz, amp_px=amp_px)):
        if i % 2:                         # the live loop runs at ~30 fps
            continue
        view.update(gray, t, {"right": lm})
        t_last = t
    return view, np.array([v for _, v in view.trace("right", t_last)])


def test_live_view_draws_a_still_hand_flat_and_a_tremor_as_a_wave():
    from core.tremor.flow_view import TRACE_RANGE_PCT
    _, still = _view_trace()
    _, shake = _view_trace(hz=5.0, amp_px=0.6)       # ~0.4 % of hand length peak
    assert len(still) > 20 and len(shake) > 20
    # on the fixed scale a still hand stays near the midline ...
    assert np.abs(still).max() < 0.2 * TRACE_RANGE_PCT, np.abs(still).max()
    # ... and a small tremor visibly moves it
    assert shake.std() > 5 * still.std(), (shake.std(), still.std())


def test_live_view_tracks_skin_points_inside_the_hand():
    view, _ = _view_trace()
    pts = view.hands["right"].flow.pts.reshape(-1, 2)
    assert len(pts) >= fl.MIN_POINTS
    inside = fl.hand_shape_mask((H, W), _LM, 4)
    assert all(inside[int(y), int(x)] for x, y in pts)


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
