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

SceneFlow tracks everything that is neither hand nor forearm: the camera's
own shake, reported beside each hand so a peak it shares can be recognised.

Pure apart from OpenCV. Unit-tested on synthetic video in
screening_tests/tests/test_tremor_flow.py; used by core/tremor/offline.py.
Plan: TREMOR_TEST_PLAN.md §3a, §3c.
"""

from __future__ import annotations

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
#: Hand-shaped region (hand_shape_mask): the palm polygon plus a capsule along
#: each finger's bones, this share of the hand length wide. The convex hull it
#: replaced also covers whatever lies between spread fingers -- on a flat hand
#: in the lap, the lap -- and still points there pull the median motion toward
#: zero (TREMOR_TEST_PLAN.md §3c).
FINGER_WIDTH_FRAC = 0.12
#: Seeds go this far inside the hand shape. A tracked point's LK window
#: (LK_WIN, 21 px) is wider than a flat finger seen from lap distance
#: (~0.12 x ~110 px), so a point on a finger also sees the still lap around it
#: and under-reads the motion. On a spread synthetic hand over a textured lap,
#: a 5 Hz tremor read 76 % of its true amplitude through the old convex hull,
#: 88-90 % through the hand shape inset 0.02, and 92-97 % inset 0.05-0.06,
#: which leaves mostly the palm and the back of the hand; fingers are tracked
#: only when the camera is close enough for them to be wider than the window.
SEED_INSET_FRAC = 0.05
PALM = (0, 1, 5, 9, 13, 17)
FINGERS = ((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16),
           (17, 18, 19, 20))
#: LandmarkSmoother window. A resting hand does not move in this long, and
#: tremor is never read from the smoothed points -- they only place the mask,
#: which MediaPipe's per-frame guesses on a flat hand (1-2 % of the hand length
#: every frame, 2026-09-30) would otherwise shake.
SMOOTH_S = 0.3
#: SceneFlow. A camera resting on a bed or a loose mount shakes the whole
#: picture: on 2026-09-30 the wall and shelves of Adam's recordings showed a
#: clean 5.3-5.7 Hz peak (0.01-0.03 % of the hand length) in every hold, the
#: same peak both of his still hands had. It is MEASURED, not subtracted:
#: subtracting it was tried on those recordings and did not remove the still
#: hands' peak (a camera that bounces sees near and far things move by
#: different amounts), while in the tremor run the scene shook four times
#: harder (0.08 %) because the trembling hands shook the bed -- subtracting
#: would have eaten the tremor. Scene points stay clear of each hand and of
#: its forearm, which moves with a tremor.
SCENE_POINTS = 80
SCENE_MIN = 20
SCENE_HAND_CLEAR = 0.5          # hand lengths kept clear round each hand
SCENE_ARM_LEN = 2.5             # forearm exclusion, from the wrist, hand lengths
SCENE_ARM_W = 0.8
SCENE_BORDER_PX = 8
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


def _morph(mask, grow_px: float) -> np.ndarray:
    k = int(round(abs(grow_px)))
    if not k:
        return mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    return (cv2.dilate if grow_px > 0 else cv2.erode)(mask, kernel)


def hand_shape_mask(shape, pts_px, grow_px: float = 0.0,
                    width_frac: float = FINGER_WIDTH_FRAC) -> np.ndarray:
    """uint8 mask of the hand itself: the palm polygon plus a capsule along
    each finger, grown by `grow_px` (shrunk if negative). Falls back to the
    convex hull for anything but 21 points."""
    pts = np.asarray(pts_px, np.float32)
    if len(pts) != 21:
        return hand_mask(shape, pts_px, grow_px)
    h, w = shape[:2]
    mask = np.zeros((h, w), np.uint8)
    palm = cv2.convexHull(pts[list(PALM)]).astype(np.int32)
    cv2.fillConvexPoly(mask, palm, 255)
    thick = max(1, int(round(width_frac * _length(pts))))
    for chain in FINGERS:
        for a, b in zip(chain, chain[1:]):
            cv2.line(mask, tuple(int(v) for v in pts[a]), tuple(int(v) for v in pts[b]),
                     255, thick, lineType=cv2.LINE_8)
    return _morph(mask, grow_px)


def hull_extra_frac(shape, pts_px) -> float | None:
    """Share of the convex hull that is not hand: what the old mask added."""
    if pts_px is None or len(pts_px) != 21:
        return None
    hull = hand_mask(shape, pts_px, 0) > 0
    n = int(hull.sum())
    if not n:
        return None
    return float((hull & ~(hand_shape_mask(shape, pts_px) > 0)).sum() / n)


class LandmarkSmoother:
    """Per-point median of the last SMOOTH_S of landmark detections, for the
    geometry only (where the hand is, how long it is). Call ``update(t, pts)``
    with each frame's 21 points or None; returns the smoothed points, or None
    while nothing has been seen for SMOOTH_S."""

    def __init__(self, window_s: float = SMOOTH_S):
        self.window_s = window_s
        self.buf: deque = deque()

    last_seen: float | None = None       # time of the last real detection

    def update(self, t: float, pts_px):
        if pts_px is not None:
            self.buf.append((t, np.asarray(pts_px, np.float32)))
            self.last_seen = t
        while self.buf and t - self.buf[0][0] > self.window_s:
            self.buf.popleft()
        if not self.buf:
            return None
        return np.median(np.stack([p for _, p in self.buf]), axis=0)


def _length(pts_px) -> float:
    """Wrist -> middle knuckle, the engine's hand length (metrics.hand_length)."""
    p = np.asarray(pts_px, float)
    return float(np.hypot(*(p[9] - p[0]))) if len(p) > 9 else 0.0


