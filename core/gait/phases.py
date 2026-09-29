"""
The walking test's blocks (GAIT_TEST_PLAN.md §3). Only the seated tier is built
so far: leg agility per leg (UPDRS 3.8) and five sit-to-stands (UPDRS 3.9).
The walking blocks (C-F) will be added here as they are built.

Titles, cues and instruction lines are English source strings; they are
translated at draw time (core/i18n.py) and the instruction blocks by key,
`gait.<key>.instructions`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LEG_AGILITY = "leg_agility"
SIT_TO_STAND = "sit_to_stand"


@dataclass(frozen=True)
class GaitBlock:
    key: str
    kind: str                   # LEG_AGILITY | SIT_TO_STAND
    title: str
    cue: str                    # one short line shown while recording
    duration_s: float           # fixed length, or the time limit
    side: str | None = None     # which leg, for leg agility
    instructions: tuple = field(default_factory=tuple)


BLOCKS: dict[str, GaitBlock] = {
    "leg_right": GaitBlock(
        key="leg_right", kind=LEG_AGILITY, side="right",
        title="Right Leg Stamps",
        cue="Stamp your right foot, high and fast",
        duration_s=10.0,
        instructions=(
            "Sit back in the chair.",
            "Lift your right foot as high as you can",
            "and stamp it down, over and over,",
            "as fast as you can. Keep the left foot still.",
        )),
    "leg_left": GaitBlock(
        key="leg_left", kind=LEG_AGILITY, side="left",
        title="Left Leg Stamps",
        cue="Stamp your left foot, high and fast",
        duration_s=10.0,
        instructions=(
            "Now the other leg.",
            "Lift your left foot as high as you can",
            "and stamp it down, over and over,",
            "as fast as you can. Keep the right foot still.",
        )),
    "sts5": GaitBlock(
        key="sts5", kind=SIT_TO_STAND,
        title="Five Sit-to-Stands",
        cue="Stand up and sit down, five times",
        # A time limit, not a length: the block ends at the fifth sit.
        duration_s=45.0,
        instructions=(
            "Cross your arms over your chest.",
            "After the beep, stand up fully and sit back down,",
            "five times, as fast as you safely can.",
            "Use your hands if you need to.",
        )),
}

SEATED_ORDER = ("leg_right", "leg_left", "sts5")
