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
    n_trials: int              # scored trials the block plans to run
    n_practice: int            # unscored, with explicit feedback
    fixation_min_s: float      # jittered central fixation
    fixation_max_s: float
    gap_s: float               # fixation offset → target onset (gap paradigm)
    target_hold_s: float       # how long the dot stays up
    eccentricity: float        # target x offset as fraction of frame width
    instructions: tuple = field(default_factory=tuple)
    summary: str = ""
    # Replacement trials. A block runs `n_trials`, then keeps going only while
    # it is short of `target_valid` usable ones, never past `n_trials_max`.
    # Both default to 0, meaning "fixed length"; both blocks now set them.
    n_trials_max: int = 0
    target_valid: int = 0

    @property
    def trial_span_s(self) -> float:
        """Worst-case seconds per trial, for the progress estimate."""
        return self.fixation_max_s + self.gap_s + self.target_hold_s

    @property
    def max_trials(self) -> int:
        return self.n_trials_max or self.n_trials

    @property
    def extends(self) -> bool:
        return self.max_trials > self.n_trials and self.target_valid > 0


_COMMON = dict(
    n_practice=2,
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
        n_trials=15,
        # The pro block loses trials to blinks and lost tracking exactly as the
        # anti block does - over the recorded history it was scoring only ~69%
        # of what it attempted, which is what kept firing the MIN_VALID_PRO
        # note and left Anti - Pro resting on a thin baseline. It gets the same
        # replacement rule; 12 is the pro-side analogue of anti's 13, sitting
        # just above metrics.MIN_VALID_PRO so the note fires on a genuinely
        # poor block rather than on ordinary attrition.
        n_trials_max=20,
        target_valid=12,
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
        # 15 scored trials, not 24: computed against the healthy (~6%) and AD
        # (~25.4%) error rates this test is banded on, 15 flags a 25% rate as
        # often as 24 does (76.4% vs 75.3%), because 3/15 falls exactly on the
        # 20% band edge. It costs false positives (5.7% vs 1.3%), which the
        # band_edge flag is there to soften. The relationship is NOT monotonic
        # — 16 trials moves the edge to 25% and detection drops to 59.5% — so
        # this number cannot be nudged without redoing that arithmetic.
        n_trials=15,
        # Anticipated and lost trials buy replacements rather than costing the
        # run: keep going while short of 13 usable ones, to a hard 20.
        n_trials_max=20,
        target_valid=13,
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
