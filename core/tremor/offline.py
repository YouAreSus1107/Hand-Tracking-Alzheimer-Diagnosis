"""
The tremor test's offline pass: every recorded frame of a hold, measured after
the hold is over (docs/tests/TREMOR_RESTRUCTURE_PLAN.md §4).

Live, MediaPipe runs at whatever rate the laptop manages (16-30 fps), so the
landmark cells stopped near 7.5 Hz, the optical flow was seeded from landmarks
up to 0.25 s old, and trust was decided at the live rate. Here every frame of
the Take (core/capture.FrameRecorder, 60 fps on the Razer) gets its own
landmarks, its own framing verdict, its own flow seeds and one clock, and the
result no longer depends on how busy the machine was during the hold.

Per frame, in order:
  decode -> CLAHE (always on; offline there is time) -> HandLandmarker
  -> left/right by screen position (assign_hands, shared with the live loop)
  -> FramingMonitor on the capture clock -> trusted landmarks
  -> HandFlow seeded from THIS frame's landmarks -> flow position
Then per hand: analyse_hand() on the flow and on the landmarks, with
exact_times (lost frames filled, core/tremor/metrics.fill_drops). The flow
cell is scored when it scored, else the landmark cell -- the same rule the
live test used.

No MediaPipe import: the caller passes `detect(rgb, ts_ms) -> result`, which
is also how the run-loop harness substitutes its scripted landmarker.
"""

from __future__ import annotations

import queue
import threading

import cv2
import numpy as np

from core import framing
from core.capture import Take, drop_stats, save_take
from core.hand_utils import preprocess_for_mediapipe, true_hand
from core.tremor import metrics as tm
from core.tremor.flow import HandFlow

HANDS = ("left", "right")
LUMA_EVERY = 30              # frames between luminance samples


def assign_hands(result, hands=HANDS) -> dict:
    """{"left"|"right": 21 MediaPipe landmarks} from one detection.

    Two hands are told apart by where they are, not by MediaPipe's handedness
    label: resting apart they never cross, and the label flips now and then.
    Frames are in selfie view, so the hand on the picture's left is the
    person's left. With one hand in view the label is all there is, read
    through true_hand() since on a selfie frame it names the other hand."""
    found = list(zip(getattr(result, "hand_landmarks", None) or [],
                     getattr(result, "handedness", None) or []))
    if len(found) >= 2:
        found = sorted(found[:2], key=lambda f: f[0][0].x)
        labelled = zip(("left", "right"), found)
    elif found:
        labelled = [(true_hand(found[0][1][0].category_name, selfie=True),
                     found[0])]
    else:
        labelled = []
    return {label: lms for label, (lms, _hd) in labelled if label in hands}


