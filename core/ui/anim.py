"""
Easing / interpolation helpers (UI_STYLE_GUIDE.md §6).
OpenCV renders frame-by-frame, so "animation" = interpolating a value by
elapsed wall-clock time each frame — never assume a fixed frame rate.
"""

from __future__ import annotations


def clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 4 * t**3 if t < 0.5 else 1.0 - ((-2 * t + 2) ** 3) / 2


def progress(t0: float, now: float, duration: float) -> float:
    """0→1 progress of an animation started at t0."""
    if duration <= 0:
        return 1.0
    return clamp01((now - t0) / duration)


def fade_in_out(t0: float, now: float, fade: float, hold: float) -> float:
    """Alpha envelope: fade in over `fade`, hold `hold`, fade out over `fade`."""
    e = now - t0
    total = fade + hold + fade
    if e <= 0 or e >= total:
        return 0.0
    if e < fade:
        return ease_out_cubic(e / fade)
    if e < fade + hold:
        return 1.0
    return 1.0 - ease_in_out_cubic((e - fade - hold) / fade)


class CountUp:
    """Animate a metric from 0 to its final value over `duration` (§6.2)."""

    def __init__(self, target: float, t0: float, duration: float = 0.320):
        self.target = target
        self.t0 = t0
        self.duration = duration

    def value(self, now: float) -> float:
        return self.target * ease_in_out_cubic(progress(self.t0, now, self.duration))
