"""
Spiral geometry (pure) — Archimedes spiral generation, equal-arc-length
resampling, and nearest-point lookup. Moved verbatim in behavior from
spiral_test.py so the run loop and unit tests share one implementation.

The spiral is r = b*theta, sampled densely in theta (points bunch near the
center, spread at the rim) then resampled by arc length so a guide/progress
index advances at constant linear speed instead of accelerating outward.
"""

from __future__ import annotations

import math

import numpy as np

# Default geometry (was module-level in spiral_test.py).
SPIRAL_TURNS = 3.5
SPIRAL_NUM_POINTS = 1200

# Placement. The fingertip leads and the palm and wrist hang below it, so the
# lower the spiral reaches, the more often the hand is cut off by the bottom
# edge (core/framing.py) -- which argues for a small spiral set high.
#
# Size is NOT free, though. Tracking jitter is a fixed number of pixels, so a
# smaller spiral makes the same jitter a bigger share of the movement and the
# smoothness index falls. Replaying 33 recorded runs with the movement scaled
# and the jitter kept (2026-09): radius 0.30 cost 12.7 index points on
# average, 0.35 cost 4.2, 0.375 cost 1.5. Position costs nothing -- SPARC does
# not care where the spiral is -- so the centre moves up freely, as far as the
# status bar allows.
#
# 0.36 at 46 %: at 640x480 the drawn spiral spans 12-74 % of the height, so a
# quarter of the frame is left below the lowest arm (the old centred layout's
# reached ~85 %). Measured on the same replay: -1.8 points on average, -0.3 for
# the median run. Until 2026-09 it was
# centred with a radius of 0.40; raw.spiral records the frame and radius of
# each session, so the layouts stay distinguishable and redraw correctly.
SPIRAL_CENTER_Y_FRAC = 0.46
SPIRAL_RADIUS_FRAC = 0.36

# Practice spiral: the same shape, smaller and with fewer turns, so it rehearses
# the real task in about half the time and is visibly not the scored run.
PRACTICE_TURNS = 2.0
PRACTICE_RADIUS_FRAC = 0.7
PRACTICE_NUM_POINTS = 600


def resample_by_arclength(pts, n):
    """Resample a polyline to n points spaced equally by arc length."""
    arr = np.asarray(pts, dtype=np.float64)
    seg = np.sqrt(np.sum(np.diff(arr, axis=0) ** 2, axis=1))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total < 1e-6:
        return [(int(round(arr[0, 0])), int(round(arr[0, 1])))] * n
    targets = np.linspace(0.0, total, n)
    xs = np.interp(targets, cum, arr[:, 0])
    ys = np.interp(targets, cum, arr[:, 1])
    return [(int(round(x)), int(round(y))) for x, y in zip(xs, ys)]


def generate_spiral(cx, cy, b, turns, num_points):
    """Archimedes spiral (r = b*theta), resampled to equal arc-length spacing."""
    max_theta = turns * 2 * math.pi
    dense = max(num_points * 6, 4000)
    raw = []
    for i in range(dense):
        theta = max_theta * i / (dense - 1)
        r = b * theta
        raw.append((cx + r * math.cos(theta), cy - r * math.sin(theta)))
    return resample_by_arclength(raw, num_points)


def practice_coefficient(b, turns=SPIRAL_TURNS):
    """Archimedes coefficient of the practice spiral, given the test's b."""
    max_r = b * turns * 2 * math.pi
    return max_r * PRACTICE_RADIUS_FRAC / (PRACTICE_TURNS * 2 * math.pi)


def scale_spiral_to_frame(fw, fh, turns=SPIRAL_TURNS, num_points=SPIRAL_NUM_POINTS):
    """Generate the test spiral + the smaller practice spiral, both centred
    in the viewport.

    Returns (spiral_points, practice_points, (cx, cy), b) where b is the test
    spiral's Archimedes coefficient r = b*theta."""
    cx, cy = fw // 2, int(round(fh * SPIRAL_CENTER_Y_FRAC))
    max_r = SPIRAL_RADIUS_FRAC * min(fw, fh)
    max_theta = turns * 2 * math.pi
    b = max_r / max_theta
    pts = generate_spiral(cx, cy, b, turns, num_points)
    practice = generate_spiral(cx, cy, practice_coefficient(b, turns),
                               PRACTICE_TURNS,
                               PRACTICE_NUM_POINTS)
    return pts, practice, (cx, cy), b


def nearest_spiral_point(fx, fy, sp_np):
    """Return (index, distance, nearest_x, nearest_y) for the closest point."""
    diffs = sp_np - np.array([fx, fy], dtype=np.float32)
    dists = np.sqrt(np.sum(diffs * diffs, axis=1))
    idx = int(np.argmin(dists))
    return idx, float(dists[idx]), int(sp_np[idx, 0]), int(sp_np[idx, 1])
