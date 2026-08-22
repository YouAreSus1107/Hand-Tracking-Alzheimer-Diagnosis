"""
SaccadeTask registry — the single source of truth for both task blocks
(OCULOMOTOR_TEST_PLAN.md §2). All dependent values (trial counts, timings,
display copy) derive from the task so configuration and on-screen copy can
never drift apart (parallels core/tapping/modes.py `TapMode`).

A run is: prosaccade block first (per-user latency baseline), then the
anti-saccade block (primary — its error rate is the headline metric).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SaccadeTask:
    key: str
    title: str
    is_anti: bool
    n_trials: int              # scored trials
    n_practice: int            # unscored, with explicit feedback
    fixation_min_s: float      # jittered central fixation
    fixation_max_s: float
    gap_s: float               # fixation offset → target onset (gap paradigm)
    target_hold_s: float       # how long the dot stays up
    eccentricity: float        # target x offset as fraction of frame width
    instructions: tuple = field(default_factory=tuple)
    summary: str = ""

    @property
    def trial_span_s(self) -> float:
        """Worst-case seconds per trial, for the progress estimate."""
        return self.fixation_max_s + self.gap_s + self.target_hold_s


_COMMON = dict(
    n_practice=3,
    fixation_min_s=1.0,
    fixation_max_s=2.0,
    gap_s=0.2,
    target_hold_s=1.0,
    eccentricity=0.36,
)

TASKS: dict[str, SaccadeTask] = {
    "pro": SaccadeTask(
        key="pro",
        title="Part 1 - Look Toward",
        is_anti=False,
        n_trials=16,
        instructions=(
            "Keep your eyes on the + in the middle.",
            "When a dot appears to the left or right,",
            "look AT the dot as quickly as you can.",
            "Then look back at the middle.",
        ),
        summary="Prosaccade baseline: look toward the dot.",
        **_COMMON,
    ),
    "anti": SaccadeTask(
        key="anti",
        title="Part 2 - Look Away",
        is_anti=True,
        n_trials=24,
        instructions=(
            "Keep your eyes on the + in the middle.",
            "When the dot appears, look to the",
            "OPPOSITE side - AWAY from the dot.",
            "It feels unnatural - that is the test.",
        ),
        summary="Anti-saccade: look away from the dot (inhibitory control).",
        **_COMMON,
    ),
}

BLOCK_ORDER = ("pro", "anti")


def build_directions(n: int, rng: random.Random | None = None) -> list[int]:
    """Count-balanced, shuffled left/right schedule (+1 right, −1 left) with
    no run of more than 3 same-side targets in a row."""
    rng = rng or random.Random()
    dirs = [1] * (n // 2) + [-1] * (n - n // 2)
    for _ in range(100):
        rng.shuffle(dirs)
        run, longest = 1, 1
        for i in range(1, n):
            run = run + 1 if dirs[i] == dirs[i - 1] else 1
            longest = max(longest, run)
        if longest <= 3:
            break
    return dirs
