"""
Confidence for the speech tests. `confidence()` is the DDK run — how much its
rhythm CV% deserves to be believed; `phonation_confidence()` (below) is the
sustained vowel, which has no interval statistic and so scores recording
quality only. Same contract as core/tapping/confidence.py: factors in [0, 1],
multiplied, so any one bad factor dominates; the 75/45 level split and the
band-straddle rule come from core/confidence.py so "moderate" means the same
thing here as on every other test's points on the Analysis page.

Factors
  precision   interval support + how much of the band the CV error bar eats
              (Miller 1991, shared with tapping — the statistic is the same)
  signal      syllable peaks over the room's noise floor
  clipping    share of samples at full scale
  continuity  intervals dropped as pauses

The phoneme model's syllable count is deliberately NOT a factor. It was one at
first, but on test speech the model under-counted (20-22 of 24 syllables)
while the envelope was exact, so the disagreement penalised good runs for the
model's own misses (SPEECH_TEST_PLAN.md §3.1b). The count is still recorded.

Pure and stdlib-only.
"""

from __future__ import annotations

import math

from core.confidence import clamp, level_of, straddles_band  # noqa: F401
from core.tapping.confidence import cv_ci, cv_rel_se

SNR_FLOOR_DB, SNR_GOOD_DB = 12.0, 25.0
CLIP_CEILING = 0.02         # 2% of samples clipped → factor 0
REJECT_CEILING = 0.25


def confidence(*, n_intervals: int, cv_pct: float, band_width_pct: float,
               snr_db: float | None, clip_frac: float, rejected_frac: float) -> dict:
    """Returns {"confidence_pct", "confidence_level", "factors", "reasons",
    "cv_ci_low_pct", "cv_ci_high_pct"}. `reasons` are English source strings,
    stored with the numbers; translation happens at draw time."""
    factors: dict[str, float] = {}
    reasons: list[str] = []

    rse = cv_rel_se(cv_pct / 100.0, n_intervals)
    if rse is None or band_width_pct <= 0:
        factors["precision"] = 0.0
    else:
        factors["precision"] = (clamp(1.0 - cv_pct * rse / band_width_pct)
                                * math.sqrt(min(1.0, n_intervals / 30.0)))
    if factors["precision"] < 0.7:
        reasons.append("Few syllable intervals were measured - the rhythm "
                       "estimate carries a wide margin.")

    factors["signal"] = (1.0 if snr_db is None else
                         clamp((snr_db - SNR_FLOOR_DB) / (SNR_GOOD_DB - SNR_FLOOR_DB)))
    if factors["signal"] < 0.7:
        reasons.append("Background noise was close to the level of the voice.")

    factors["clipping"] = clamp(1.0 - clip_frac / CLIP_CEILING)
    if factors["clipping"] < 0.9:
        reasons.append("The microphone was overloaded for part of the run.")

    factors["continuity"] = clamp(1.0 - rejected_frac / REJECT_CEILING)
    if factors["continuity"] < 0.9:
        reasons.append("Pauses interrupted the repetition, so some intervals "
                       "were left out of the score.")

    score = 100.0
    for v in factors.values():
        score *= v
    ci = cv_ci(cv_pct, n_intervals)
    return {"confidence_pct": score, "confidence_level": level_of(score),
            "factors": factors, "reasons": reasons,
            "cv_ci_low_pct": ci[0] if ci else None,
            "cv_ci_high_pct": ci[1] if ci else None}


# Phonation: HNR and shimmer are read against the noise, so it needs more
# headroom than syllable timing does.
PHON_SNR_FLOOR_DB, PHON_SNR_GOOD_DB = 12.0, 30.0
VOICED_FLOOR, VOICED_GOOD = 0.60, 0.95
VOICED_FULL_S = 4.0


def phonation_confidence(*, snr_db: float | None, clip_frac: float,
                         voiced_frac: float, voiced_s: float) -> dict:
    """Confidence for a sustained vowel. No interval statistic exists here, so
    the factors are recording quality only:
      signal    voice over the room's noise floor
      clipping  share of samples at full scale
      voicing   share of the scored segment Praat found voiced — breaks in the
                voice put gaps in the period sequence jitter is read from
      length    voiced time against a 4 s target
    """
    factors: dict[str, float] = {}
    reasons: list[str] = []
    factors["signal"] = (1.0 if snr_db is None else clamp(
        (snr_db - PHON_SNR_FLOOR_DB) / (PHON_SNR_GOOD_DB - PHON_SNR_FLOOR_DB)))
    if factors["signal"] < 0.7:
        reasons.append("Background noise was close to the level of the voice.")
    factors["clipping"] = clamp(1.0 - clip_frac / CLIP_CEILING)
    if factors["clipping"] < 0.9:
        reasons.append("The microphone was overloaded for part of the run.")
    factors["voicing"] = clamp((voiced_frac - VOICED_FLOOR)
                               / (VOICED_GOOD - VOICED_FLOOR))
    if factors["voicing"] < 0.9:
        reasons.append("The voice broke or faded during the vowel.")
    factors["length"] = math.sqrt(clamp(voiced_s / VOICED_FULL_S))
    if factors["length"] < 0.9:
        reasons.append("Only a short stretch of steady voice was measured.")
    score = 100.0
    for v in factors.values():
        score *= v
    return {"confidence_pct": score, "confidence_level": level_of(score),
            "factors": factors, "reasons": reasons}
