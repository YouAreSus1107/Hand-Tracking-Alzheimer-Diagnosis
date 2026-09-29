"""
Headless smoke test of the camera tests' real run loops -- no camera, no
window, no sound, nothing written to results/.

Each test's own App.run() is driven frame by frame on a simulated clock, with
MediaPipe replaced by a scripted subject who does the awkward things real
people do: drifts to each edge of the picture in turn, vanishes for a moment,
blinks. The on-screen buttons are pressed in rotation, so every screen gets
visited, including the ones that only appear once a run has finished.

This exists because some lines in a run loop are only reached in particular
live states -- the tremor test crashed only once a hand touched the edge of
the picture, a state no unit test reaches and every real patient does.
Anything that raises inside a run loop fails here.

The subject is not trying to score well, so a run may end "couldn't score" --
that screen has to work too. The test only asserts that nothing raised and
that the loop got past its opening screens.

Needs the MediaPipe model files (the landmarker is built, then bypassed).
Run:  python screening_tests/tests/test_run_loops.py
"""

from __future__ import annotations

import importlib.util
import inspect
import math
import sys
import time as _real_time
import traceback
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))

import numpy as np

FPS = 15.0              # enough to clear tremor's 14 fps floor, half the frames
FRAME_W, FRAME_H = 640, 480
CLICK_EVERY = 13        # frames between button presses
SPACE_EVERY = 20        # frames between Space presses (tremor's advance key)

# A right hand, palm to camera, wrist at the origin, y down, ~1 hand length.
_HAND = [
    (0.00, 0.00),                                              # wrist
    (-0.20, -0.10), (-0.33, -0.25), (-0.42, -0.40), (-0.48, -0.52),  # thumb
    (-0.12, -0.45), (-0.14, -0.65), (-0.15, -0.80), (-0.16, -0.92),  # index
    (0.00, -0.48), (0.00, -0.70), (0.00, -0.86), (0.00, -0.98),      # middle
    (0.12, -0.45), (0.13, -0.65), (0.14, -0.79), (0.15, -0.90),      # ring
    (0.22, -0.38), (0.25, -0.53), (0.27, -0.64), (0.29, -0.74),      # pinky
]


# ── the scripted subject ─────────────────────────────────────────────────

