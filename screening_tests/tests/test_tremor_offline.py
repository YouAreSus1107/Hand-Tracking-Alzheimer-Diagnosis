"""
Unit tests for record-now-analyse-after: core/capture.py (FrameRecorder, Take,
the device clock, lost-frame counting) and core/tremor/offline.py (the offline
pass over a recorded hold), plus the engine's lost-frame fill. No camera, no
MediaPipe: frames are synthetic video (test_tremor_flow's scene) and the
detector is scripted with the landmarks the frames were drawn from.

Run:  python screening_tests/tests/test_tremor_offline.py
"""

from __future__ import annotations

import math
import sys
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import capture as cap_mod
from core.capture import FrameRecorder, Take, drop_stats, load_take, save_take
from core.tremor import metrics as tm
from core.tremor import offline as off

import test_tremor_flow as synth          # the synthetic hand video

FS = 60.0


# ── scripted detector ─────────────────────────────────────────────────────

class _Lm:
    def __init__(self, x, y):
        self.x, self.y, self.z = x, y, 0.0


class _Cat:
    def __init__(self, name):
        self.category_name = name


class _Result:
    def __init__(self, hands):
        self.hand_landmarks = [[_Lm(x, y) for x, y in pts] for pts, _ in hands]
        self.handedness = [[_Cat(label)] for _, label in hands]


def _take_from_video(dur=10.0, hz=6.0, amp_px=0.6, skip=()):
    """A Take of synthetic video, plus the landmarks each frame was drawn
    with, keyed by the millisecond offset the offline pass will ask for."""
    take = Take("test", device_clock=True)
    truth = {}
    t0 = None
    for i, (t, gray, lm) in enumerate(synth._video(fs=FS, dur=dur, hz=hz,
                                                   amp_px=amp_px)):
        if i in skip:                      # a frame the camera lost
            continue
        t_abs = 1000.0 + t
        t0 = t_abs if t0 is None else t0
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR),
                               [cv2.IMWRITE_JPEG_QUALITY, 90])
        take.t.append(t_abs)
        take.jpeg.append(buf)
        norm = [(x / synth.W, y / synth.H) for x, y in lm]
        truth[int(round((t_abs - t0) * 1000.0))] = norm
    take.closed = True
    return take, truth


def _detect_for(truth):
    """One right hand. On a selfie frame MediaPipe labels it "Left"."""
    keys = np.array(sorted(truth))

    def detect(_rgb, ms):
        k = int(keys[np.argmin(np.abs(keys - ms))])
        return _Result([(truth[k], "Left")])
    return detect


def _window(take):
    return take.t[0] + 1.0, take.t[-1]


# ── the engine's lost-frame fill ──────────────────────────────────────────

def test_fill_drops_inserts_the_missing_frames():
    ts = np.array([0, 1, 2, 4, 5, 8, 9], float) / FS      # 1 lost, then 2
    arr = np.arange(len(ts), dtype=float)[:, None] * [1.0, -1.0]
    t2, a2, n = tm.fill_drops(ts, arr)
    assert n == 3, n
    assert np.allclose(np.diff(t2) * FS, 1.0), np.diff(t2) * FS
    assert np.allclose(a2[3], (arr[2] + arr[3]) / 2)      # linear midpoint


def test_fill_drops_leaves_long_holes_alone():
    ts = np.array([0, 1, 2, 7, 8, 9], float) / FS         # 4 lost: a split
    t2, _a, n = tm.fill_drops(ts, np.zeros((6, 2)))
    assert n == 0 and len(t2) == 6


def test_exact_times_keep_the_peak_through_lost_frames():
    # A 6 Hz tremor sampled at 60 fps, every 25th frame lost. Filled, the
    # frequency and size come back as with nothing lost.
    t = np.arange(int(12 * FS)) / FS
    keep = np.ones(len(t), bool)
    keep[::25] = False
    x = 2.0 * np.sin(2 * math.pi * 6.0 * t)
    pts = np.stack([x, 0.4 * x], axis=1)[:, None, :]
    full = tm.analyse_hand(t, pts, np.full(len(t), 100.0), exact_times=True)
    lossy = tm.analyse_hand(t[keep], pts[keep], np.full(keep.sum(), 100.0),
                            exact_times=True)
    # frame 0 is lost too, but a lost first frame is no gap to fill
    assert lossy["filled"] == (~keep).sum() - 1, lossy["filled"]
    assert abs(lossy["peak_hz"] - full["peak_hz"]) <= 0.05
    assert abs(lossy["amp_pct"] - full["amp_pct"]) / full["amp_pct"] < 0.05


def test_live_scoring_is_untouched_by_the_fill():
    # Without exact_times nothing is inserted and no "filled" key appears:
    # the live landmark path scores exactly as before.
    t = np.arange(600) / 16.0
    x = np.sin(2 * math.pi * 5.0 * t)
    r = tm.analyse_hand(t, np.stack([x, x], 1)[:, None, :], np.full(600, 50.0))
    assert "filled" not in r


# ── capture ───────────────────────────────────────────────────────────────

def test_drop_stats_counts_lost_frames():
    ts = [i / FS for i in range(100) if i not in (10, 50, 51)]
    s = drop_stats(ts)
    assert s["dropped"] == 3 and abs(s["period_ms"] - 1000 / FS) < 0.01, s


