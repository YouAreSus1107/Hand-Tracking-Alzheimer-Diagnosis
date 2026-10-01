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
  -> a hand the whole frame missed is looked for in its own half of the
     picture (detect_half; engine 4)
  -> FramingMonitor on the capture clock -> trusted landmarks; a dropout
     shorter than DROPOUT_MAX_S does not break trust
  -> LandmarkSmoother (0.3 s median, geometry only) -> HandFlow seeded and
     fenced by the hand's own shape -> flow position
  -> SceneFlow on everything else -> the camera's own shake, reported
     beside each hand (never subtracted: see flow.SCENE_POINTS)
Then per hand: analyse_hand() on the flow and on the landmarks, with
exact_times (lost frames filled, core/tremor/metrics.fill_drops). The flow
cell is scored when it scored, else the landmark cell -- the same rule the
live test used. Engine 4: TREMOR_TEST_PLAN.md §3c.

No MediaPipe import: the caller passes `detect(rgb, ts_ms) -> result`, which
is also how the run-loop harness substitutes its scripted landmarker, and
optionally `side_detect` = {"left"|"right": single-hand detect} for the
half-frame fallback.
"""

from __future__ import annotations

import queue
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np

from core import framing
from core.capture import Take, drop_stats, save_take
from core.hand_utils import preprocess_for_mediapipe, true_hand
from core.tremor import metrics as tm
from core.tremor.flow import HandFlow, LandmarkSmoother, SceneFlow

HANDS = ("left", "right")
LUMA_EVERY = 30              # frames between luminance samples
#: With both hands in one picture MediaPipe can lock onto one and never find
#: the other: on 2026-09-30 a flat hand seen from a low camera was found in 0
#: of 1,202 frames of a hold, and in every frame once its half of the picture
#: was searched alone. Each half is widened by this share of the width.
HALF_OVERLAP = 0.125
#: A half-frame hand whose wrist lies this close (share of the width) to the
#: other hand's is the same hand found twice, and is dropped.
DUP_MIN = 0.08
#: A hand MediaPipe loses for less than this is still the same resting hand:
#: the flow keeps tracking its own points, and trust is not broken. Longer,
#: and the hold splits there as before.
DROPOUT_MAX_S = 1.0


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


def detect_half(rgb, side: str, detect_one, ts_ms: int, other=None):
    """Look for one hand in its own half of the picture (selfie view: the
    person's left hand is on the picture's left). Returns 21 landmarks in
    full-frame normalised coordinates, or None."""
    h, w = rgb.shape[:2]
    if side == "left":
        x0, x1 = 0, int(round(w * (0.5 + HALF_OVERLAP)))
    else:
        x0, x1 = int(round(w * (0.5 - HALF_OVERLAP))), w
    res = detect_one(np.ascontiguousarray(rgb[:, x0:x1]), ts_ms)
    found = getattr(res, "hand_landmarks", None) or []
    if not found:
        return None
    cw = x1 - x0
    lms = [SimpleNamespace(x=(p.x * cw + x0) / w, y=p.y, z=getattr(p, "z", 0.0))
           for p in found[0]]
    wx = lms[0].x
    if (side == "left" and wx > 0.5 + HALF_OVERLAP) or \
            (side == "right" and wx < 0.5 - HALF_OVERLAP):
        return None
    if other is not None and abs(other[0].x - wx) < DUP_MIN \
            and abs(other[0].y - lms[0].y) < DUP_MIN:
        return None                      # the other hand, found again
    return lms


def analyse_take(take: Take, detect, window: tuple[float, float],
                 move_max: float, hands=HANDS, on_frame=None,
                 side_detect: dict | None = None) -> dict:
    """Measure one hold from its recorded frames.

    detect      : (rgb uint8 array, ts_ms int) -> a HandLandmarker result
    window      : (t0, t1) scored window on the Take's clock (settle excluded)
    on_frame    : called after every frame (progress, and the pause point)
    side_detect : {"left"|"right": single-hand detect}, for a hand the whole
                  frame missed (detect_half); None skips the fallback
    """
    w0, w1 = window
    mon = {h: framing.FramingMonitor() for h in hands}
    flows = {h: HandFlow() for h in hands}
    scene = SceneFlow()
    scene_pos = np.zeros(2)
    scene_track = {"t": [], "xy": []}
    smooth = {h: LandmarkSmoother() for h in hands}
    last_geo = {h: None for h in hands}
    half_n = {h: 0 for h in hands}
    bridged_n = {h: 0 for h in hands}
    lm_prev = {h: None for h in hands}
    lm_steps = {h: [] for h in hands}           # raw landmark jitter, % hand
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
        rgb = preprocess_for_mediapipe(frame)
        found = assign_hands(detect(rgb, ms), hands)
        if side_detect:
            for h in hands:
                if h not in found and h in side_detect:
                    other = next((v for k, v in found.items() if k != h), None)
                    lms_h = detect_half(rgb, h, side_detect[h], ms, other)
                    if lms_h is not None:
                        found[h] = lms_h
                        if w0 <= t <= w1:
                            half_n[h] += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if i % LUMA_EVERY == 0:
            luma.append(float(gray[::8, ::8].mean()))
        in_win = w0 <= t <= w1

        # geometry first, for every hand: the scene must keep clear of both
        geos, raws, pxs, bridging = {}, {}, {}, {}
        for h in hands:
            lms = found.get(h)
            raw = [(p.x, p.y) for p in lms] if lms else None
            px = [(x * fw, y * fh) for x, y in raw] if raw else None
            # geometry from the smoothed hand: on a flat hand MediaPipe's
            # guesses move 1-2 % of the hand length every frame, and the mask
            # must not move with them. The flow itself reads the image.
            geo = smooth[h].update(t, px)
            if px is not None and geo is not None:
                last_geo[h] = geo.tolist()
            seen = smooth[h].last_seen
            bridging[h] = (raw is None and seen is not None
                           and t - seen <= DROPOUT_MAX_S)
            if raw is not None or not bridging[h]:
                mon[h].update(raw, t)       # a short dropout keeps its trust
            geos[h] = last_geo[h] if (px is not None or bridging[h]) else None
            raws[h], pxs[h] = raw, px
        s = scene.update(gray, t, [g for g in geos.values() if g is not None])
        if s is not None:
            scene_pos = np.array(s[1:])
            if in_win:
                scene_track["t"].append(t)
                scene_track["xy"].append(tuple(scene_pos))

        for h in hands:
            raw, px, geo = raws[h], pxs[h], geos[h]
            # during a dropout the flow tracks its own points, unfenced
            sample = flows[h].update(gray, t, geo if raw is not None else None)
            if in_win and raw is None and bridging[h] and not mon[h].untrusted \
                    and sample is not None and geo is not None:
                length = tm.hand_length(geo)
                if length:
                    bridged_n[h] += 1
                    fl[h]["t"].append(sample[0])
                    fl[h]["xy"].append((sample[1], sample[2]))
            if not in_win or raw is None:
                lm_prev[h] = None
                continue
            ln = tm.hand_length(geo)
            if lm_prev[h] is not None and ln:
                (x0, y0), (x1, y1) = lm_prev[h], px[tm.HAND_LEN_TO]
                lm_steps[h].append(100.0 * float(np.hypot(x1 - x0, y1 - y0)) / ln)
            lm_prev[h] = px[tm.HAND_LEN_TO]
            all_frames += 1
            if mon[h].level == framing.CLIPPED:
                clip_frames += 1
            if mon[h].untrusted:
                continue
            length = tm.hand_length(geo)
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

    def flow_cell(track, scale):
        if len(track["t"]) < 8:
            return None
        return tm.analyse_hand(track["t"], [[xy] for xy in track["xy"]],
                               [scale] * len(track["t"]), move_max=move_max,
                               instrument="flow", exact_times=True)

    cells, landmark_cells = {}, {}
    scales = [sorted(lm[h]["len"])[len(lm[h]["len"]) // 2] for h in hands if lm[h]["len"]]
    # the scene in the hands' units, so its shake reads beside their tremor
    scene_cell = flow_cell(scene_track, float(np.median(scales))) if scales else None
    for h in hands:
        d, f = lm[h], fl[h]
        lm_cell = tm.analyse_hand(d["t"], d["pts"], d["len"], move_max=move_max,
                                  exact_times=True, despike_spikes=True,
                                  instrument="landmarks")
        landmark_cells[h] = lm_cell
        cell = None
        if len(f["t"]) >= 8 and d["len"]:
            # one hand length from MediaPipe scales the flow, as it scales
            # the landmarks, so both read in % of hand length
            scale = sorted(d["len"])[len(d["len"]) // 2]
            cell = tm.analyse_hand(f["t"], [[xy] for xy in f["xy"]],
                                   [scale] * len(f["t"]), move_max=move_max,
                                   instrument="flow",
                                   exact_times=True)
        if cell and cell.get("scored"):
            cell["method"] = "offline_flow"
        else:
            cell = dict(lm_cell, method="offline_landmarks")
        # how much MediaPipe was re-guessing this hand, and how much lap the
        # old convex-hull mask would have mixed in (TREMOR_TEST_PLAN.md §3c)
        cell["lm_step_pct"] = (round(float(np.median(lm_steps[h])), 3)
                               if lm_steps[h] else None)
        cell["hull_extra_pct"] = (round(100.0 * flows[h].hull_extra, 1)
                                  if flows[h].hull_extra is not None else None)
        n_win = max(1, len(f["t"]))
        cell["half_frame_pct"] = round(100.0 * half_n[h] / max(1, len(d["t"]) + bridged_n[h]), 1)
        cell["bridged_pct"] = round(100.0 * bridged_n[h] / n_win, 1)
        # the camera's own shake, in the same units: a hand peak at the
        # scene's frequency and size is the camera, not the hand
        if scene_cell and scene_cell.get("scored"):
            cell["scene_amp_pct"] = scene_cell["amp_pct"]
            cell["scene_peak_hz"] = scene_cell["peak_hz"]
        cells[h] = cell

    stats = drop_stats(take.t)
    stats.update(device_clock=take.device_clock, overflow=take.overflow,
                 luminance=round(float(np.mean(luma)), 1) if luma else None)
    return {"cells": cells, "landmark_cells": landmark_cells, "lm": lm,
            "flow": fl, "scene": scene_track, "all_frames": all_frames,
            "clip_frames": clip_frames, "stats": stats}


class _HandedOver(Exception):
    """Raised inside a hold's analysis when OfflineAnalyser.hand_over() asks
    for the work back; never escapes the analyser."""


class OfflineAnalyser(threading.Thread):
    """Works through submitted holds in the background.

    Paused while a hold is recording (pause()/resume()), so it never competes
    with the capture it is analysing the output of. Each hold gets a fresh
    landmarker from `make_detect()` -> (detect, close) or (detect, close,
    side_detect) for the half-frame fallback: VIDEO mode keeps
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
        self._cancel = False             # hand_over(): abandon work, keep frames
        self._handed: list = []          # jobs abandoned mid-way, frames intact
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
        if self._cancel:
            raise _HandedOver

    def hand_over(self, timeout: float = 15.0) -> list | None:
        """Stop working and give back every hold not yet measured, as
        (key, take, window, move_max) with its frames intact, so another
        process can finish them (core/pending.py). Finished holds stay in
        `results`/`errors`. The thread exits.

        None if the hold being measured did not stop within `timeout` (it
        stops at its next frame, so this means something hung): the analyser
        is then left running with every job it had, as if never asked."""
        drained = []
        with self._lock:
            self._cancel = True
            while True:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if job is None:
                    continue
                drained.append(job)
                self._pending -= 1
                self.total_frames -= len(job[1])
        self._go.set()
        end = time.monotonic() + timeout
        while not self.idle() and time.monotonic() < end:
            time.sleep(0.01)
        with self._lock:
            if self._pending:                # stuck: undo, carry on here
                self._cancel = False
                for job in self._handed + drained:
                    self._pending += 1
                    self.total_frames += len(job[1])
                    self._jobs.put(job)
                self._handed = []
                return None
            left, self._handed = self._handed + drained, []
        self._jobs.put(None)
        return sorted(left, key=lambda j: j[1].t[0] if j[1].t else 0.0)

    def run(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            key, take, window, move_max = job
            n = len(take)
            done_before = self.done_frames
            close = None
            handed = False
            try:
                self._go.wait()
                if self._cancel:
                    raise _HandedOver
                if self.keep_dir is not None:
                    try:
                        save_take(take, self.keep_dir / key)
                    except OSError as e:
                        self.errors[f"{key}:keep"] = str(e)
                made = self.make_detect()
                detect, close = made[0], made[1]
                side = made[2] if len(made) > 2 else None
                self.results[key] = analyse_take(take, detect, window, move_max,
                                                 self.hands, on_frame=self._tick,
                                                 side_detect=side)
            except _HandedOver:
                handed = True
            except Exception as e:  # noqa: BLE001 - a hold falls back, never crashes
                self.errors[key] = f"{type(e).__name__}: {e}"
            finally:
                if close is not None:
                    try:
                        close()
                    except Exception:  # noqa: BLE001
                        pass
                with self._lock:
                    if handed and not self._cancel:
                        # hand_over() gave up and took the request back just
                        # as this hold saw it: start the hold again (still
                        # pending, so _pending is left alone)
                        self.done_frames = done_before
                        self._jobs.put(job)
                    elif handed:
                        # frames kept for whoever finishes it
                        self._handed.append(job)
                        self.done_frames = done_before
                        self.total_frames -= n
                        self._pending -= 1
                    else:
                        take.free()
                        # a failed hold still counts as done for the progress bar
                        self.done_frames = done_before + n
                        self._pending -= 1

    def stop(self):
        self._stop = True
        self._go.set()
        self._jobs.put(None)
        if self.is_alive():
            self.join(timeout=2.0)