def analyse_take(take: Take, detect, window: tuple[float, float],
                 move_max: float, hands=HANDS, on_frame=None) -> dict:
    """Measure one hold from its recorded frames.

    detect   : (rgb uint8 array, ts_ms int) -> a HandLandmarker result
    window   : (t0, t1) scored window on the Take's clock (settle excluded)
    on_frame : called after every frame (progress, and the pause point)
    """
    w0, w1 = window
    mon = {h: framing.FramingMonitor() for h in hands}
    flows = {h: HandFlow() for h in hands}
    lm = {h: {"t": [], "pts": [], "len": []} for h in hands}
    fl = {h: {"t": [], "xy": []} for h in hands}
    all_frames = clip_frames = 0
    luma = []
    t_first = take.t[0] if len(take) else 0.0
    last_ms = -1

    for i, (t, frame) in enumerate(take.frames()):
        if frame is None:                      # a frame that would not decode
            if on_frame:
                on_frame()
            continue
        fh, fw = frame.shape[:2]
        # VIDEO mode needs strictly increasing whole milliseconds
        ms = max(last_ms + 1, int(round((t - t_first) * 1000.0)))
        last_ms = ms
        found = assign_hands(detect(preprocess_for_mediapipe(frame), ms), hands)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if i % LUMA_EVERY == 0:
            luma.append(float(gray[::8, ::8].mean()))
        in_win = w0 <= t <= w1
        for h in hands:
            lms = found.get(h)
            raw = [(p.x, p.y) for p in lms] if lms else None
            mon[h].update(raw, t)
            px = [(x * fw, y * fh) for x, y in raw] if raw else None
            sample = flows[h].update(gray, t, px)
            if not in_win or raw is None:
                continue
            all_frames += 1
            if mon[h].level == framing.CLIPPED:
                clip_frames += 1
            if mon[h].untrusted:
                continue
            length = tm.hand_length(px)
            if length is None:
                continue
            lm[h]["t"].append(t)
            lm[h]["pts"].append(tm.select(px))
            lm[h]["len"].append(length)
            if sample is not None:
                fl[h]["t"].append(sample[0])
                fl[h]["xy"].append((sample[1], sample[2]))
        if on_frame:
            on_frame()

    cells, landmark_cells = {}, {}
    for h in hands:
        d, f = lm[h], fl[h]
        lm_cell = tm.analyse_hand(d["t"], d["pts"], d["len"], move_max=move_max,
                                  exact_times=True)
        landmark_cells[h] = lm_cell
        cell = None
        if len(f["t"]) >= 8 and d["len"]:
            # one hand length from MediaPipe scales the flow, as it scales
            # the landmarks, so both read in % of hand length
            scale = sorted(d["len"])[len(d["len"]) // 2]
            cell = tm.analyse_hand(f["t"], [[xy] for xy in f["xy"]],
                                   [scale] * len(f["t"]), move_max=move_max,
                                   exact_times=True)
        if cell and cell.get("scored"):
            cell["method"] = "offline_flow"
        else:
            cell = dict(lm_cell, method="offline_landmarks")
        cells[h] = cell

    stats = drop_stats(take.t)
    stats.update(device_clock=take.device_clock, overflow=take.overflow,
                 luminance=round(float(np.mean(luma)), 1) if luma else None)
    return {"cells": cells, "landmark_cells": landmark_cells, "lm": lm,
            "flow": fl, "all_frames": all_frames, "clip_frames": clip_frames,
            "stats": stats}


class OfflineAnalyser(threading.Thread):
    """Works through submitted holds in the background.

    Paused while a hold is recording (pause()/resume()), so it never competes
    with the capture it is analysing the output of. Each hold gets a fresh
    landmarker from `make_detect()` -> (detect, close): VIDEO mode keeps
    tracking state and needs increasing timestamps, and holds restart the
    Take clock. A hold whose analysis raises is recorded in `errors`, and the
    test falls back to its live cells."""

    def __init__(self, make_detect, hands=HANDS, keep_dir=None):
        super().__init__(daemon=True, name="tremor-offline")
        self.make_detect = make_detect
        self.keep_dir = keep_dir          # --keep-frames: write each Take here
        self.hands = hands
        self._jobs: queue.Queue = queue.Queue()
        self._go = threading.Event()
        self._go.set()
        self._lock = threading.Lock()
        self._pending = 0
        self._stop = False
        self.total_frames = 0
        self.done_frames = 0
        self.results: dict = {}
        self.errors: dict = {}

    def submit(self, key: str, take: Take, window, move_max: float):
        with self._lock:
            self._pending += 1
            self.total_frames += len(take)
        self._jobs.put((key, take, window, move_max))

    def pause(self):
        self._go.clear()

    def resume(self):
        self._go.set()

    def reset(self):
        """Forget the last run's results (call only when idle)."""
        with self._lock:
            self.total_frames = self.done_frames = 0
            self.results.clear()
            self.errors.clear()

    def idle(self) -> bool:
        with self._lock:
            return self._pending == 0

    def progress(self) -> float:
        with self._lock:
            return (self.done_frames / self.total_frames
                    if self.total_frames else 1.0)

    def _tick(self):
        with self._lock:
            self.done_frames += 1
        self._go.wait()

    def run(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            key, take, window, move_max = job
            n = len(take)
            done_before = self.done_frames
            close = None
            try:
                self._go.wait()
                if self.keep_dir is not None:
                    try:
                        save_take(take, self.keep_dir / key)
                    except OSError as e:
                        self.errors[f"{key}:keep"] = str(e)
                detect, close = self.make_detect()
                self.results[key] = analyse_take(take, detect, window, move_max,
                                                 self.hands, on_frame=self._tick)
            except Exception as e:  # noqa: BLE001 - a hold falls back, never crashes
                self.errors[key] = f"{type(e).__name__}: {e}"
            finally:
                if close is not None:
                    try:
                        close()
                    except Exception:  # noqa: BLE001
                        pass
                take.free()
                with self._lock:
                    # a failed hold still counts as done for the progress bar
                    self.done_frames = done_before + n
                    self._pending -= 1

    def stop(self):
        self._stop = True
        self._go.set()
        self._jobs.put(None)
        if self.is_alive():
            self.join(timeout=2.0)
