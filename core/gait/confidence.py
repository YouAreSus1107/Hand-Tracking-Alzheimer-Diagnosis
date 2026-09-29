"""
Confidence for a scored walking-test run. Same contract as the other tests'
confidence modules: factors in [0, 1], multiplied, so one bad factor
dominates; the 75/45 split comes from core/confidence.py.

Factors
  coverage   share of recorded frames where the whole body was trusted
  blocks     blocks that could be scored, of those run
  sides      whether the arm-raise check settled which leg is which

The camera's frame rate is not a factor, for the tremor test's reason: it is
the machine, not the recording. It is reported beside the result instead.

Pure and stdlib-only.
"""

from __future__ import annotations

from core.confidence import clamp, level_of

UNCHECKED_SIDES = 0.85


def confidence(*, trusted_frac: float, blocks_scored: int, blocks_run: int,
               sides_checked: bool) -> dict:
    factors: dict[str, float] = {}
    reasons: list[str] = []

    # 90 % of frames in view is a clean run; below that it falls away.
    factors["coverage"] = clamp(trusted_frac / 0.9)
    if factors["coverage"] < 0.9:
        reasons.append("Parts of your body were often out of the picture.")

    factors["blocks"] = clamp(blocks_scored / max(1, blocks_run))
    if factors["blocks"] < 1.0:
        reasons.append("Some parts of the test could not be measured.")

    factors["sides"] = 1.0 if sides_checked else UNCHECKED_SIDES
    if not sides_checked:
        reasons.append("Left and right were not confirmed, so the legs may "
                       "be swapped.")

    pct = 100.0
    for v in factors.values():
        pct *= v
    pct = round(pct, 0)
    return {"confidence_pct": pct, "confidence_level": level_of(pct),
            "factors": {k: round(v, 3) for k, v in factors.items()},
            "reasons": reasons}
