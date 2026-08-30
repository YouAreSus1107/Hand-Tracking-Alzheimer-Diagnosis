"""
Confidence: how much a scored anti-saccade run deserves to be believed.

The mirror of core/tapping/confidence.py, and it exists for the same reason:
an error rate computed from 6 valid trials and one computed from 15 are not the
same measurement, and the results screen used to present them identically — or,
worse, refuse the thin one outright and hand back nothing for four minutes of
the patient's time. The floor is now low and the honesty lives in a 0-100
score, an error bar, and a flag when the interval straddles a band edge.

Pure and stdlib-only. Level thresholds and the band-straddle rule come from
core/confidence.py so "moderate" means the same thing here as in tapping.

The statistics
--------------
The headline is a **proportion** (errors ÷ valid trials), not a CV, so the
interval is a **Wilson score interval** rather than the Wald form. That is not
a stylistic preference: Wald collapses to zero width at p = 0, and p = 0 is the
*common* case here — a healthy participant scoring 0 errors out of 15. Wilson
still returns a sensible upper bound there (0 of 15 → about 0-20%), which is
exactly the honest statement: this run cannot distinguish a perfect performer
from a mildly elevated one.

Binomial variance peaks at p = 0.5, so a genuinely elevated error rate carries
a *wider* error bar than a low one. That fact is reported where it belongs — in
the interval and the `band_edge` flag — and deliberately kept **out** of the
confidence score. Folding it in was tried and dropped: at a fixed block length
the error bar depends only on the result, so every run with a mid-range error
rate scored "low" no matter how cleanly it was recorded, which relabels the
scale instead of ranking anything. Tapping can afford a precision term because
a 15 s run yields 60-odd intervals; 15 trials cannot.

So the score answers "was this recorded properly?" — trial support, eye
tracking, protocol compliance, all of which genuinely vary between runs and all
of which a redo can fix. How precise the resulting number is, is a separate
statement carried by the CI.

Trial counts and the bands interact discretely: at 15 trials each error is
worth 6.7 points and 3 errors lands exactly on the 20% band edge, which is why
`band_edge` matters more here than it does for tapping's continuous CV.
"""

from __future__ import annotations

import math

from core.confidence import (HIGH, MODERATE, Z95, clamp,  # noqa: F401
                             level_of, straddles_band)

# Factor shaping constants. Provisional, like the bands they are measured
# against — see OCULOMOTOR_TEST_PLAN.md §3.3.
GAZE_FLOOR = 0.70           # gaze-readable ratio at or below which tracking → 0
# ...and the ratio that already counts as full marks. Unlike tapping's
# hand-visible ratio, this one cannot reach 1.0: blinking is involuntary and
# costs ~4% of frames on a normal run, so scoring against a ceiling of 1.0
# would dock every participant for having eyelids.
GAZE_GOOD = 0.92
EXCLUDED_CEILING = 0.50     # share of trials excluded → 0 (half the block)
SATURATION_TRIALS = 15      # valid trials at which the support factor saturates


def wilson_ci(errors: int, n_valid: int,
              z: float = Z95) -> tuple[float, float] | None:
    """(low, high) Wilson score interval on an error rate, in percent."""
    if n_valid <= 0:
        return None
    p = errors / n_valid
    denom = 1.0 + z * z / n_valid
    center = (p + z * z / (2 * n_valid)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n_valid
                                   + z * z / (4 * n_valid * n_valid))
    return (max(0.0, center - half) * 100.0,
            min(1.0, center + half) * 100.0)


def error_se_pct(errors: int, n_valid: int) -> float | None:
    """Standard error of the error rate, in percentage points."""
    if n_valid <= 0:
        return None
    p = errors / n_valid
    return 100.0 * math.sqrt(p * (1 - p) / n_valid)


def onset_resolution_ms(camera_fps: float | None) -> float | None:
    """How precisely a saccade onset can be stamped at this frame rate.

    Onset is the first of two consecutive out-of-deadband frames, so it is
    known to within one frame period — 33 ms at 30 fps, against a 90 ms
    anticipatory cutoff.
    """
    if not camera_fps or camera_fps <= 0:
        return None
    return 1000.0 / camera_fps


