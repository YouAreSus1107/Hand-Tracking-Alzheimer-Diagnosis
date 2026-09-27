"""
Fixation stability (docs/research/04-oculomotor-gaze.md §10.3): the user holds gaze
on the central cross while we quantify how steady that fixation is. Elevated
instability and saccadic intrusions are markers in AD and especially PSP.

Pure logic, no OpenCV — unit-testable with synthetic traces (parallels
core/gaze/detector.py `SaccadeTrial`). Reported metrics:

  rms_jitter              RMS of horizontal gaze position about the fixation
                          centroid, in calibrated units (1.0 = the eye-to-
                          target distance). The headline "jitter" number;
                          smaller = steadier. Only samples inside the fixation
                          deadband count, so gross intrusions don't inflate it.
  bcea                    Bivariate Contour Ellipse Area at P=0.68 over the 2-D
                          iris cloud (raw eye-width units²). A *relative*
                          stability measure — not in degrees, since viewing
                          distance is unknown (§10.6) and the vertical axis is
                          an uncalibrated iris proxy (§10.1).
  intrusion_rate_per_min  Count of gaze excursions beyond the fixation deadband
                          (square-wave-jerk / saccadic-intrusion proxy), per
                          minute of valid fixation.

Because the gaze signal is One-Euro smoothed upstream, these measure fixation
instability *above the tracker's smoothing floor* — robust for within-pipeline
comparison across sessions, not an absolute physiological tremor amplitude.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

HOLD_S = 12.0            # steady-fixation recording window
SETTLE_S = 0.8           # ignore initial samples (eye settling onto the cross)
MIN_VALID_RATIO = 0.6    # fraction of post-settle frames that must be tracked
MIN_SAMPLES = 30         # min stable samples for a reliable score
DEBOUNCE_FRAMES = 2      # consecutive out-of-deadband frames to confirm an intrusion
# Floor on the intrusion threshold, decoupling it from the calibrated deadband.
# The two used to be the same number, so lowering the deadband to make the
# saccade blocks register real attempts would have quietly made this block
# count more intrusions - a change to a reported metric as a side effect of a
# fix to a different one. 0.30 is the value the recorded intrusion counts were
# measured at, so they stay comparable.
INTRUSION_MIN = 0.30

BCEA_P = 0.68
_BCEA_K = -math.log(1.0 - BCEA_P)   # ≈ 1.1394 (fraction of a 2-D Gaussian inside)

# Provisional stability bands on rms_jitter (calibrated position units, i.e.
# fraction of the eye-to-target distance). Anchored to internal pilot spread,
# NOT a clinical norm — mirrors the tapping/saccade tests' honest bands.
JITTER_TYPICAL = 0.08
JITTER_MONITOR = 0.16
THRESHOLDS_NOTE = ("Provisional fixation bands - internal pilot spread, "
                   "not a clinical norm.")


@dataclass(frozen=True)
class FixationResult:
    scoreable: bool
    reason: str | None
    rms_jitter: float | None            # calibrated position units
    bcea: float | None                  # raw eye-width units²
    intrusion_count: int
    intrusion_rate_per_min: float | None
    fixation_s: float
    valid_ratio: float
    n_samples: int
    status: str | None = None
    label: str | None = None


def jitter_band(rms: float) -> tuple[str, str]:
    """(status_token, plain-language label) — shown with icon + word, never
    color alone (style guide §2.4)."""
    if rms < JITTER_TYPICAL:
        return "success", "Steady fixation"
    if rms < JITTER_MONITOR:
        return "warning", "Mildly unsteady - consider monitoring"
    return "danger", "Unsteady - recommend follow-up"


def _rms(vals: list[float]) -> float:
    """Root-mean-square deviation about the mean (population form)."""
    n = len(vals)
    mean = sum(vals) / n
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / n)


def bcea(xs: list[float], ys: list[float]) -> float:
    """Bivariate Contour Ellipse Area at P=0.68 (Steinman 1965; Crossland &
    Rubin 2002): BCEA = 2·k·π·σx·σy·√(1−ρ²), k = −ln(1−P). Same unit² as the
    inputs. Returns 0 for a degenerate (zero-spread) cloud."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sx2 = sum((x - mx) ** 2 for x in xs) / (n - 1)
    sy2 = sum((y - my) ** 2 for y in ys) / (n - 1)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)
    sx, sy = math.sqrt(sx2), math.sqrt(sy2)
    if sx <= 0.0 or sy <= 0.0:
        return 0.0
    rho = max(-0.999, min(0.999, sxy / (sx * sy)))
    return 2.0 * _BCEA_K * math.pi * sx * sy * math.sqrt(1.0 - rho * rho)