def _track(prev, gray, p0):
    """Pyramidal LK forward and back: (new points, mask of points that came
    home within FB_MAX_PX), or (None, None)."""
    p1, st1, _ = cv2.calcOpticalFlowPyrLK(prev, gray, p0, None, winSize=LK_WIN,
                                          maxLevel=LK_LEVELS, criteria=LK_CRIT)
    if p1 is None:
        return None, None
    pb, st2, _ = cv2.calcOpticalFlowPyrLK(gray, prev, p1, None, winSize=LK_WIN,
                                          maxLevel=LK_LEVELS, criteria=LK_CRIT)
    fb = np.linalg.norm((pb - p0).reshape(-1, 2), axis=1)
    return p1, (st1.ravel() == 1) & (st2.ravel() == 1) & (fb < FB_MAX_PX)


def _inside(mask, pts) -> np.ndarray:
    h, w = mask.shape
    xy = pts.reshape(-1, 2)
    xi = np.clip(xy[:, 0].astype(int), 0, w - 1)
    yi = np.clip(xy[:, 1].astype(int), 0, h - 1)
    return mask[yi, xi] > 0


def scene_mask(shape, hands_px) -> np.ndarray:
    """Where the scene may be tracked: the frame, less a border, less each
    hand (grown SCENE_HAND_CLEAR hand lengths) and its forearm."""
    h, w = shape[:2]
    mask = np.zeros((h, w), np.uint8)
    b = SCENE_BORDER_PX
    mask[b:h - b, b:w - b] = 255
    for pts in hands_px:
        pts = np.asarray(pts, np.float32)
        ln = _length(pts)
        if ln <= 0:
            continue
        mask[hand_shape_mask(shape, pts, SCENE_HAND_CLEAR * ln) > 0] = 0
        u = pts[0] - pts[9]
        u = u / (float(np.linalg.norm(u)) or 1.0)
        end = pts[0] + u * SCENE_ARM_LEN * ln
        cv2.line(mask, tuple(int(v) for v in pts[0]), tuple(int(v) for v in end), 0,
                 max(1, int(SCENE_ARM_W * ln)))
    return mask


class SceneFlow:
    """The picture's own motion (camera shake), integrated from optical flow
    on everything that is not a hand or forearm. ``update(gray, t, hands)``
    with the hands' 21-point geometry each frame; returns (t, x, y) in
    pixels, or None. It seeds only once at least one hand is known, so it
    always knows what to keep clear of."""

    def __init__(self):
        self.prev = None
        self.pts = np.empty((0, 1, 2), np.float32)
        self.pos = np.zeros(2)

    def _seed(self, gray, hands, keep=None):
        mask = scene_mask(gray.shape, hands)
        if keep is not None:
            for x, y in keep.reshape(-1, 2):
                cv2.circle(mask, (int(x), int(y)), 7, 0, -1)
        want = SCENE_POINTS - (0 if keep is None else len(keep))
        new = cv2.goodFeaturesToTrack(gray, maxCorners=max(1, want), qualityLevel=0.01,
                                      minDistance=7, mask=mask)
        new = np.empty((0, 1, 2), np.float32) if new is None else new.astype(np.float32)
        return new if keep is None or not len(keep) else np.concatenate([keep, new])

    def update(self, gray, t: float, hands=()):
        hands = [h for h in hands if h is not None]
        if self.prev is None or not len(self.pts):
            if hands:
                self.pts = self._seed(gray, hands)
            self.prev = gray
            return None
        p1, good = _track(self.prev, gray, self.pts)
        sample = None
        if p1 is None:
            self.pts = np.empty((0, 1, 2), np.float32)
        else:
            if hands:                   # a hand moved onto a scene point
                good &= _inside(scene_mask(gray.shape, hands), p1)
            if good.sum() >= MIN_GOOD:
                self.pos += np.median((p1 - self.pts).reshape(-1, 2)[good], axis=0)
                sample = (t, float(self.pos[0]), float(self.pos[1]))
            self.pts = p1[good].reshape(-1, 1, 2)
        if len(self.pts) < SCENE_MIN and hands:
            self.pts = self._seed(gray, hands, keep=self.pts if len(self.pts) else None)
        self.prev = gray
        return sample


class HandFlow:
    """One hand's position, integrated from optical flow.

    Call ``update(gray, t, seeds)`` on every frame. ``seeds`` is the latest
    21 MediaPipe landmarks in pixels (or None) -- it only has to be fresh,
    not from this frame. Returns (t, x, y) in pixels, or None for a frame that
    could not be measured (a gap, which the engine splits on)."""

    def __init__(self, shape: bool = True):
        self.shape = shape           # False: the convex hull (engines 1-3)
        self.prev = None
        self.pts = np.empty((0, 1, 2), np.float32)
        self.pos = np.zeros(2)
        self.gaps = 0
        self.frames = 0
        self.hull_extra = None       # diagnostic, from the first seeding

    def reset(self):
        self.__init__(self.shape)

    def _mask(self, shape, seeds, grow_px):
        return (hand_shape_mask if self.shape else hand_mask)(shape, seeds, grow_px)

    def _seed(self, gray, seeds, keep=None):
        if self.hull_extra is None:
            self.hull_extra = hull_extra_frac(gray.shape, seeds)
        inset = SEED_INSET_FRAC if self.shape else HULL_MARGIN
        mask = self._mask(gray.shape, seeds, -inset * _length(seeds))
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
        p1, good = _track(self.prev, gray, p0)
        if p1 is None:
            self.pts = np.empty((0, 1, 2), np.float32)
            self.prev = gray
            self.gaps += 1
            return None
        if fresh and good.any():
            fence = self._mask(gray.shape, seeds, HULL_MARGIN * _length(seeds))
            good &= _inside(fence, p1)

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