def confidence(*, n_valid: int, errors: int, band_width_pct: float,
               attempted: int = 0, excluded: int = 0,
               anticipatory: int = 0, gaze_valid_ratio: float = 1.0,
               camera_fps: float | None = None) -> dict:
    """Score how much this run's anti-saccade error rate deserves to be
    believed, and put an interval around it.

    Returns {"confidence_pct", "confidence_level", "factors", "reasons",
             "error_ci_low_pct", "error_ci_high_pct", "error_se_pct"}.
    `reasons` are English source strings -- core/i18n.py translates at draw
    time, never here (they are stored in results/ alongside the numbers).
    """
    excluded_frac = excluded / attempted if attempted else 0.0
    quality = block_quality(support=n_valid / SATURATION_TRIALS,
                            excluded_frac=excluded_frac,
                            gaze_valid_ratio=gaze_valid_ratio)
    factors = quality["factors"]
    reasons: list[str] = []

    if factors["support"] < 0.95:
        reasons.append(f"Only {n_valid} anti-saccade trials could be scored - "
                       f"the error rate carries a wide margin.")
    if factors["tracking"] < 0.9:
        reasons.append("Your eyes could not be read for part of the run.")
    # A patient who keeps starting early lands here: it costs confidence, and
    # no longer costs them the whole run.
    if anticipatory and attempted and anticipatory >= max(2, 0.2 * attempted):
        reasons.append(f"{anticipatory} trials started before the dot appeared "
                       f"and could not be scored - wait for the dot.")
    elif factors["compliance"] < 0.9:
        reasons.append("Some trials could not be scored and were left out.")

    # The error bar itself is a statement about the result, not the recording,
    # so it is reported rather than scored (see the module docstring).
    se = error_se_pct(errors, n_valid)
    if se is not None and band_width_pct > 0 and se > band_width_pct / 2:
        reasons.append("At this error rate a short block cannot pin the "
                       "number down - read the range, not the single figure.")

    # Not a factor -- a diagnostic. Frame rate does not disturb a proportion,
    # but it does blur the line between an early start and a fast one.
    res = onset_resolution_ms(camera_fps)
    if res is not None and res > 20.0:
        reasons.append(f"At {camera_fps:.0f} fps a saccade's start is only "
                       f"timed to about {res:.0f} ms, so borderline early "
                       f"starts may be misjudged.")

    ci = wilson_ci(errors, n_valid)
    return {
        "confidence_pct": quality["quality_pct"],
        "confidence_level": quality["quality_level"],
        "factors": factors,
        "reasons": reasons,
        "error_ci_low_pct": ci[0] if ci else None,
        "error_ci_high_pct": ci[1] if ci else None,
        "error_se_pct": se,
    }


def block_quality(*, support: float, excluded_frac: float = 0.0,
                  gaze_valid_ratio: float = 1.0) -> dict:
    """Recording quality for one part, for the summary card shown between
    parts — and the engine `confidence()` scores the whole run with.

    It takes no trials and no band, so it means the same thing for all three
    parts including the fixation hold, and it answers the only question a redo
    can fix: did this part record properly? `confidence()` is this score plus
    the run-level interval; the card shows this one alone, under a different
    label ("Recording quality"), because between parts the patient is being
    asked about the recording and nothing else.

    `support` is how much of the intended data arrived: valid ÷ planned trials
    for a saccade block, the tracked fraction for the fixation hold. Taken
    linearly: square-rooting it was tried and flattered the thin end badly —
    a 6-of-15 block came out "moderate", which is exactly the run the score
    exists to warn about.
    """
    factors = {
        "support": clamp(support),
        "tracking": clamp((gaze_valid_ratio - GAZE_FLOOR)
                          / (GAZE_GOOD - GAZE_FLOOR)),
        "compliance": clamp(1.0 - excluded_frac / EXCLUDED_CEILING),
    }
    reasons: list[str] = []
    if factors["support"] < 0.9:
        reasons.append("Fewer usable trials than planned.")
    if factors["tracking"] < 0.9:
        reasons.append("Your eyes could not be read for part of this section.")
    if factors["compliance"] < 0.9:
        reasons.append("Several trials could not be scored.")

    score = 100.0
    for value in factors.values():
        score *= value
    return {"quality_pct": score, "quality_level": level_of(score),
            "factors": factors, "reasons": reasons}
