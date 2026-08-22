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


def generate_warmup_circle(cx, cy, radius, num_points=400):
    """Simple circle for the warmup phase."""
    points = []
    for i in range(num_points):
        theta = 2 * math.pi * i / (num_points - 1)
        x = cx + radius * math.cos(theta)
        y = cy - radius * math.sin(theta)
        points.append((int(round(x)), int(round(y))))
    return points


def scale_spiral_to_frame(fw, fh, turns=SPIRAL_TURNS, num_points=SPIRAL_NUM_POINTS):
    """Generate spiral + warmup circle sized to fit the viewport.

    Returns (spiral_points, warmup_points, (cx, cy), b) where b is the
    Archimedes coefficient r = b*theta."""
    cx, cy = fw // 2, fh // 2
    max_r = 0.4 * min(fw, fh)
    max_theta = turns * 2 * math.pi
    b = max_r / max_theta
    pts = generate_spiral(cx, cy, b, turns, num_points)
    warmup = generate_warmup_circle(cx, cy, max_r * 0.35, 400)
    return pts, warmup, (cx, cy), b


def nearest_spiral_point(fx, fy, sp_np):
    """Return (index, distance, nearest_x, nearest_y) for the closest point."""
    diffs = sp_np - np.array([fx, fy], dtype=np.float32)
    dists = np.sqrt(np.sum(diffs * diffs, axis=1))
    idx = int(np.argmin(dists))
    return idx, float(dists[idx]), int(sp_np[idx, 0]), int(sp_np[idx, 1])
