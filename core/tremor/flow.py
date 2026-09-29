"""
Hand motion from optical flow, on every camera frame.

Why this exists: the tremor test's frame rate is set by MediaPipe, not the
camera. A 60 fps camera still yields ~16 scored frames a second on a busy
laptop (docs/performance/FPS_FINDINGS.md), which caps the band at ~7-8 Hz and
leaves each landmark's regression jitter (0.1-0.8 % of hand length at rest,
up to 3.4 % arms out) as the noise floor. Optical flow is cheap enough to run
on every frame, and a median over a few dozen skin-texture points moves by
fractions of a pixel, not by what a neural net guesses each frame.

So the work is split:

  MediaPipe (as often as it can)  where each hand is -> seeds the points,
                                  trust/framing, hand length for the scale
  HandFlow (every frame)          how the hand moved since the last frame

Signal: frame-to-frame displacement of the tracked points, median over the
points (robust to a few that slide onto the background or a moving finger),
summed into a position. Summing increments rather than averaging positions is
what makes re-seeding free: a point contributes only while it is tracked in
both frames, so points can be dropped and added without a jump in the trace.
The integration drifts as a slow random walk (LK error ~0.02-0.05 px a frame),
which the engine's detrend and <1 Hz movement gate already treat as posture.

Every point is checked forward and backward (Kalal 2010): track it to the new
frame and back again, and drop it if it does not come home. Points that leave
the hand -- the region MediaPipe last saw it in -- are dropped too.

Pure apart from OpenCV. HandFlow is unit-tested on synthetic video in
screening_tests/tests/test_tremor_flow.py; FlowCamera is the thread that owns
the capture in screening_tests/tremor_test.py. Plan: TREMOR_TEST_PLAN.md §3a.
"""

from __future__ import annotations

import threading
import time
from collections import deque

import cv2
import numpy as np

# ── Tracking constants ──────────────────────────────────────────────────────
MAX_POINTS = 60          # points seeded per hand
MIN_POINTS = 12          # below this, top up from the hand region
MIN_GOOD = 6             # fewer survivors than this and the frame is a gap
FB_MAX_PX = 0.5          # forward-backward disagreement that drops a point
SEED_QUALITY = 0.01      # goodFeaturesToTrack quality level
SEED_MIN_DIST = 5        # px between seeded points
SEED_MAX_AGE_S = 0.25    # landmarks older than this do not seed or fence
HULL_MARGIN = 0.08       # fence grows by this share of the hand length
LK_WIN = (21, 21)
LK_LEVELS = 3
LK_CRIT = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)


def hand_mask(shape, pts_px, grow_px: float) -> np.ndarray:
    """uint8 mask of the landmarks' convex hull, grown by `grow_px` (or
    shrunk, if negative)."""
    h, w = shape[:2]
    mask = np.zeros((h, w), np.uint8)
    pts = np.asarray(pts_px, np.float32)
    if len(pts) < 3:
        return mask
    hull = cv2.convexHull(pts).astype(np.int32)
    cv2.fillConvexPoly(mask, hull, 255)
    k = int(round(abs(grow_px)))
    if k:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        mask = (cv2.dilate if grow_px > 0 else cv2.erode)(mask, kernel)
    return mask


def _length(pts_px) -> float:
    """Wrist -> middle knuckle, the engine's hand length (metrics.hand_length)."""
    p = np.asarray(pts_px, float)
    return float(np.hypot(*(p[9] - p[0]))) if len(p) > 9 else 0.0


