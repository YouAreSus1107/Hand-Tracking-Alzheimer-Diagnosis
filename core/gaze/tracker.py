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

Blinks are guarded per eye by an adaptive, per-person lid-openness gate
(openness.py): when an eye reads as closed its iris is dropped, and with no
usable eye the sample's `ratio` is None (face still tracked — the caller
distinguishes "no face" from "eyes not readable"). The gate is proportional to
each eye's own learned open aperture rather than a fixed number, so a narrow
palpebral fissure is not mistaken for a permanent blink; the sample carries
`open_frac` so the UI can show the person the same margin the gate is using.

Head pose (`head`, yaw/pitch in degrees) comes from the model's facial
transformation matrix and is carried even through a blink, since the head
does not stop turning when the lids close. It feeds the head-turn check
(headpose.py); it never touches the gaze ratio.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import quiet          # keep above mediapipe: silences its startup log
import mediapipe as mp

from core.hand_utils import OneEuroFilter
from core.gaze.headpose import angles as head_angles
from core.gaze.openness import OpennessGate

# MediaPipe Face Landmarker (refined) landmark indices.
_RIGHT_IRIS_CENTER = 468
_LEFT_IRIS_CENTER = 473
_RIGHT_EYE_CORNERS = (33, 133)     # outer, inner
_LEFT_EYE_CORNERS = (362, 263)     # inner, outer
_RIGHT_EYE_LIDS = (159, 145)       # upper, lower
_LEFT_EYE_LIDS = (386, 374)


@dataclass
class GazeSample:
    ratio: float | None            # smoothed averaged iris ratio (horizontal); None on blink
    ratio_raw: float | None
    ratio_y: float | None          # smoothed averaged vertical iris proxy; None on blink
    ratio_y_raw: float | None
    blink: bool
    iris_px: list[tuple[int, int]]      # both iris centers, pixel coords
    corners_px: list[tuple[int, int]]   # all four eye corners, pixel coords
    openness: float | None = None       # lid gap ÷ eye width, better eye
    open_frac: float | None = None      # openness ÷ that eye's open baseline
    narrow: bool = False                # their open aperture is a narrow one
    head: tuple[float, float] | None = None   # head (yaw, pitch), degrees


def _eye_ratios(lms, iris_i: int, corners: tuple[int, int],
                lids: tuple[int, int]
                ) -> tuple[float, float, float] | None:
    """(rx, ry, openness) for one eye, or None if the eye box is degenerate.

    rx = horizontal iris position as a fraction of eye width (→ image-right).
    ry = vertical iris offset from the lid midpoint, in the same eye-width
    units (→ image-down), so the 2-D cloud is isotropic and eye-averageable.
    openness = lid gap in those same units. Whether the eye is open enough to
    believe is not decided here — that is the per-eye OpennessGate's job."""
    c1, c2 = lms[corners[0]], lms[corners[1]]
    lo, hi = min(c1.x, c2.x), max(c1.x, c2.x)
    width = hi - lo
    if width < 1e-4:
        return None
    upper, lower = lms[lids[0]], lms[lids[1]]
    iris = lms[iris_i]
    return ((iris.x - lo) / width,
            (iris.y - (upper.y + lower.y) / 2) / width,
            abs(upper.y - lower.y) / width)


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
            output_facial_transformation_matrixes=True,
        )
        with quiet.muted_native_stderr():
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self._filter = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self._filter_y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self._gates = {"right": OpennessGate(), "left": OpennessGate()}
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
        mats = getattr(result, "facial_transformation_matrixes", None)
        head = head_angles(mats[0]) if mats else None

        eyes = {
            "right": _eye_ratios(lms, _RIGHT_IRIS_CENTER,
                                 _RIGHT_EYE_CORNERS, _RIGHT_EYE_LIDS),
            "left": _eye_ratios(lms, _LEFT_IRIS_CENTER,
                                _LEFT_EYE_CORNERS, _LEFT_EYE_LIDS),
        }
        xs: list[float] = []
        ys: list[float] = []
        states = []
        for side, measured in eyes.items():
            if measured is None:
                continue
            rx, ry, openness = measured
            st = self._gates[side].update(now, openness)
            states.append(st)
            xs.append(rx)
            ys.append(ry)
        # Every measurable eye must pass, and the ratio always averages the
        # same set of eyes. Dropping to one eye mid-run would be tempting for
        # asymmetric lids, but the two eyes' ratios carry slightly different
        # offsets (camera angle, corner-landmark bias), so switching sets
        # steps the signal by an amount comparable to the deadband — which the
        # detector would read as a saccade onset.
        limiting = min(states, key=lambda s: s.open_frac) if states else None
        eyes_open = bool(states) and all(s.open for s in states)
        blink = bool(states) and not eyes_open
        openness = limiting.openness if limiting else None
        open_frac = limiting.open_frac if limiting else None
        narrow = any(s.narrow for s in states) if states else False
        vertical_ok = eyes_open and all(s.vertical_ok for s in states)

        iris_px = [(int(lms[i].x * frame_w), int(lms[i].y * frame_h))
                   for i in (_RIGHT_IRIS_CENTER, _LEFT_IRIS_CENTER)]
        corners_px = [(int(lms[i].x * frame_w), int(lms[i].y * frame_h))
                      for i in _RIGHT_EYE_CORNERS + _LEFT_EYE_CORNERS]

        if not eyes_open:
            self._filter.reset()           # don't smooth across a lid closure
            self._filter_y.reset()
            return GazeSample(None, None, None, None, blink, iris_px,
                              corners_px, openness, open_frac, narrow, head)
        raw_x = sum(xs) / len(xs)
        raw_y = sum(ys) / len(ys)
        if not vertical_ok:
            self._filter_y.reset()
        return GazeSample(self._filter.filter(raw_x, now), raw_x,
                          self._filter_y.filter(raw_y, now) if vertical_ok
                          else None,
                          raw_y if vertical_ok else None, False,
                          iris_px, corners_px, openness, open_frac, narrow,
                          head)

    def close(self) -> None:
        self.landmarker.close()
