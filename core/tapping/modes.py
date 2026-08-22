"""
TapMode registry — the single source of truth for every tapping paradigm
(FINGER_TAPPING_REVISION_PLAN.md §C1). All dependent values (debounce,
minimum counts, display copy) derive from the mode so configuration and
on-screen copy can never drift apart (the A1 class of bugs).

Modes implemented: B2 max-speed (primary, literature-aligned) and B1 paced.
B3–B7 slot in here as further entries reusing the same engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TapMode:
    key: str
    title: str                 # e.g. "Big & Fast"
    paced: bool                # metronome-driven?
    duration_s: float          # scored duration
    warmup_s: float            # unscored metronome practice (paced only)
    interval_s: float          # beat interval (paced only; 0 for self-paced)
    expected_rate_hz: float    # rough expected tap rate — drives debounce
    min_taps: int              # minimum taps for a scoreable run
    trim_taps: int             # ramp-up taps dropped (only if enough remain)
    cv_typical: float          # CV% below this → within typical range
    cv_monitor: float          # CV% below this → monitor; above → follow-up
    thresholds_note: str       # honest provenance of the bands (plan A5)
    instructions: tuple = field(default_factory=tuple)
    summary: str = ""

    @property
    def min_intertap_s(self) -> float:
        """Fastest plausible inter-tap time — replaces the fixed 300 ms debounce."""
        return 0.5 / self.expected_rate_hz

    @property
    def max_iti_ms(self) -> float:
        """ITI outlier cutoff. Paced: 1.5× interval; self-paced handled by median rule."""
        if self.paced:
            return self.interval_s * 1000 * 1.5
        return 3.0 * 1000.0 / self.expected_rate_hz


MODES: dict[str, TapMode] = {
    "big_and_fast": TapMode(
        key="big_and_fast",
        title="Big & Fast",
        paced=False,
        duration_s=10.0,
        warmup_s=0.0,
        interval_s=0.0,
        expected_rate_hz=5.0,          # healthy max-speed tapping ~4-7 Hz
        min_taps=10,
        trim_taps=2,
        cv_typical=15.0,
        cv_monitor=25.0,
        thresholds_note="Provisional bands - to be calibrated against normative data.",
        instructions=(
            "Using the hand you write with:",
            "Tap your INDEX FINGER and THUMB together",
            "as BIG and as FAST as you can.",
            "Open wide, close fully - keep going for 10 seconds.",
        ),
        summary="Self-paced maximum-speed tapping (TapTalk / Suzumura paradigm).",
    ),
    "paced": TapMode(
        key="paced",
        title="Paced Rhythm",
        paced=True,
        duration_s=30.0,
        warmup_s=5.0,
        interval_s=1.0,
        expected_rate_hz=1.0,
        min_taps=10,
        trim_taps=3,
        cv_typical=15.0,
        cv_monitor=25.0,
        thresholds_note="Bands for 1 Hz paced tapping - provisional, not from a cited norm.",
        instructions=(
            "Using the hand you write with:",
            "Each time you hear the BEEP, tap your INDEX",
            "FINGER to your THUMB - once per beep.",
            "Your rhythm consistency is what's measured,",
            "not your exact beat timing.",
        ),
        summary="Metronome-paced tapping at 1 Hz; measures rhythm + beat sync.",
    ),
}

DEFAULT_MODE = "big_and_fast"
