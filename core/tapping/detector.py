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
  - **Thresholds follow the actual tapping excursion, not the warm-up.**
    Calibration is recorded while the participant opens wide and closes fully;
    real tapping is a smaller motion, and it shrinks further over the trial
    (that shrinking IS the decrement biomarker). Frozen calibration thresholds
    therefore start missing the shallow half of a run - one dropped tap merges
    two intervals into a double-length one and inflates CV% far more than the
    lost tap itself. The fractions below are now applied to a rolling estimate
    of the recent excursion, with calibration as the seed and the floor guard.
    This is the threshold-free direction docs/research/01-webcam-hand-motor.md
    recommends (peak detection on the displacement curve, as TapTalk does).
"""

from __future__ import annotations

import math

CLOSE_FRAC = 0.40   # close when d < lo + 0.40·range (higher = more sensitive tap)
OPEN_FRAC = 0.55    # re-open only above lo + 0.55·range (hysteresis)

# Rolling-envelope adaptation.
ENVELOPE_S = 3.0            # window the recent excursion is estimated over
ENVELOPE_MIN_FRAMES = 20    # below this the window is not yet representative
# 0.20 of the calibrated range is the measured knee: real tapping is still
# recovered down to a quarter of the warm-up excursion, while a hand held
# still yields no manufactured taps even at 0.05 landmark noise. Loosening
# to 0.15 scores that still hand as ~25 taps.
ADAPT_MIN_RANGE_FRAC = 0.20


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
    velocity, and decrement (audit A11).

    `near_miss` counts partial closures the hysteresis rejected: dips that fell
    past `open_at` but never reached `close_at`, then rose back. It changes no
    threshold and no tap count -- it exists so a run that looks slow can be told
    apart from a run the detector under-counted, which is the difference
    between genuine bradykinesia and a participant who taps without opening
    the hand fully."""

    def __init__(self, min_intertap_s: float, ema_alpha: float,
                 d_closed: float, d_open: float, adaptive: bool = True):
        rng = max(1e-6, d_open - d_closed)
        self.cal_range = rng
        self.cal_close_at = d_closed + CLOSE_FRAC * rng
        self.cal_open_at = d_closed + OPEN_FRAC * rng
        self.close_at = self.cal_close_at
        self.open_at = self.cal_open_at
        self.adaptive = adaptive
        self._win: list[tuple[float, float]] = []
        self.adapted_frames = 0
        # (t, close_at, open_at) in force when each frame was judged. Recorded
        # so the session report can draw the thresholds the detector actually
        # used -- a flat line would now misrepresent an adapting one.
        self.threshold_series: list[tuple[float, float, float]] = []
        self.min_intertap_s = min_intertap_s
        self.ema_alpha = ema_alpha
        self._ema: float | None = None
        self._closed = False
        self.tap_times: list[float] = []
        self.series: list[tuple[float, float]] = []
        self.last_tap_t: float = -1e9
        self.near_miss = 0
        self._dip_min: float | None = None
        self._frames = 0
        self._closed_frames = 0

    def update(self, t: float, d_raw: float | None) -> bool:
        """Feed one frame's distance sample. Returns True if a tap registered."""
        if d_raw is None:
            return False
        self._ema = d_raw if self._ema is None else (
            self.ema_alpha * d_raw + (1 - self.ema_alpha) * self._ema)
        d = self._ema
        self.series.append((t, d))
        self.threshold_series.append((t, self.close_at, self.open_at))
        self._frames += 1
        tapped = False
        if not self._closed and d < self.close_at:
            self._closed = True
            self._dip_min = None          # this dip closed; not a near miss
            if t - self.last_tap_t >= self.min_intertap_s:
                self.tap_times.append(t)
                self.last_tap_t = t
                tapped = True
        elif self._closed and d > self.open_at:
            self._closed = False
            self._dip_min = None
        elif not self._closed:
            # Open: track how deep this dip goes. Rising back over open_at
            # without ever reaching close_at is the near miss.
            if d < self.open_at:
                self._dip_min = d if self._dip_min is None else min(self._dip_min, d)
            elif self._dip_min is not None:
                self.near_miss += 1
                self._dip_min = None
        if self._closed:
            self._closed_frames += 1
        # Re-estimate the excursion AFTER deciding, so a frame never moves the
        # threshold it is being judged against.
        self._track_envelope(t, d)
        return tapped

    def _track_envelope(self, t: float, d: float) -> None:
        """Slide the window and re-derive the thresholds from the excursion
        actually being performed. Holds the last good pair when the window is
        too short or too flat to trust -- a hand held still must never collapse
        the range onto the noise floor and start scoring jitter as taps."""
        if not self.adaptive:
            return
        self._win.append((t, d))
        cut = t - ENVELOPE_S
        i = 0
        while i < len(self._win) and self._win[i][0] < cut:
            i += 1
        if i:
            del self._win[:i]
        if len(self._win) < ENVELOPE_MIN_FRAMES:
            return
        lo, hi = self._window_percentiles()
        rng = hi - lo
        if rng < ADAPT_MIN_RANGE_FRAC * self.cal_range:
            return
        self.close_at = lo + CLOSE_FRAC * rng
        self.open_at = lo + OPEN_FRAC * rng
        self.adapted_frames += 1

    def _window_percentiles(self) -> tuple[float, float]:
        """5th/95th of the window -- the same estimator Calibrator uses, so the
        seed and the running estimate mean the same thing."""
        s = sorted(d for _, d in self._win)
        n = len(s)
        return (s[int(n * 0.05)], s[min(n - 1, int(n * 0.95))])

    @property
    def smoothed(self) -> float | None:
        return self._ema

    @property
    def closed_dwell_frac(self) -> float:
        """Share of frames spent below the close threshold. A high value with
        few taps means the hysteresis is holding closed, not that the hand
        stopped moving."""
        if self._frames == 0:
            return 0.0
        return self._closed_frames / self._frames
