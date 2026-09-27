"""
TremorPhase registry — the three holds of the hand tremor test
(docs/tests/TREMOR_TEST_PLAN.md §2), the tremor counterpart of
core/speech/tasks.py SpeechTask and core/tapping/modes.py TapMode. Duration,
settle time and the on-screen copy hang off one entry, so what the person is
told and what the engine scores cannot drift apart.

Order matters and is the order they run in:
  rest        forearms on the table, hands relaxed — rest tremor (MDS-UPDRS 3.17)
  rest_count  the same, while counting backward aloud — mental load is the
              standard way to bring out a rest tremor that is hiding
  postural    both arms held out — postural tremor (MDS-UPDRS 3.15), which is
              what essential and enhanced physiological tremor show
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    "rest": TremorPhase(
        key="rest",
        title="Hands at Rest",
        duration_s=20.0,
        settle_s=2.0,
        instructions=(
            "Rest both forearms flat on the table,",
            "palms down, with your hands fully relaxed.",
            "Let them go loose - do not hold them still.",
            "Keep both hands inside the picture.",
        ),
        cue="Relax both hands completely",
    ),
    "rest_count": TremorPhase(
        key="rest_count",
        title="Rest While Counting",
        duration_s=20.0,
        settle_s=2.0,
        instructions=(
            "Same position, hands relaxed on the table.",
            "This time, count backward out loud",
            "from 100 in steps of 3: 100, 97, 94 ...",
            "Keep your hands loose while you count.",
        ),
        cue="Count backward from 100 by 3s, out loud",
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

PHASE_ORDER: tuple[str, ...] = ("rest", "rest_count", "postural")

HANDS: tuple[str, ...] = ("left", "right")
