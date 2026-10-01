"""
Confidence for a scored tremor run — how much of the intended recording the
reading actually rests on. Same contract as core/speech/confidence.py and
core/tapping/confidence.py: factors in [0, 1], multiplied, so any one bad
factor dominates; the 75/45 split comes from core/confidence.py so "moderate"
means the same here as on every other test's points on the Analysis page.

Factors
  coverage   hand × phase cells that could be scored, of the six intended
  windows    still 4 s windows per scored cell, against a full phase's worth
  stillness  windows dropped because a hand was being moved
  framing    share of frames with a hand at the edge of the picture
  instrument share of scored cells read from hand landmarks rather than the
             optical flow (engine 4): landmarks jitter 1-2 % of the hand
             length a frame on a flat hand, and such a cell can only say
             "possible"

The camera's frame rate is deliberately NOT a factor. It limits which tremors
can be seen at all (a 16 fps camera stops near 7.6 Hz), but it is a property
of the machine, not of this recording: folding it in capped every run on a
16 fps laptop at ~64% before the person had done anything, and read as "you
did something wrong". The reach is reported separately as band_hi_hz.

Pure and stdlib-only.
"""

from __future__ import annotations

from core.confidence import clamp, level_of

FULL_WINDOWS = 6            # a clean 18 s phase gives 8; 6 is plenty
CLIP_CEILING_PCT = 30.0
LANDMARK_PENALTY = 0.3      # every cell from landmarks: confidence x 0.7


def confidence(*, expected_cells: int, scored: list,
               clipped_pct: float) -> dict:
    """Returns {"confidence_pct", "confidence_level", "factors", "reasons"}.
    `reasons` are English source strings; translation happens at draw time."""
    factors: dict[str, float] = {}
    reasons: list[str] = []

    factors["coverage"] = clamp(len(scored) / max(1, expected_cells))
    if factors["coverage"] < 1.0:
        reasons.append("Some parts of the test could not be measured for "
                       "one or both hands.")

    if scored:
        factors["windows"] = sum(min(1.0, c["windows"] / FULL_WINDOWS)
                                 for c in scored) / len(scored)
        used = sum(c["windows"] for c in scored)
        dropped = sum(c.get("rejected_windows", 0) for c in scored)
        factors["stillness"] = clamp(1.0 - dropped / max(1, used + dropped) / 0.5)
    else:
        factors["windows"] = factors["stillness"] = 0.0
    if factors["windows"] < 0.8:
        reasons.append("The hands were in view for only part of each hold.")
    if factors["stillness"] < 0.8:
        reasons.append("The hands moved during the holds, so parts of the "
                       "recording were left out.")

    factors["framing"] = clamp(1.0 - clipped_pct / CLIP_CEILING_PCT)
    if factors["framing"] < 0.9:
        reasons.append("A hand was often at the edge of the picture.")

    lm = sum(1 for c in scored if c.get("instrument") == "landmarks")
    factors["instrument"] = clamp(1.0 - LANDMARK_PENALTY * lm / max(1, len(scored)))
    if lm:
        reasons.append("Part of this reading comes from hand landmarks, which "
                       "are less precise than the motion tracking.")

    score = 100.0
    for v in factors.values():
        score *= v
    return {"confidence_pct": score, "confidence_level": level_of(score),
            "factors": factors, "reasons": reasons}