def test_device_anchor_removes_read_jitter():
    anchor = cap_mod.DeviceAnchor()
    rng = np.random.default_rng(1)
    placed = []
    for i in range(200):
        dev_ms = 5000.0 + i * 1000.0 / FS
        host = 77.0 + dev_ms / 1000.0 + 0.004 + abs(rng.normal(0, 0.007))
        placed.append(anchor.place(host, dev_ms))
    d = np.diff(placed[50:])
    assert np.allclose(d, 1.0 / FS, atol=2e-4), (d.min(), d.max())


class _FakeCap:
    def __init__(self, n, device=True):
        self.i, self.n, self.device = 0, n, device
        self.frame = np.full((48, 64, 3), 120, np.uint8)

    def read(self):
        if self.i >= self.n:
            return False, None
        self.i += 1
        f = self.frame.copy()
        f[0, 0] = self.i % 255
        return True, f

    def frame_time_ms(self):
        return 1000.0 + self.i * 1000.0 / FS if self.device else None


def test_recorder_keeps_only_the_armed_frames():
    cam = _FakeCap(30)
    # host clock: the frame's capture time plus a jittery read delay
    rng = np.random.default_rng(3)
    rec = FrameRecorder(cam, clock=lambda: 7.0 + cam.i / FS + abs(rng.normal(0.004, 0.006)))
    for _ in range(5):
        rec.step()
    take = rec.arm("hold")
    for _ in range(10):
        rec.step()
    assert rec.disarm() is take and take.closed
    for _ in range(5):
        rec.step()
    assert len(take) == 10 and take.device_clock
    assert np.allclose(np.diff(take.t), 1.0 / FS, atol=1e-9), np.diff(take.t)
    t, frame = next(take.frames())
    assert frame.shape == (48, 64, 3)
    seq, _t, _f = rec.next_frame(0)
    assert seq == 20


def test_recorder_caps_a_take():
    rec = FrameRecorder(_FakeCap(40), max_take_frames=12)
    take = rec.arm("hold")
    for _ in range(40):
        rec.step()
    assert len(take) == 12 and take.overflow


def test_a_take_survives_save_and_load():
    take, _ = _take_from_video(dur=0.5)
    with tempfile.TemporaryDirectory() as d:
        back = load_take(save_take(take, Path(d) / "hold"))
    assert back.t == take.t and back.device_clock
    assert all(bytes(a) == bytes(b) for a, b in zip(back.jpeg, take.jpeg))


# ── the offline pass ──────────────────────────────────────────────────────

def test_offline_pass_finds_a_subpixel_tremor_at_60fps():
    take, truth = _take_from_video(hz=6.0, amp_px=0.6)
    res = off.analyse_take(take, _detect_for(truth), _window(take), 0.15)
    cell = res["cells"]["right"]
    assert cell["scored"] and cell["method"] == "offline_flow", cell
    assert abs(cell["peak_hz"] - 6.0) <= 0.25, cell["peak_hz"]
    assert cell["band"][1] >= 12.0 - 1e-9          # the full band at 60 fps
    assert not res["cells"]["left"]["scored"]      # nobody there
    assert res["stats"]["dropped"] == 0 and res["stats"]["frames"] == len(take)


def test_offline_pass_sees_ten_hertz():
    take, truth = _take_from_video(hz=10.0, amp_px=0.6)
    cell = off.analyse_take(take, _detect_for(truth), _window(take), 0.15)["cells"]["right"]
    assert abs(cell["peak_hz"] - 10.0) <= 0.25, cell["peak_hz"]


def test_offline_pass_counts_and_fills_lost_frames():
    take, truth = _take_from_video(hz=6.0, amp_px=0.6, skip=set(range(40, 600, 37)))
    res = off.analyse_take(take, _detect_for(truth), _window(take), 0.15)
    lost = len(range(40, 600, 37))
    assert res["stats"]["dropped"] == lost, res["stats"]
    assert abs(res["cells"]["right"]["peak_hz"] - 6.0) <= 0.25


def test_assign_hands_by_position_then_label():
    left = [(0.2, 0.5)] * 21
    right = [(0.8, 0.5)] * 21
    both = off.assign_hands(_Result([(right, "Left"), (left, "Right")]))
    assert both["left"][0].x == 0.2 and both["right"][0].x == 0.8
    one = off.assign_hands(_Result([(right, "Left")]))
    assert list(one) == ["right"]                  # selfie label names the other


def test_analyser_pauses_and_finishes():
    take, truth = _take_from_video(dur=2.0)
    n = len(take)
    closed = []
    an = off.OfflineAnalyser(lambda: (_detect_for(truth), lambda: closed.append(1)))
    an.pause()
    an.start()
    an.submit("rest_palm_up", take, _window(take), 0.15)
    time.sleep(0.3)
    assert not an.idle() and an.done_frames == 0   # nothing while paused
    an.resume()
    for _ in range(300):
        if an.idle():
            break
        time.sleep(0.05)
    assert an.idle() and "rest_palm_up" in an.results, an.errors
    assert an.done_frames == n and an.progress() == 1.0
    assert closed == [1] and take.jpeg == []       # landmarker closed, frames freed
    an.stop()


def test_a_failing_hold_is_an_error_not_a_crash():
    take, _ = _take_from_video(dur=0.5)

    def broken(_rgb, _ms):
        raise RuntimeError("model gone")
    an = off.OfflineAnalyser(lambda: (broken, None))
    an.start()
    an.submit("postural", take, _window(take), 0.6)
    for _ in range(100):
        if an.idle():
            break
        time.sleep(0.05)
    assert "postural" in an.errors and "postural" not in an.results
    assert an.progress() == 1.0
    an.stop()


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
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
