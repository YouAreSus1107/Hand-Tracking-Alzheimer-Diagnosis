"""
Scoring for the walking test's seated tier (GAIT_TEST_PLAN.md §7). Pure and
stdlib-only.

Headline: the five-sit-to-stand time, the clinically familiar number. Leg
agility is reported per leg, with the left/right difference, but carries no
band: nothing published maps knee lift in thigh lengths onto a cut-off, and
inventing one would put a verdict on a number nobody has validated.

**The bands are provisional and must be checked against the sources** (plan
§7): ~13 s is the upper end of healthy 60-79-year-olds (Bohannon 2006), and
16 s separated PD fallers from non-fallers (Duncan 2011). Both are quoted
from memory in the plan; verify before relying on them.
"""

from __future__ import annotations

from .confidence import confidence

ENGINE_VERSION = 1

STS_TYPICAL_S = 13.0        # provisional (Bohannon 2006, verify)
STS_FOLLOW_UP_S = 16.0      # provisional (Duncan 2011, PD fallers, verify)
SIDE_DIFF_PCT = 20.0        # legs differing by more than this are named


def band(sts5_s: float | None, completed: bool) -> tuple[str, str]:
    if not completed or sts5_s is None:
        return "warning", "Did not finish five stands"
    if sts5_s < STS_TYPICAL_S:
        return "success", "Within typical range"
    if sts5_s < STS_FOLLOW_UP_S:
        return "warning", "Slower than typical - consider monitoring"
    return "danger", "Slow to rise - recommend follow-up"


def laterality(legs: dict) -> dict:
    """Which leg is weaker, if they differ clearly. A one-sided difference is
    how Parkinson's usually starts; handedness explains small ones."""
    r, l = legs.get("right") or {}, legs.get("left") or {}
    out: dict = {"weaker_leg": None}
    if not (r.get("scored") and l.get("scored")):
        return out
    for key in ("rate_hz", "amp_pct"):
        a, b = r.get(key), l.get(key)
        if a and b:
            out[f"{key}_diff_pct"] = round(100.0 * abs(a - b) / max(a, b), 1)
    diffs = [(k, out.get(f"{k}_diff_pct") or 0.0) for k in ("rate_hz", "amp_pct")]
    key, diff = max(diffs, key=lambda kv: kv[1])
    if diff >= SIDE_DIFF_PCT:
        out["weaker_leg"] = "right" if r[key] < l[key] else "left"
        out["weaker_by"] = key
    return out


def compute_metrics(*, legs: dict, sts: dict | None, trusted_frac: float,
                    sides_checked: bool, fps: float) -> dict:
    """legs = {"right": analyse_leg(...), "left": ...}; sts = analyse_sts(...)."""
    blocks = [legs.get("right"), legs.get("left"), sts]
    run = [b for b in blocks if b is not None]
    scored = [b for b in run if b.get("scored")]
    out: dict = {"engine_version": ENGINE_VERSION, "fps": round(fps, 1),
                 "legs": legs, "sts": sts, "scoreable": False}

    if not sts or not sts.get("scored"):
        out["reason"] = (sts or {}).get("reason") or \
            "The sit-to-stand part could not be measured."
        # The leg readings still stand on their own; keep them visible.
        out.update(laterality(legs))
        return out

    status, label = band(sts.get("sts5_s"), bool(sts.get("completed")))
    conf = confidence(trusted_frac=trusted_frac, blocks_scored=len(scored),
                      blocks_run=len(run), sides_checked=sides_checked)
    out.update(
        scoreable=True,
        status=status, label=label,
        sts5_s=sts.get("sts5_s"),
        sts5_sit_s=sts.get("sts5_sit_s"),
        n_stands=sts.get("n_stands"),
        failed_attempts=sts.get("failed_attempts"),
        hands_used=sts.get("hands_used"),
        rise_s_median=sts.get("rise_s_median"),
        lean_deg_median=sts.get("lean_deg_median"),
        confidence_pct=conf["confidence_pct"],
        confidence_level=conf["confidence_level"],
        confidence_factors=conf["factors"],
        confidence_reasons=conf["reasons"],
    )
    for side in ("right", "left"):
        c = legs.get(side) or {}
        if c.get("scored"):
            out[f"leg_{side}_rate_hz"] = c.get("rate_hz")
            out[f"leg_{side}_amp_pct"] = c.get("amp_pct")
    out.update(laterality(legs))
    return out
