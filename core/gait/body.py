"""
Body landmarks for the walking test: which MediaPipe Pose indices mean what,
which side of the body each one is, and the few geometric helpers every block
shares. Pure and stdlib-only -- the tracker lives in pose.py.

Left/right (GAIT_TEST_PLAN.md §3). MediaPipe's hand model names the opposite
hand on a selfie-flipped frame, and that went unnoticed for months (see
core/hand_utils.true_hand). The pose model's convention has not been verified
on this suite's cameras, so it is not assumed: the setup asks the person to
raise their right arm, and SideMap records whether the model's "right" is the
person's right. Every caller goes through SideMap.idx(), never a raw index.
"""

from __future__ import annotations

import math

# MediaPipe Pose (33 landmarks): the model's own left/right labels.
NOSE = 0
_MODEL = {
    "left": {"shoulder": 11, "elbow": 13, "wrist": 15, "hip": 23,
             "knee": 25, "ankle": 27, "heel": 29, "toe": 31},
    "right": {"shoulder": 12, "elbow": 14, "wrist": 16, "hip": 24,
              "knee": 26, "ankle": 28, "heel": 30, "toe": 32},
}
SIDES = ("left", "right")

# The joints the test reads and the framing check needs in the picture. The
# face (bar the nose) and the hands' extra points are left out: they add
# nothing here and would make a turned head read as a framing problem.
BODY = (NOSE,) + tuple(sorted(i for s in _MODEL.values() for i in s.values()))

# Skeleton edges for drawing, in model indices.
EDGES = (
    (11, 12), (11, 23), (12, 24), (23, 24),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),
    (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),
)


class SideMap:
    """Maps the person's side to the model's label.

    `swapped` is None until the arm-raise check has run; until then the
    model's labels are taken as they come, and `checked` says so."""

    def __init__(self, swapped: bool | None = None):
        self.swapped = swapped

    @property
    def checked(self) -> bool:
        return self.swapped is not None

    def model_side(self, person_side: str) -> str:
        if self.swapped:
            return "left" if person_side == "right" else "right"
        return person_side

    def person_side(self, model_side: str) -> str:
        return self.model_side(model_side)       # the swap is its own inverse

    def idx(self, person_side: str, joint: str) -> int:
        return _MODEL[self.model_side(person_side)][joint]


def model_idx(model_side: str, joint: str) -> int:
    return _MODEL[model_side][joint]


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def mid(a, b) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def trunk_lean_deg(pts) -> float | None:
    """Forward lean of the trunk from vertical, in degrees, from the shoulder
    and hip midpoints. Side-on, this is the flexion a sit-to-stand uses and the
    stoop UPDRS 3.13 looks at. Unsigned: the camera may be on either side."""
    if pts is None:
        return None
    sh = mid(pts[11], pts[12])
    hp = mid(pts[23], pts[24])
    dx, dy = sh[0] - hp[0], hp[1] - sh[1]          # image y grows downward
    if dy <= 1e-6:
        return None
    return math.degrees(math.atan2(abs(dx), dy))


def raised_side(pts, margin: float = 0.0) -> str | None:
    """The model side whose wrist is above the nose while the other is not,
    else None. Used by the arm-raise check."""
    if pts is None:
        return None
    nose_y = pts[NOSE][1]
    up = [s for s in SIDES if pts[_MODEL[s]["wrist"]][1] < nose_y - margin]
    return up[0] if len(up) == 1 else None
