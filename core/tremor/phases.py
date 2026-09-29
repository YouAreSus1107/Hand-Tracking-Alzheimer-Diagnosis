"""
TremorPhase registry — the three holds of the hand tremor test
(docs/tests/TREMOR_TEST_PLAN.md §2), the tremor counterpart of
core/speech/tasks.py SpeechTask and core/tapping/modes.py TapMode. Duration,
settle time and the on-screen copy hang off one entry, so what the person is
told and what the engine scores cannot drift apart.

Order matters and is the order they run in:
  rest_palm_up    hands resting in the lap, palms up — rest tremor (MDS-UPDRS 3.17)
  rest_palm_down  the same, palms down, so both sides of the hand are seen
  postural        both arms held out — postural tremor (MDS-UPDRS 3.15), which is
                  what essential and enhanced physiological tremor show

The rest holds are in the lap because that is where the hands are fully
supported and at rest, which is how a neurologist examines it (revised
2026-09-27 on a neurologist's advice). An earlier protocol had the forearms on
a table and a second hold counting backward aloud; both were dropped. The lap
needs a camera that can see it — a webcam aimed down at it, not a laptop's own
camera on the table in front of it.
"""


from __future__ import annotations

from dataclasses import dataclass, field

#: The holds that measure rest tremor. Run-level rest figures (asymmetry, the
#: glove comparison) are taken across these.
REST_PHASES: tuple[str, ...] = ("rest_palm_up", "rest_palm_down")


@dataclass(frozen=True)
class TremorPhase:
    key: str
    title: str
    duration_s: float           # recorded window, settle included
    # Dropped from the front of the window before scoring: the hands are still
    # coming to rest after the beep, and that motion is voluntary, not tremor.
    settle_s: float
    # Slow (<1 Hz) movement above this, in hand lengths, is taken as the hand
    # being moved on purpose and that window is dropped. A supported hand
    # barely drifts; arms held out sway far more, and that sway is not tremor.
    move_max: float = 0.15
    instructions: tuple = field(default_factory=tuple)
    cue: str = ""               # one short line shown while recording

    @property
    def scored_s(self) -> float:
        return self.duration_s - self.settle_s


PHASES: dict[str, TremorPhase] = {
    "rest_palm_up": TremorPhase(
        key="rest_palm_up",
        title="Palms Up in Your Lap",
        duration_s=20.0,
        settle_s=2.0,
        instructions=(
            "Sit back and rest both hands in your lap,",
            "palms facing up, fingers loose.",
            "Let them go completely - do not hold them still.",
            "Keep both hands inside the picture.",
        ),
        cue="Palms up, hands fully relaxed",
    ),
    "rest_palm_down": TremorPhase(
        key="rest_palm_down",
        title="Palms Down in Your Lap",
        duration_s=20.0,
        settle_s=2.0,
        instructions=(
            "Now turn both hands over,",
            "palms facing down, resting on your legs.",
            "Let them go completely - do not hold them still.",
            "Keep both hands inside the picture.",
        ),
        cue="Palms down, hands fully relaxed",
    ),
    "postural": TremorPhase(
        key="postural",
        title="Arms Held Out",
        duration_s=20.0,
        settle_s=2.0,
        # Measured on the first live run: arms-out sway was 15-42% of a hand
        # length per 4 s window, against a rest hold's 0.2-11%.
        move_max=0.60,
        instructions=(
            "Lift both arms straight out in front of you,",
            "palms down, fingers gently spread.",
            "Hold them there, level and steady,",
            "with both hands inside the picture.",
        ),
        cue="Hold both arms out, palms down",
    ),
}

PHASE_ORDER: tuple[str, ...] = ("rest_palm_up", "rest_palm_down", "postural")

HANDS: tuple[str, ...] = ("left", "right")