class FixationAnalyzer:
    """One fixation hold's detector. Feed `update(t, pos, rx, ry)` every frame
    the cross is shown (pos None = face lost / blink), then `finalize()`.

    pos  — signed calibrated horizontal position (from GazeMap), used for the
           jitter headline and intrusion counting (threshold = deadband).
    rx,ry — raw per-frame iris ratios in eye-width units (both axes), used for
           the 2-D BCEA cloud; pass None when unavailable.
    """

    def __init__(self, t0: float, deadband: float):
        self.t0 = t0
        # Never below INTRUSION_MIN: a generous calibration may widen the band
        # this person's own noise needs, but a narrow one must not sharpen it.
        self.threshold = max(INTRUSION_MIN, deadband)
        self._frames = 0
        self._missing = 0
        self._run_len = 0
        self._intrusions = 0
        self._xs: list[float] = []          # calibrated horizontal, stable samples
        self._rx: list[float] = []          # raw iris x/y, stable samples (BCEA)
        self._ry: list[float] = []
        self._first_t: float | None = None
        self._last_t: float | None = None
        self.series: list[tuple[float, float | None]] = []   # (t−t0, pos)

    def update(self, t: float, pos: float | None,
               rx: float | None = None, ry: float | None = None) -> None:
        after = t - self.t0
        self.series.append((after, pos))
        if after < SETTLE_S:                 # eye still settling onto the cross
            return
        self._frames += 1
        if pos is None:
            self._missing += 1
            self._run_len = 0
            return
        if self._first_t is None:
            self._first_t = t
        self._last_t = t
        if abs(pos) >= self.threshold:
            self._run_len += 1
            if self._run_len == DEBOUNCE_FRAMES:   # confirmed excursion, count once
                self._intrusions += 1
            return
        self._run_len = 0
        self._xs.append(pos)
        if rx is not None and ry is not None:
            self._rx.append(rx)
            self._ry.append(ry)

    def finalize(self) -> FixationResult:
        fixation_s = ((self._last_t - self._first_t)
                      if (self._first_t is not None and self._last_t is not None)
                      else 0.0)
        valid_ratio = (1.0 - self._missing / self._frames) if self._frames else 0.0
        n = len(self._xs)

        if self._frames < MIN_SAMPLES or valid_ratio < MIN_VALID_RATIO:
            return FixationResult(
                False,
                "Your eyes weren't tracked steadily enough to measure fixation - "
                "add a little light and try again.",
                None, None, self._intrusions, None, fixation_s, valid_ratio, n)
        if n < MIN_SAMPLES:
            return FixationResult(
                False,
                "Your gaze wandered too much to measure - try to hold still on "
                "the + and retry.",
                None, None, self._intrusions, None, fixation_s, valid_ratio, n)

        rms = _rms(self._xs)
        area = bcea(self._rx, self._ry) if len(self._rx) >= MIN_SAMPLES else None
        rate = (self._intrusions / (fixation_s / 60.0)) if fixation_s > 0 else None
        status, label = jitter_band(rms)
        return FixationResult(True, None, rms, area, self._intrusions, rate,
                              fixation_s, valid_ratio, n, status, label)
