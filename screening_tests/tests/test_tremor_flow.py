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


class _FakeCap:
    """Serves synthetic frames (BGR, and pre-mirrored so FlowCamera's selfie
    flip puts the hand back where the landmarks say it is)."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.i = 0

    def read(self):
        if self.i >= len(self.frames):
            import time
            time.sleep(0.01)
            return False, None
        _t, gray, _lm = self.frames[self.i]
        self.i += 1
        return True, cv2.flip(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), 1)


def test_flow_camera_thread_hands_out_frames_and_samples():
    frames = list(_video(dur=2.0, hz=5.0, amp_px=1.0))
    cam = fl.FlowCamera(_FakeCap(frames), hands=("left",))
    cam.set_seeds("left", _LM, 1e12)            # "fresh" for the whole test
    fl_age, fl.SEED_MAX_AGE_S = fl.SEED_MAX_AGE_S, 1e13
    try:
        cam.start()
        seqs, got = [], []
        seq = 0
        while len(seqs) < 20:
            r = cam.next_frame(seq, timeout=2.0)
            assert r is not None, "no frame from the thread"
            seq = r[0]
            seqs.append(seq)
        import time
        deadline = time.time() + 30
        while cam.cap.i < len(frames) and time.time() < deadline:
            got.append(cam.drain()["left"])
            time.sleep(0.05)
        cam.stop()
        got.append(cam.drain()["left"])
    finally:
        fl.SEED_MAX_AGE_S = fl_age
    assert seqs == sorted(set(seqs)), "frames came back out of order"
    n = sum(len(v) for v in got)
    assert n >= len(frames) - 5, f"only {n} flow samples for {len(frames)} frames"
    assert cam.fps > 0


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