def _misbehaving(t: float) -> str:
    """What the subject is doing wrong at time t: 'edge:<side>', 'gone' or ''.
    Every 7 s they drift to the next edge for 1.5 s; every 11 s they vanish
    for 1 s. Both are routine in a real run."""
    if t % 11.0 >= 9.5:
        return "gone"
    if t % 7.0 >= 5.5:
        return "edge:" + ("left", "right", "top", "bottom")[int(t // 7.0) % 4]
    return ""


def _place(cx: float, cy: float, size: float, mirror: bool, pinch: float):
    """21 normalised points. pinch 0 = open, 1 = thumb tip on index tip."""
    pts = []
    for i, (x, y) in enumerate(_HAND):
        if mirror:
            x = -x
        pts.append([cx + x * size, cy + y * size + size * 0.5])
    tx, ty = pts[4]
    ix, iy = pts[8]
    mx, my = (tx + ix) / 2, (ty + iy) / 2
    pts[4] = [tx + (mx - tx) * pinch, ty + (my - ty) * pinch]
    pts[8] = [ix + (mx - ix) * pinch, iy + (my - iy) * pinch]
    return pts


def _shift_to_edge(pts, side: str):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if side == "left":
        dx, dy = -min(xs) - 0.03, 0.0
    elif side == "right":
        dx, dy = 1.03 - max(xs), 0.0
    elif side == "top":
        dx, dy = 0.0, -min(ys) - 0.03
    else:
        dx, dy = 0.0, 1.03 - max(ys)
    return [[x + dx, y + dy] for x, y in pts]


class _Lm:
    __slots__ = ("x", "y", "z")

    def __init__(self, x, y):
        self.x, self.y, self.z = x, y, 0.0


class _Cat:
    def __init__(self, name):
        self.category_name = name
        self.score = 0.95


class _Result:
    def __init__(self, hands):
        self.hand_landmarks = [[_Lm(x, y) for x, y in pts] for pts, _ in hands]
        self.handedness = [[_Cat(label)] for _, label in hands]
        self.hand_world_landmarks = []


class _FakeHandLandmarker:
    def __init__(self, feed):
        self.feed = feed

    def detect_for_video(self, _img, ts_ms):
        return _Result(self.feed(ts_ms / 1000.0))

    def close(self):
        pass


# ── harness ──────────────────────────────────────────────────────────────

def _load(path: Path):
    name = f"_smoke_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def time(self):
        return self.t


class _FakeCap:
    """Grey frames on the simulated clock; presses the last frame's buttons
    in rotation, because run() reads the click between frames."""

    def __init__(self, clock, frames, harness):
        self.clock, self.left, self.h = clock, frames, harness
        self.source, self.mirrored = 0, False
        self.frame = np.full((FRAME_H, FRAME_W, 3), 90, np.uint8)

    def isOpened(self):
        return self.left > 0

    def read(self):
        self.left -= 1
        self.clock.t += 1.0 / FPS
        self.h.before_frame()
        return True, self.frame.copy()

    def release(self):
        self.left = 0

    def set(self, *_a):
        return True

    def get(self, *_a):
        return 0.0


class _Harness:
    def __init__(self, script: str):
        self.path = _REPO_ROOT / "screening_tests" / script
        self.mod = _load(self.path)
        self.clock = _Clock()
        self.frame_i = 0
        self.buttons: list[tuple] = []
        self.presses = 0
        self.states: list[str] = []
        self.app = None
        self._undo: list = []

    def patch(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def unpatch(self):
        for obj, name, value in reversed(self._undo):
            setattr(obj, name, value)
        self._undo.clear()

    def t(self) -> float:
        return self.clock.t - 1_000_000.0

    def before_frame(self):
        self.frame_i += 1
        app = self.app
        if app is not None:
            if not self.states or self.states[-1] != app.state:
                self.states.append(app.state)
            if self.buttons and self.frame_i % CLICK_EVERY == 0:
                x, y, w, h = self.buttons[self.presses % len(self.buttons)]
                self.presses += 1
                app.click = (x + w // 2, y + h // 2)
                app.mouse = app.click
        self.buttons = []

    def install(self):
        m = self.mod
        cv2 = m.cv2
        clock = self.clock
        shim = types.SimpleNamespace(**{k: getattr(_real_time, k)
                                        for k in dir(_real_time)
                                        if not k.startswith("_")})
        shim.time = clock.time
        shim.sleep = lambda _s: None
        self.patch(m, "time", shim)
        self.patch(cv2, "imshow", lambda *a: None)
        self.patch(cv2, "setMouseCallback", lambda *a: None)
        self.patch(cv2, "destroyAllWindows", lambda *a: None)
        self.patch(cv2, "waitKey",
                   lambda _ms: 32 if self.frame_i % SPACE_EVERY == 0 else 255)
        self.patch(m, "create_display_window", lambda *a, **k: None)
        self.patch(m, "window_closed", lambda _w: False)
        self.patch(m, "save_session",
                   lambda **k: _REPO_ROOT / "results" / "_smoke_test.json")
        from core.tapping import audio
        self.patch(audio.AudioWorker, "play", lambda self_, *a, **k: None)
        canvas_cls = m.Canvas
        real_button = canvas_cls.button
        harness = self

        def button(c, x, y, w, h, *a, **k):
            harness.buttons.append((x, y, w, h))
            return real_button(c, x, y, w, h, *a, **k)
        self.patch(canvas_cls, "button", button)

    def run(self, seconds: float, make_app):
        self.install()
        try:
            cap = _FakeCap(self.clock, int(seconds * FPS), self)
            self.app = make_app(self.mod, cap)
            self.app.run()
        finally:
            self.unpatch()
        return self.states


def _hand_feed(h: _Harness, two_hands: bool):
    """Scripted MediaPipe output for the hand tests."""
    def feed(t_abs):
        t = t_abs - 1_000_000.0
        bad = _misbehaving(t)
        if bad == "gone":
            return []
        pinch = 0.5 + 0.5 * math.sin(2 * math.pi * 2.0 * t)   # 2 Hz taps
        wobble = 0.004 * math.sin(2 * math.pi * 5.0 * t)       # 5 Hz tremor
        app = h.app
        state = getattr(app, "state", "")
        pts_list = []
        if two_hands:
            pts_list = [(_place(0.28 + wobble, 0.45, 0.22, True, 0.0), "Right"),
                        (_place(0.72 + wobble, 0.45, 0.22, False, 0.0), "Left")]
        else:
            cx, cy = 0.5, 0.45
            pts = _place(cx, cy, 0.22, False, pinch)
            # Spiral: hold the index tip on the centre until the trace starts
            # (each trace opens with a centre hold), then carry it along the
            # spiral being traced at an unhurried pace.
            path, start = None, None
            if state == "practice":
                path = getattr(app, "practice_points", None)
                if getattr(app, "_p_started", False):
                    start = app._p_start_t
            elif state in ("recording", "prepare", "countdown"):
                path = getattr(app, "spiral_points", None)
                if state == "recording":
                    start = getattr(app, "recording_start", None)
            if path:
                since = 0.0 if start is None else t_abs - start
                k = min(len(path) - 1, max(0, int(since / 20.0 * len(path))))
                px, py = path[k]
                tx, ty = px / FRAME_W, py / FRAME_H
                dx, dy = tx - pts[8][0], ty - pts[8][1]
                pts = [[x + dx + wobble, y + dy] for x, y in pts]
            pts_list = [(pts, "Left")]            # selfie frame: names the other hand
        if bad.startswith("edge:"):
            side = bad.split(":")[1]
            pts_list = [(_shift_to_edge(p, side), lab) for p, lab in pts_list]
        return pts_list
    return feed


class _LockstepRecorder:
    """Stands in for a capture thread (core/capture.FrameRecorder): one
    frame per UI frame, on the simulated clock. A real thread would read the
    fake camera dry before the first screen was drawn. While the test waits
    on real work in another thread (tremor's offline pass), each frame also
    gives that thread a little real time, or the simulated run would end
    before the work could."""

    def __init__(self, rec, harness):
        self.rec, self.h = rec, harness

    def start(self):
        pass

    def stop(self):
        pass

    def next_frame(self, after_seq, timeout=1.0):
        if getattr(self.h.app, "state", "") == "analysing":
            _real_time.sleep(0.02)
        if not self.rec.step():
            return None
        return self.rec.next_frame(after_seq, timeout=0)

    def __getattr__(self, name):
        return getattr(self.rec, name)


def _run_hand_test(script: str, seconds: float, two_hands: bool):
    h = _Harness(script)
    feed = _hand_feed(h, two_hands)

    def make(mod, cap):
        # A test that builds landmarkers itself (tremor: one live, one per
        # hold for its offline pass) takes the scripted one as its factory.
        if "landmarker_factory" in inspect.signature(mod.App).parameters:
            app = mod.App(cap, landmarker_factory=lambda: _FakeHandLandmarker(feed))
            if hasattr(app, "recorder"):
                app.recorder = _LockstepRecorder(
                    mod.FrameRecorder(cap, clock=h.clock.time), h)
            return app
        app = mod.App(cap)
        app.landmarker.close()
        app.landmarker = _FakeHandLandmarker(feed)
        return app

    return _check_run(script, h, seconds, make)


def _check_run(script, h, seconds, make):
    try:
        states = h.run(seconds, make)
    except Exception:  # noqa: BLE001 - the whole point: report where it broke
        states = h.states
        raise AssertionError(
            f"{script} raised at t={h.t():.1f}s in state "
            f"'{states[-1] if states else '?'}' (visited {states}):\n"
            + traceback.format_exc())
    distinct = set(states)
    assert len(distinct) >= 4, \
        f"{script}: harness never got past the opening screens: {states}"
    return states


# ── the tests ────────────────────────────────────────────────────────────

def test_finger_tapping_run_loop():
    states = _run_hand_test("finger_tapping.py", 150, two_hands=False)
    print(f"        visited: {' > '.join(dict.fromkeys(states))}")


def test_spiral_run_loop():
    states = _run_hand_test("spiral_test.py", 200, two_hands=False)
    print(f"        visited: {' > '.join(dict.fromkeys(states))}")


def test_tremor_run_loop():
    states = _run_hand_test("tremor_test.py", 200, two_hands=True)
    assert "complete" in states, f"tremor never finished a run: {states}"
    print(f"        visited: {' > '.join(dict.fromkeys(states))}")


def test_oculomotor_run_loop():
    h = _Harness("oculomotor_test.py")
    GazeSample = sys.modules["core.gaze.tracker"].GazeSample

    def sample(now):
        t = now - 1_000_000.0
        bad = _misbehaving(t)
        if bad == "gone":
            return None
        blink = (t % 3.0) < 0.12
        r = 0.5 + 0.12 * (1 if (t % 2.6) < 1.3 else -1) + 0.002 * math.sin(40 * t)
        if bad.startswith("edge:"):
            r += 0.2
        cx, cy = FRAME_W // 2, FRAME_H // 2
        return GazeSample(
            ratio=None if blink else r, ratio_raw=None if blink else r,
            ratio_y=None if blink else 0.0, ratio_y_raw=None if blink else 0.0,
            blink=blink, iris_px=[(cx - 40, cy), (cx + 40, cy)],
            corners_px=[(cx - 60, cy), (cx - 20, cy), (cx + 20, cy), (cx + 60, cy)],
            openness=0.05 if blink else 0.3, open_frac=0.15 if blink else 1.0)

    def make(mod, cap):
        app = mod.App(cap)
        app.detect_gaze = lambda frame, now: sample(now)
        return app

    states = _check_run("oculomotor_test.py", h, 360, make)
    print(f"        visited: {' > '.join(dict.fromkeys(states))}")


# A seated person side-on to the camera, in pixels (MediaPipe Pose indices).
_SEATED = {0: (300, 120), 11: (295, 160), 12: (305, 160), 13: (300, 220),
           14: (306, 220), 15: (330, 200), 16: (334, 200), 23: (290, 280),
           24: (300, 280), 25: (380, 285), 26: (390, 285), 27: (380, 380),
           28: (390, 380), 29: (372, 392), 30: (382, 392), 31: (400, 395),
           32: (410, 395)}
_UPPER = (0, 11, 12, 13, 14, 15, 16, 23, 24)
_LEG = {"left": (25, 27, 29, 31), "right": (26, 28, 30, 32)}


def test_gait_run_loop():
    """The walking test's seated part: arm raise, both legs stamping, five
    sit-to-stands -- while drifting to the edges and vanishing like the rest."""
    h = _Harness("gait_test.py")

    def pose(t_abs):
        t = t_abs - 1_000_000.0
        bad = _misbehaving(t)
        if bad == "gone":
            return None, None
        app = h.app
        state = getattr(app, "state", "")
        pts = {i: list(p) for i, p in _SEATED.items()}
        if state == "setup" and (app.clock_in_state(t_abs) > 1.5):
            pts[16] = [334, 60]                       # right wrist above the head
        if state == "recording":
            since = t_abs - app.record_start
            blk = app.block
            if blk.kind == "leg_agility":
                lift = 25 * abs(math.sin(math.pi * 2.5 * since))
                for i in _LEG[blk.side]:
                    pts[i][1] -= lift
            else:
                ph = (since % 2.4) / 2.4
                s = 1 - abs(2 * ph - 1)               # 0 -> 1 -> 0 each 2.4 s
                for i in _UPPER:
                    pts[i][1] -= 85 * s
        full = [(0.0, 0.0)] * 33
        for i, (x, y) in pts.items():
            full[i] = (float(x), float(y))
        # the 16 points the model returns but the test ignores sit on the nose
        full = [p if i in pts else full[0] for i, p in enumerate(full)]
        if bad.startswith("edge:"):
            norm = [[x / FRAME_W, y / FRAME_H] for x, y in full]
            norm = _shift_to_edge(norm, bad.split(":")[1])
            full = [(x * FRAME_W, y * FRAME_H) for x, y in norm]
        return full, [0.9] * 33

    class _FakePose:
        def detect(self, _rgb, t_s, _size):
            return pose(t_s)

        def close(self):
            pass

    def make(mod, cap):
        app = mod.App(cap)
        app.tracker.close()
        app.tracker = _FakePose()
        app.clock_in_state = lambda now: now - app.t_state
        return app

    states = _check_run("gait_test.py", h, 200, make)
    assert "complete" in states, f"gait never finished a run: {states}"
    print(f"        visited: {' > '.join(dict.fromkeys(states))}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        t0 = _real_time.perf_counter()
        try:
            fn()
            print(f"  PASS  {fn.__name__}  ({_real_time.perf_counter() - t0:.0f} s)")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
