"""
Tap detection: landmarks → calibrated, scale-invariant distance → tap events.
Pure logic, no OpenCV window — unit-testable with synthetic signals
(FINGER_TAPPING_REVISION_PLAN.md §C2/§C5).

Fixes over the old fixed-threshold approach:
  - Distance is normalized by hand span (wrist→middle-MCP), so apparent hand
    size / camera distance no longer shifts the threshold (audit A3).
  - Per-session calibration captures the user's own open/closed range.
  - Hysteresis (close below 30% of range, re-open above 55%) replaces the
    fixed 300 ms debounce that blocked max-speed tapping (audit A4).
"""

from __future__ import annotations

import math

CLOSE_FRAC = 0.40   # close when d < d_closed + 0.40·range (higher = more sensitive tap)
OPEN_FRAC = 0.55    # re-open only above d_closed + 0.55·range (hysteresis)


def thumb_index_distance(landmarks) -> float | None:
    """Thumb-tip↔index-tip distance normalized by hand span (scale-invariant).

    `landmarks` is a list of (x, y, z) tuples in normalized image space.
    Returns None if the hand span is degenerate (tracking glitch).
    """
    span = math.hypot(landmarks[0][0] - landmarks[9][0],
                      landmarks[0][1] - landmarks[9][1])
    if span < 1e-4:
        return None
    d = math.hypot(landmarks[4][0] - landmarks[8][0],
                   landmarks[4][1] - landmarks[8][1])
    return d / span


class Calibrator:
    """Guided warm-up calibration: the user opens/closes a few times while we
    record the distance signal; d_open / d_closed come from percentiles."""

    MIN_FRAMES = 45          # ~1.5 s of signal at 30 fps
    MIN_RANGE = 0.30         # span-normalized units; open ≈ 1.0+, closed ≈ 0.2
    MIN_CYCLES = 2           # full open→close cycles observed
    TIMEOUT_S = 20.0

    def __init__(self):
        self._samples: list[float] = []
        self._t0: float | None = None
        self._below_mid = False
        self.cycles = 0

    def update(self, t: float, d: float) -> None:
        if self._t0 is None:
            self._t0 = t
        self._samples.append(d)
        lo, hi = self._percentiles()
        if hi - lo >= self.MIN_RANGE * 0.6:
            mid = lo + 0.4 * (hi - lo)
            if d < mid and not self._below_mid:
                self._below_mid = True
                self.cycles += 1
            elif d > lo + 0.6 * (hi - lo):
                self._below_mid = False

    def _percentiles(self) -> tuple[float, float]:
        if len(self._samples) < 5:
            return (0.0, 0.0)
        s = sorted(self._samples)
        n = len(s)
        return (s[int(n * 0.05)], s[min(n - 1, int(n * 0.95))])

    @property
    def range_seen(self) -> float:
        lo, hi = self._percentiles()
        return hi - lo

    @property
    def progress(self) -> float:
        """0→1 gauge for the calibration UI."""
        f = min(1.0, len(self._samples) / self.MIN_FRAMES)
        r = min(1.0, self.range_seen / self.MIN_RANGE)
        c = min(1.0, self.cycles / self.MIN_CYCLES)
        return min(f, r, c)

    @property
    def done(self) -> bool:
        return (len(self._samples) >= self.MIN_FRAMES
                and self.range_seen >= self.MIN_RANGE
                and self.cycles >= self.MIN_CYCLES)

    def timed_out(self, t: float) -> bool:
        return self._t0 is not None and (t - self._t0) > self.TIMEOUT_S

    def result(self) -> tuple[float, float]:
        """(d_closed, d_open) percentile estimates."""
        return self._percentiles()


class TapDetector:
    """Calibrated hysteresis tap detector over the normalized distance signal.

    Also records the full (t, d) series so metrics can derive amplitude,
    velocity, and decrement (audit A11)."""

    def __init__(self, min_intertap_s: float, ema_alpha: float,
                 d_closed: float, d_open: float):
        rng = max(1e-6, d_open - d_closed)
        self.close_at = d_closed + CLOSE_FRAC * rng
        self.open_at = d_closed + OPEN_FRAC * rng
        self.min_intertap_s = min_intertap_s
        self.ema_alpha = ema_alpha
        self._ema: float | None = None
        self._closed = False
        self.tap_times: list[float] = []
        self.series: list[tuple[float, float]] = []
        self.last_tap_t: float = -1e9

    def update(self, t: float, d_raw: float | None) -> bool:
        """Feed one frame's distance sample. Returns True if a tap registered."""
        if d_raw is None:
            return False
        self._ema = d_raw if self._ema is None else (
            self.ema_alpha * d_raw + (1 - self.ema_alpha) * self._ema)
        d = self._ema
        self.series.append((t, d))
        tapped = False
        if not self._closed and d < self.close_at:
            self._closed = True
            if t - self.last_tap_t >= self.min_intertap_s:
                self.tap_times.append(t)
                self.last_tap_t = t
                tapped = True
        elif self._closed and d > self.open_at:
            self._closed = False
        return tapped

    @property
    def smoothed(self) -> float | None:
        return self._ema
