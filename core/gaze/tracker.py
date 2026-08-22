"""
Face Landmarker wrapper → smoothed horizontal gaze signal
(OCULOMOTOR_TEST_PLAN.md §3.1).

Per eye, the horizontal gaze proxy is the iris-center x expressed relative to
the two eye-corner x's, so it is invariant to head translation:

    ratio_eye = (iris_x − corner_min_x) / (corner_max_x − corner_min_x)

Using min/max of the corners (rather than inner/outer) makes both eyes' ratios
increase toward image-right, so they can be averaged directly. The averaged
ratio is One-Euro smoothed; the calibration layer (calibrate.py) maps it to a
signed screen position, so no left/right convention is assumed here.

A vertical proxy (`ratio_y`) is also emitted: iris-y relative to the eye's
lid-midpoint, normalised by the *same* eye width so both axes share a unit and
the two eyes can be averaged. It is uncalibrated (the 3-point calibration is
horizontal-only) and noisier — used only as a relative spread signal for the
fixation-stability BCEA (see core/gaze/fixation.py), never for saccades.

Blinks are guarded: when either eye's openness drops below a threshold the
iris landmarks are unreliable, and the sample's `ratio` is None (face still
tracked — the caller distinguishes "no face" from "blink").
"""

from __future__ import annotations

from dataclasses import dataclass

import mediapipe as mp

from core.hand_utils import OneEuroFilter

# MediaPipe Face Landmarker (refined) landmark indices.
_RIGHT_IRIS_CENTER = 468
_LEFT_IRIS_CENTER = 473
_RIGHT_EYE_CORNERS = (33, 133)     # outer, inner
_LEFT_EYE_CORNERS = (362, 263)     # inner, outer
_RIGHT_EYE_LIDS = (159, 145)       # upper, lower
_LEFT_EYE_LIDS = (386, 374)

BLINK_OPENNESS = 0.14              # lid gap / eye width below this = blink


@dataclass
class GazeSample:
    ratio: float | None            # smoothed averaged iris ratio (horizontal); None on blink
    ratio_raw: float | None
    ratio_y: float | None          # smoothed averaged vertical iris proxy; None on blink
    ratio_y_raw: float | None
    blink: bool
    iris_px: list[tuple[int, int]]      # both iris centers, pixel coords
    corners_px: list[tuple[int, int]]   # all four eye corners, pixel coords


def _eye_ratios(lms, iris_i: int, corners: tuple[int, int],
                lids: tuple[int, int]
                ) -> tuple[float | None, float | None, bool]:
    """(rx, ry, blink) for one eye; rx/ry None if degenerate or blinking.
    rx = horizontal iris position as a fraction of eye width (→ image-right).
    ry = vertical iris offset from the lid midpoint, in the same eye-width
    units (→ image-down), so the 2-D cloud is isotropic and eye-averageable."""
    c1, c2 = lms[corners[0]], lms[corners[1]]
    lo, hi = min(c1.x, c2.x), max(c1.x, c2.x)
    width = hi - lo
    if width < 1e-4:
        return None, None, False
    upper, lower = lms[lids[0]], lms[lids[1]]
    openness = abs(upper.y - lower.y) / width
    if openness < BLINK_OPENNESS:
        return None, None, True
    iris = lms[iris_i]
    rx = (iris.x - lo) / width
    ry = (iris.y - (upper.y + lower.y) / 2) / width
    return rx, ry, False


class GazeTracker:
    """Face Landmarker (VIDEO mode) → per-frame GazeSample or None (no face)."""

    def __init__(self, model_path: str,
                 min_cutoff: float = 1.5, beta: float = 0.6):
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self._filter = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self._filter_y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self._had_face = False

    def detect(self, rgb_frame, now: float,
               frame_w: int, frame_h: int) -> GazeSample | None:
        """Run detection on an RGB frame. Returns None when no face is found."""
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        if not result.face_landmarks:
            if self._had_face:
                self._filter.reset()       # don't smooth across a tracking gap
                self._filter_y.reset()
                self._had_face = False
            return None
        self._had_face = True
        lms = result.face_landmarks[0]

        r_x, r_y, r_blink = _eye_ratios(lms, _RIGHT_IRIS_CENTER,
                                        _RIGHT_EYE_CORNERS, _RIGHT_EYE_LIDS)
        l_x, l_y, l_blink = _eye_ratios(lms, _LEFT_IRIS_CENTER,
                                        _LEFT_EYE_CORNERS, _LEFT_EYE_LIDS)
        blink = r_blink or l_blink

        iris_px = [(int(lms[i].x * frame_w), int(lms[i].y * frame_h))
                   for i in (_RIGHT_IRIS_CENTER, _LEFT_IRIS_CENTER)]
        corners_px = [(int(lms[i].x * frame_w), int(lms[i].y * frame_h))
                      for i in _RIGHT_EYE_CORNERS + _LEFT_EYE_CORNERS]

        xs = [r for r in (r_x, l_x) if r is not None]
        ys = [r for r in (r_y, l_y) if r is not None]
        if blink or not xs:
            return GazeSample(None, None, None, None, blink, iris_px, corners_px)
        raw_x = sum(xs) / len(xs)
        raw_y = sum(ys) / len(ys)
        return GazeSample(self._filter.filter(raw_x, now), raw_x,
                          self._filter_y.filter(raw_y, now), raw_y, False,
                          iris_px, corners_px)

    def close(self) -> None:
        self.landmarker.close()
