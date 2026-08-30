"""
Confidence: how much a scored tapping run deserves to be believed.

A CV% computed from 5 inter-tap intervals and one computed from 60 are not the
same measurement, and until now the results screen presented them identically.
This module attaches an honest error bar and a 0-100 confidence score so a
thin-but-scoreable run can be reported instead of thrown away.

Pure and stdlib-only (mirrors core/spiral/metrics.py): no I/O, no OpenCV, no
PIL. Ported to JS in participant/engine.js -- Python is normative, so any
change here lands first and the parity vectors are regenerated after.

The statistics
--------------
For the sample CV of a roughly normal interval series, Miller's (1991)
approximation gives the relative standard error over `n` intervals as

    RSE = sqrt((0.5 + CV**2) / n)          CV as a fraction, not a percent

which is ~24% at 9 intervals (the old 10-tap floor), ~17% at 18 and ~13% at 30.
Against a 10-point-wide "monitor" band that is the difference between a band
call worth acting on and a coin flip.

Four factors, each in [0, 1], multiplied: a single bad one should dominate,
which is the honest behaviour when any one of them can invalidate the run.
"""

from __future__ import annotations

import math

# The level split and the band-straddle rule are shared with the other tests'
# confidence modules, so "moderate" means one thing across the whole suite
# (core/confidence.py). Re-exported here: this module's public surface is
# unchanged, and the JS port in participant/engine.js still mirrors one file.
from core.confidence import (HIGH, MODERATE, Z95, level_of,  # noqa: F401
                             straddles_band, clamp as _clamp)

# Factor shaping constants.
VISIBLE_FLOOR = 0.70        # hand-visible ratio at or below which tracking → 0
REJECT_CEILING = 0.25       # share of intervals dropped as outliers → 0


def cv_rel_se(cv_frac: float, n_intervals: int) -> float | None:
    """Relative standard error of a sample CV (Miller 1991).

    `cv_frac` is the CV as a fraction (0.15, not 15.0). Returns None when
    there are too few intervals for the approximation to mean anything.
    """
    if n_intervals < 2:
        return None
    return math.sqrt((0.5 + cv_frac * cv_frac) / n_intervals)


def cv_ci(cv_pct: float, n_intervals: int, z: float = Z95) -> tuple[float, float] | None:
    """(low, high) confidence interval on a CV%, clamped at zero below."""
    rse = cv_rel_se(cv_pct / 100.0, n_intervals)
    if rse is None:
        return None
    half = z * cv_pct * rse
    return (max(0.0, cv_pct - half), cv_pct + half)


def quantisation_cv_pct(camera_fps: float | None, mean_iti_ms: float) -> float | None:
    """CV% that frame quantisation alone would produce at this tap rate.

    Each tap time is rounded to a frame, so an interval carries the difference
    of two uniform errors: SD = (1000/fps) / sqrt(6) ms. At 30 fps that is
    13.6 ms -- negligible against a 1 Hz interval, ~7 CV points at 5 Hz.
    """
    if not camera_fps or camera_fps <= 0 or mean_iti_ms <= 0:
        return None
    return 100.0 * (1000.0 / camera_fps) / math.sqrt(6.0) / mean_iti_ms


def confidence(*, n_intervals: int, cv_pct: float, mean_iti_ms: float,
               band_width_pct: float, camera_fps: float | None = None,
               hand_visible_ratio: float = 1.0, rejected_frac: float = 0.0,
               near_miss: int = 0, taps: int = 0) -> dict:
    """Score how much this run's CV% deserves to be believed.

    Returns {"confidence_pct", "confidence_level", "factors", "reasons",
             "cv_ci_low_pct", "cv_ci_high_pct", "quant_cv_pct"}.
    `reasons` are English source strings -- core/i18n.py translates at draw
    time, never here (they are stored in results/ alongside the numbers).
    """
    factors: dict[str, float] = {}
    reasons: list[str] = []

    # 1. Precision -- interval support plus how much of the band the
    #    1-SE error bar eats. Thirty intervals saturates the sample factor.
    rse = cv_rel_se(cv_pct / 100.0, n_intervals)
    if rse is None or band_width_pct <= 0:
        factors["precision"] = 0.0
    else:
        error_factor = _clamp(1.0 - (cv_pct * rse) / band_width_pct)
        sample_factor = math.sqrt(min(1.0, n_intervals / 30.0))
        factors["precision"] = error_factor * sample_factor
    if factors["precision"] < 0.7:
        reasons.append(f"Only {n_intervals} tap intervals were measured - "
                       f"the variability estimate carries a wide margin.")

    # 2. Timing -- share of the measured variance that is frame quantisation.
    #    Variances add, so the fraction is the ratio squared.
    quant = quantisation_cv_pct(camera_fps, mean_iti_ms)
    if quant is None or cv_pct <= 0:
        factors["timing"] = 1.0
    else:
        factors["timing"] = _clamp(1.0 - (quant / cv_pct) ** 2)
    if factors["timing"] < 0.7:
        reasons.append(f"At {camera_fps:.0f} fps the camera cannot time taps "
                       f"this fast precisely - some of this variability is the "
                       f"camera, not the hand.")

    # 3. Tracking -- reuses the hand-visible ratio the run loop already keeps.
    factors["tracking"] = _clamp(
        (hand_visible_ratio - VISIBLE_FLOOR) / (1.0 - VISIBLE_FLOOR))
    if factors["tracking"] < 0.9:
        reasons.append("The hand left the frame for part of the run.")

    # 4. Continuity -- intervals thrown out as outliers (pauses, lost taps).
    factors["continuity"] = _clamp(1.0 - rejected_frac / REJECT_CEILING)
    if factors["continuity"] < 0.9:
        reasons.append("Pauses interrupted the rhythm, so some intervals were "
                       "left out of the score.")

    # Not a factor -- a diagnostic. Shallow closures mean the detector may be
    # under-counting rather than the hand genuinely being slow.
    if near_miss and taps and near_miss >= max(2, 0.25 * taps):
        reasons.append(f"{near_miss} closures were too shallow to count as "
                       f"taps - open the hand fully between taps.")

    score = 100.0
    for value in factors.values():
        score *= value

    ci = cv_ci(cv_pct, n_intervals)
    return {
        "confidence_pct": score,
        "confidence_level": level_of(score),
        "factors": factors,
        "reasons": reasons,
        "cv_ci_low_pct": ci[0] if ci else None,
        "cv_ci_high_pct": ci[1] if ci else None,
        "quant_cv_pct": quant,
    }

