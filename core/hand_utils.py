"""
Hand tracking utilities shared by hand_tracking.py and finger_tapping.py.

Provides:
  HAND_CONNECTIONS          -- MediaPipe landmark connectivity list
  OneEuroFilter             -- adaptive low-pass filter (reduces jitter, preserves fast-motion fidelity)
  make_landmark_filters()   -- create a fresh (filters_x, filters_y) pair
  smooth_landmarks()        -- apply One-Euro filtering, return list of (x, y, z) tuples
  preprocess_for_mediapipe()-- CLAHE + sharpening to improve detection under varied lighting
  true_hand()               -- MediaPipe's handedness label -> the user's real hand
"""

import math
import cv2
import numpy as np

# ── Landmark connectivity ──────────────────────────────────────────────────
HAND_CONNECTIONS = [
    (0,1), (1,2), (2,3), (3,4),
    (0,5), (5,6), (6,7), (7,8),
    (5,9), (9,10), (10,11), (11,12),
    (9,13), (13,14), (14,15), (15,16),
    (13,17), (0,17), (17,18), (18,19), (19,20),
]

# ── Handedness ─────────────────────────────────────────────────────────────

def true_hand(category_name: str, selfie: bool) -> str:
    """The user's real hand ("left"/"right") from MediaPipe's handedness label.

    MediaPipe's docs say the label assumes a mirrored (selfie) picture. The
    Tasks HandLandmarker in use here does the opposite: on the picture as the
    camera sends it, the label already names the real hand. Verified
    2026-09-27 on a camera whose frames were confirmed unmirrored (printed
    text read normally): on the tests' selfie-flipped frame, 14/14 tapping and
    7/7 spiral runs by a right-dominant user had been saved as "left".

    So the label is the real hand on an unmirrored frame and the opposite one
    on a selfie-flipped frame. core/camera.open_capture() un-mirrors cameras
    that mirror their own picture, so "unmirrored" means every tool's raw read.
    """
    label = category_name.strip().lower()
    if not selfie:
        return label
    return {"left": "right", "right": "left"}.get(label, label)


# ── One-Euro Filter ────────────────────────────────────────────────────────

class OneEuroFilter:
    """
    Adaptive low-pass filter for scalar signals (e.g. a single landmark x or y).

    At rest (low velocity) the cutoff is low → heavy smoothing → jitter suppressed.
    During fast motion (high velocity) the cutoff rises → less lag → tap edges preserved.

    Tuned defaults for 30 fps finger-tap detection (light smoothing — preserves
    fast-tap minima and any real jitter/tremor the screening should capture):
      min_cutoff = 6.0 Hz  — smoothing at rest; increase if position still oscillates
      beta       = 1.5     — how fast cutoff rises with speed; increase to reduce tap lag
      d_cutoff   = 1.0 Hz  — derivative (velocity) filter cutoff, fixed
    """
    def __init__(self, min_cutoff: float = 6.0, beta: float = 1.5, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: float | None = None
        self._dx_prev: float = 0.0
        self._t_prev: float | None = None

    def _alpha(self, cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, timestamp: float) -> float:
        """Filter value x at the given timestamp (seconds). Returns smoothed value."""
        if self._t_prev is None:
            self._x_prev = x
            self._t_prev = timestamp
            return x
        dt = max(timestamp - self._t_prev, 1e-6)
        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self._x_prev
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = timestamp
        return x_hat

    def reset(self) -> None:
        """Clear filter state (call when tracking is interrupted or test phase changes)."""
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None


def make_landmark_filters() -> tuple[list[OneEuroFilter], list[OneEuroFilter]]:
    """Return (filters_x, filters_y) — one OneEuroFilter per landmark per axis."""
    return (
        [OneEuroFilter() for _ in range(21)],
        [OneEuroFilter() for _ in range(21)],
    )


def smooth_landmarks(
    landmarks,
    filters_x: list[OneEuroFilter],
    filters_y: list[OneEuroFilter],
    timestamp_sec: float,
) -> list[tuple[float, float, float]]:
    """
    Apply One-Euro filtering to x and y of each landmark.
    z is preserved unfiltered — monocular depth is too noisy to smooth usefully.

    Returns a list of (x, y, z) tuples in the same normalized [0, 1] space as
    the raw MediaPipe landmarks.
    """
    return [
        (
            filters_x[i].filter(lm.x, timestamp_sec),
            filters_y[i].filter(lm.y, timestamp_sec),
            lm.z,
        )
        for i, lm in enumerate(landmarks)
    ]


# ── Image preprocessing ────────────────────────────────────────────────────

_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

# Gentle sharpening: centre weight 3, cross-neighbours -0.5 each.
# Net gain = 1.0 with mild edge boost — avoids over-sharpening skin texture.
_SHARPEN_KERNEL = np.array(
    [[0.0, -0.5, 0.0],
     [-0.5,  3.0, -0.5],
     [0.0, -0.5, 0.0]],
    dtype=np.float32,
)


def preprocess_for_mediapipe(bgr_frame: np.ndarray, enable: bool = True) -> np.ndarray:
    """
    Improve MediaPipe detection quality under varied or low lighting.

    Pipeline:
      1. CLAHE on the Y (luminance) channel of YCrCb — preserves hue, lifts
         local contrast so fingertip edges are visible to the neural backbone.
      2. Gentle sharpening kernel — accentuates fingertip-to-background edges
         without amplifying noise on skin texture.

    The original BGR frame is NOT modified; the function returns a new RGB
    array ready for mp.Image(). Pass the original frame to cv2.imshow so the
    display is not affected.

    Set enable=False to bypass all preprocessing (useful for A/B latency tests).
    """
    if not enable:
        return cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)

    ycrcb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    y_eq = _clahe.apply(y)
    bgr_enh = cv2.cvtColor(cv2.merge([y_eq, cr, cb]), cv2.COLOR_YCrCb2BGR)
    sharpened = np.clip(cv2.filter2D(bgr_enh, -1, _SHARPEN_KERNEL), 0, 255).astype(np.uint8)
    return cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB)
