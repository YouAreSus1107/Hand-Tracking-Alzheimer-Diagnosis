"""
Practice-spiral coaching (pure) -- the recommended pace and the live feedback
shown while the patient traces the smaller, unscored practice spiral.

The scored test is self-paced with no dot to chase, so practice rehearses
exactly that: the same kind of spiral, traced freely, with *advice* about pace
rather than a target to follow. Nothing here touches a score -- the practice
samples never reach core/session.py.

Pace is a linear speed, not a duration, so it transfers from the practice
spiral to the larger test spiral: the recommended speed is the test spiral's
arc length over TARGET_TRACE_S. 25 s is the middle of the recorded runs that
scored smoothest (smoothness index 70-80 finished in roughly 21-30 s).

Speed is measured as the rate of *progress along the spiral* (arc length of the
furthest point reached), not as raw fingertip speed: raw speed includes the
jitter the test measures, which would read as "too fast" on a shaky hand.
"""

from __future__ import annotations

import math

TARGET_TRACE_S = 25.0      # recommended time for the full test spiral
PACE_TOLERANCE = 0.40      # "good" band is target +/- 40 %
PACE_WINDOW_S = 1.2        # rolling window for the progress-rate estimate
PACE_MIN_SPAN_S = 0.6      # below this much history the pace is unknown

# Coaching copy (English source strings; translated at draw time).
MSG_START = "Trace outward along the line"
MSG_OFF_LINE = "Go back to the line you were tracing"
MSG_SLOWER = "Slow down a little"
MSG_FASTER = "Speed up a little"
MSG_SMOOTHER = "Move more smoothly"
MSG_GOOD = "Good - keep this pace"

# Done-card takeaways.
TAKE_FASTER = "For the test, move a little faster."
TAKE_SLOWER = "For the test, move a little slower."
TAKE_LINE = "For the test, try to stay closer to the line."
TAKE_GOOD = "Good pace - keep it for the test."


def arc_length(points) -> float:
    """Total length of a polyline, in the points' own units."""
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def target_speed_px_s(test_points, target_s: float = TARGET_TRACE_S) -> float:
    """Recommended progress speed: the scored spiral traced in target_s."""
    return arc_length(test_points) / target_s if target_s > 0 else 0.0


def recommended_time_s(points, target_speed: float) -> float:
    """Time to trace `points` at the recommended speed."""
    return arc_length(points) / target_speed if target_speed > 0 else 0.0


def pace_band(speed: float | None, target: float) -> str | None:
    """'slow' | 'good' | 'fast', or None while the pace is still unknown."""
    if speed is None or target <= 0:
        return None
    ratio = speed / target
    if ratio < 1.0 - PACE_TOLERANCE:
        return "slow"
    if ratio > 1.0 + PACE_TOLERANCE:
        return "fast"
    return "good"


def progress_speed(history, now: float,
                   window_s: float = PACE_WINDOW_S) -> float | None:
    """Rate of progress along the spiral over the last `window_s` seconds.

    `history` is a time-ordered list of (t, arc_px) where arc_px is the arc
    length of the furthest point reached. Returns px/s, or None when the window
    holds less than PACE_MIN_SPAN_S of data."""
    recent = [(t, a) for t, a in history if t >= now - window_s]
    if len(recent) < 2:
        return None
    (t0, a0), (t1, a1) = recent[0], recent[-1]
    if t1 - t0 < PACE_MIN_SPAN_S:
        return None
    return max(0.0, (a1 - a0) / (t1 - t0))


def expected_index(elapsed_active_s: float, target_speed: float,
                   total_len: float, n_points: int) -> int:
    """Where on an equal-arc-length spiral of `n_points` the patient would be
    after `elapsed_active_s` at the recommended pace. The clock starts when the
    trace starts (after the centre hold), so a slow start is not penalised."""
    if n_points < 2 or total_len <= 0 or elapsed_active_s <= 0:
        return 0
    frac = min(1.0, elapsed_active_s * target_speed / total_len)
    return int(round(frac * (n_points - 1)))


def coach_message(pace: str | None, on_line: bool,
                  smooth_status: str) -> tuple[str, str]:
    """One (message, status token) for the live coach line, by priority:
    staying on the arm being traced, then pace, then smoothness."""
    if not on_line:
        return MSG_OFF_LINE, "warning"
    if pace is None:
        return MSG_START, "info"
    if pace == "fast":
        return MSG_SLOWER, "warning"
    if pace == "slow":
        return MSG_FASTER, "warning"
    if smooth_status == "danger":
        return MSG_SMOOTHER, "warning"
    return MSG_GOOD, "success"


def practice_summary(duration_s: float, recommended_s: float,
                     pace_samples, on_line_samples) -> dict:
    """Done-card numbers. `pace_samples` is the list of pace bands observed
    (None entries ignored); `on_line_samples` a list of booleans."""
    known = [p for p in pace_samples if p is not None]
    good_pct = (100.0 * sum(p == "good" for p in known) / len(known)
                if known else None)
    line_pct = (100.0 * sum(bool(s) for s in on_line_samples)
                / len(on_line_samples) if on_line_samples else None)

    ratio = duration_s / recommended_s if recommended_s > 0 else 1.0
    if line_pct is not None and line_pct < 60.0:
        take = TAKE_LINE
    elif ratio > 1.0 / (1.0 - PACE_TOLERANCE):   # took far longer -> too slow
        take = TAKE_FASTER
    elif ratio < 1.0 / (1.0 + PACE_TOLERANCE):   # far quicker -> too fast
        take = TAKE_SLOWER
    else:
        take = TAKE_GOOD
    return {"duration_s": duration_s, "recommended_s": recommended_s,
            "good_pace_pct": good_pct, "on_line_pct": line_pct,
            "takeaway": take}
