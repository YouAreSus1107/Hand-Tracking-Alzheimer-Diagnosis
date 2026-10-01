"""
Head-turn check (research note 04 §10.1, plan §3.2b): did the person turn
their head instead of moving their eyes?

The gaze signal is the iris position *relative to the eye corners*, which
ignores head translation but not head rotation. Someone who turns their head
toward the dot lands their gaze there with a smaller iris shift, and one who
turns it back while holding their eyes on the cross moves the iris without
moving their gaze at all. Neither is visible in the gaze trace.

MediaPipe's Face Landmarker already estimates head pose (its facial
transformation matrix), so this costs no new model. Per trial the head's yaw
and pitch while the eye settled on the cross are the reference, and the
largest head rotation away from it while the dot was up is the reading.

**Recorded, not yet enforced.** No saved session carries head pose, so there
is no history to check a cut-off against, and a gate that has not been
checked against real runs is how the eye test used to lose whole blocks
(plan §3.2a). So a turned-head trial is coached and saved with its reading
but keeps its outcome. Make it exclude trials only after the saved
`head_turn_deg` values show where compliant trials sit.

Pure and stdlib-only; the matrix is indexed, never imported as numpy.
"""

from __future__ import annotations

import math

# Head rotation, in degrees, above which a trial counts as a turned head.
# Provisional: the dots sit at 36% of the window width, about 10 degrees from
# centre at arm's length on a laptop, so 4 degrees means the head did roughly
# 40% of the work. MediaPipe's pose jitter frame to frame is about 1 degree.
HEAD_TURN_DEG = 4.0
# How much of the fixation dwell the reference is taken from; matches the
# settle gate's window so both describe the same moment.
REST_WINDOW_S = 0.30


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def angles(matrix) -> tuple[float, float] | None:
    """(yaw, pitch) in degrees from a 4x4 (or 3x3) head transformation matrix.

    Columns are normalised first in case the transform carries scale. Roll is
    left out on purpose: tilting the head barely moves a horizontal gaze
    reading, and yaw is the rotation that fakes or hides a saccade. Only
    *changes* in these angles are used, so the axis sign convention does not
    matter."""
    try:
        r = [[float(matrix[i][j]) for j in range(3)] for i in range(3)]
    except (TypeError, IndexError, ValueError):
        return None
    for j in range(3):
        n = math.sqrt(sum(r[i][j] ** 2 for i in range(3)))
        if n < 1e-9:
            return None
        for i in range(3):
            r[i][j] /= n
    yaw = math.degrees(math.atan2(r[0][2], r[2][2]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -r[1][2]))))
    return yaw, pitch


class HeadWatch:
    """Per-trial head-turn meter. Feed `rest()` every fixation frame, call
    `begin()` when the dot appears, feed `trial()` while it is up, then read
    `turn_deg()`. Poses are (yaw, pitch) or None when unavailable."""

    def __init__(self):
        self._rest: list[tuple[float, float, float]] = []   # (t, yaw, pitch)
        self._trial: list[tuple[float, float]] = []
        self._ref: tuple[float, float] | None = None

    def reset(self) -> None:
        self._rest.clear()
        self._trial.clear()
        self._ref = None

    def rest(self, t: float, pose: tuple[float, float] | None) -> None:
        if pose is None:
            return
        self._rest.append((t, pose[0], pose[1]))
        cutoff = t - REST_WINDOW_S
        while len(self._rest) > 1 and self._rest[0][0] < cutoff:
            self._rest.pop(0)

    def begin(self) -> None:
        """The dot is up: freeze the reference from the rest window."""
        self._trial.clear()
        if self._rest:
            self._ref = (_median([y for _, y, _ in self._rest]),
                         _median([p for _, _, p in self._rest]))
        else:
            self._ref = None

    def trial(self, pose: tuple[float, float] | None) -> None:
        if pose is not None:
            self._trial.append(pose)

    def turn_deg(self) -> float | None:
        """Largest head rotation from the reference while the dot was up, or
        None with nothing to compare. Each frame is replaced by the median of
        itself and its neighbours first, so a one-frame pose glitch cannot
        read as a turn."""
        pts = self._trial
        ref = self._ref
        if ref is None and pts:
            ref = pts[0]                 # no rest frames: first frame stands in
        if ref is None or len(pts) < 3:
            return None
        worst = 0.0
        for i in range(1, len(pts) - 1):
            yaw = _median([pts[i - 1][0], pts[i][0], pts[i + 1][0]])
            pitch = _median([pts[i - 1][1], pts[i][1], pts[i + 1][1]])
            worst = max(worst, math.hypot(yaw - ref[0], pitch - ref[1]))
        return worst


def turned(turn: float | None) -> bool:
    return turn is not None and turn >= HEAD_TURN_DEG


def summarise(turns: list[float | None]) -> dict:
    """Block readout for the saved metrics: how many trials had a head turn,
    and the median turn, so a cut-off can later be set from real runs."""
    known = [t for t in turns if t is not None]
    return {
        "head_turned": sum(1 for t in known if turned(t)),
        "head_measured": len(known),
        "head_turn_median_deg": round(_median(known), 2) if known else None,
    }