class HandFlow:
    """One hand's position, integrated from optical flow.

    Call ``update(gray, t, seeds)`` on every frame. ``seeds`` is the latest
    21 MediaPipe landmarks in pixels (or None) -- it only has to be fresh,
    not from this frame. Returns (t, x, y) in pixels, or None for a frame that
    could not be measured (a gap, which the engine splits on)."""

    def __init__(self):
        self.prev = None
        self.pts = np.empty((0, 1, 2), np.float32)
        self.pos = np.zeros(2)
        self.gaps = 0
        self.frames = 0

    def reset(self):
        self.__init__()

    def _seed(self, gray, seeds, keep=None):
        grow = -HULL_MARGIN * _length(seeds)          # inside the hand only
        mask = hand_mask(gray.shape, seeds, grow)
        if keep is not None and len(keep):
            for x, y in keep.reshape(-1, 2):          # leave room round kept points
                cv2.circle(mask, (int(x), int(y)), SEED_MIN_DIST, 0, -1)
        want = MAX_POINTS - (0 if keep is None else len(keep))
        if want <= 0:
            return keep
        new = cv2.goodFeaturesToTrack(gray, maxCorners=want, qualityLevel=SEED_QUALITY,
                                      minDistance=SEED_MIN_DIST, mask=mask)
        if new is None:
            return keep if keep is not None else np.empty((0, 1, 2), np.float32)
        new = new.astype(np.float32)
        return new if keep is None or not len(keep) else np.concatenate([keep, new])

    def update(self, gray, t: float, seeds=None):
        self.frames += 1
        fresh = seeds is not None and len(seeds) >= 10
        if self.prev is None or not len(self.pts):
            if fresh:
                self.pts = self._seed(gray, seeds)
            self.prev = gray
            return None

        p0 = self.pts
        p1, st1, _ = cv2.calcOpticalFlowPyrLK(self.prev, gray, p0, None, winSize=LK_WIN,
                                              maxLevel=LK_LEVELS, criteria=LK_CRIT)
        if p1 is None:
            self.pts = np.empty((0, 1, 2), np.float32)
            self.prev = gray
            self.gaps += 1
            return None
        pb, st2, _ = cv2.calcOpticalFlowPyrLK(gray, self.prev, p1, None, winSize=LK_WIN,
                                              maxLevel=LK_LEVELS, criteria=LK_CRIT)
        fb = np.linalg.norm((pb - p0).reshape(-1, 2), axis=1)
        good = (st1.ravel() == 1) & (st2.ravel() == 1) & (fb < FB_MAX_PX)
        if fresh and good.any():
            fence = hand_mask(gray.shape, seeds, HULL_MARGIN * _length(seeds))
            h, w = fence.shape
            xy = p1.reshape(-1, 2)
            xi = np.clip(xy[:, 0].astype(int), 0, w - 1)
            yi = np.clip(xy[:, 1].astype(int), 0, h - 1)
            good &= fence[yi, xi] > 0

        sample = None
        if good.sum() >= MIN_GOOD:
            d = (p1 - p0).reshape(-1, 2)[good]
            self.pos += np.median(d, axis=0)
            sample = (t, float(self.pos[0]), float(self.pos[1]))
        else:
            self.gaps += 1

        self.pts = p1[good].reshape(-1, 1, 2)
        if len(self.pts) < MIN_POINTS and fresh:
            self.pts = self._seed(gray, seeds, keep=self.pts)
        self.prev = gray
        return sample


class FlowCamera(threading.Thread):
    """Owns the capture: reads every frame, flips it to selfie view, runs
    HandFlow for each hand on it, and hands the newest frame to the UI.

    OpenCV releases the GIL inside read() and calcOpticalFlowPyrLK, so this
    runs beside MediaPipe on the main thread rather than taking turns with it.
    """

    def __init__(self, cap, hands=("left", "right"), flip=True):
        super().__init__(daemon=True, name="flow-camera")
        self.cap = cap
        self.flip = flip
        self.flows = {h: HandFlow() for h in hands}
        self._seeds: dict[str, tuple] = {}
        self._samples = {h: deque() for h in hands}
        self._lock = threading.Lock()
        self._new = threading.Condition(self._lock)
        self._frame = None
        self._frame_t = 0.0
        self._seq = 0
        self._stop = threading.Event()
        self.fps = 0.0
        self.error: str | None = None

    # ── thread side ──
    def run(self):
        last = None
        while not self._stop.is_set():
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.005)
                continue
            t = time.time()
            if self.flip:
                frame = cv2.flip(frame, 1)
            if last is not None:
                dt = max(1e-4, t - last)
                self.fps = (1.0 / dt) if self.fps == 0 else 0.95 * self.fps + 0.05 / dt
            last = t
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            with self._lock:
                seeds = dict(self._seeds)
            for h, fl in self.flows.items():
                s = seeds.get(h)
                pts = s[0] if s and t - s[1] <= SEED_MAX_AGE_S else None
                try:
                    out = fl.update(gray, t, pts)
                except cv2.error as e:     # never let one bad frame end the run
                    self.error = str(e)
                    fl.reset()
                    out = None
                if out is not None:
                    with self._lock:
                        self._samples[h].append(out)
            with self._new:
                self._frame, self._frame_t, self._seq = frame, t, self._seq + 1
                self._new.notify_all()

    # ── UI side ──
    def next_frame(self, after_seq: int, timeout: float = 1.0):
        """(seq, t, frame) of the newest frame after `after_seq`, or None.
        `t` is when the frame was read, the clock the flow samples carry."""
        with self._new:
            if self._seq <= after_seq:
                self._new.wait(timeout)
            if self._seq <= after_seq or self._frame is None:
                return None
            return self._seq, self._frame_t, self._frame

    def set_seeds(self, hand: str, pts_px, t: float):
        with self._lock:
            if pts_px is None:
                self._seeds.pop(hand, None)
            else:
                self._seeds[hand] = (np.asarray(pts_px, np.float32), t)

    def drain(self) -> dict[str, list]:
        with self._lock:
            out = {h: list(q) for h, q in self._samples.items()}
            for q in self._samples.values():
                q.clear()
        return out

    def stop(self):
        self._stop.set()
        self.join(timeout=2.0)
