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
    expected_rate_hz: float    # rate a typical run actually produces — the
                               # pace the instructions coach toward. NOT the
                               # debounce input (see max_rate_hz).
    min_taps: int              # minimum taps for a scoreable run
    trim_taps: int             # ramp-up taps dropped (only if enough remain)
    cv_typical: float          # CV% below this → within typical range
    cv_monitor: float          # CV% below this → monitor; above → follow-up
    thresholds_note: str       # honest provenance of the bands (plan A5)
    instructions: tuple = field(default_factory=tuple)
    summary: str = ""
    compat_window_s: float = 10.0   # sub-window rescored for literature parity
    # Fastest physically plausible tap rate — drives the debounce ONLY. Kept
    # separate from expected_rate_hz because the two answer different
    # questions: expected is the pace a real run lands on, this is the ceiling
    # above which a "tap" has to be detector chatter. Tying the debounce to
    # the expected pace would clip the fastest genuine tappers the moment the
    # expected pace is corrected downward. Defaults to expected_rate_hz.
    max_rate_hz: float | None = None
    # Absolute floor (taps/s) below which a run isn't reported as a rhythm
    # score — a hand that barely moved has no rhythm to measure. Deliberately
    # an absolute number and not a fraction of expected_rate_hz: a fraction
    # re-derives the floor every time the expected pace is retuned, which is
    # how a 1.75 Hz gate came to reject ~70% of the recorded run history.
    # None (paced modes) skips the gate: there a slow run already shows up as
    # missed beats rather than needing a speed floor.
    min_effort_hz: float | None = None

    @property
    def min_intertap_s(self) -> float:
        """Fastest plausible inter-tap time — replaces the fixed 300 ms debounce."""
        return 0.5 / (self.max_rate_hz or self.expected_rate_hz)

    @property
    def cv_band_width(self) -> float:
        """Width of the middle (monitor) band. The confidence score measures
        its error bar against this, so the two can never drift apart."""
        return self.cv_monitor - self.cv_typical

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
        # 20 s, against Suzumura 2022's (PMC9716461, the best MCI AUC in
        # research/) 15 s. Suzumura runs the same opposition paradigm at ~2 Hz,
        # so 15 s buys them ~30 taps — exactly where their MCI cut-off falls,
        # and where the confidence score's precision factor saturates. This
        # pipeline measures ~1.2 Hz, where 15 s yields about 15 scored intervals
        # and that factor cannot clear ~58% no matter how clean the run is.
        # 20 s buys ~21 intervals (~70%). Literature comparability is not spent
        # doing this: compat_window_s rescores a 10 s sub-window, which is what
        # that field is for. NB the dependency — if coaching lifts the rate
        # toward the ~2.5 Hz norm, 15 s becomes sufficient and this should be
        # revisited (docs/TAPPING_PRACTICE_PLAN.md phase 3).
        duration_s=20.0,
        warmup_s=0.0,
        interval_s=0.0,
        # 1.2 Hz. The 5-7 Hz figure that used to be quoted here belongs to a
        # DIFFERENT test: key tapping (index finger on a switch, wrist resting,
        # amplitude unconstrained), which is the Halstead-Reitan / BRAIN /
        # TAS-Test-keyboard family. This is the opposition paradigm — thumb to
        # index through the widest range of motion, the MDS-UPDRS 3.4 movement —
        # and it runs at 2.4-3.6 Hz in the literature: TapTalk 2.55/2.70 Hz on
        # the same instruction, Kwon 2022 2.69 Hz at 50-69 and 2.36 at 70-89.
        # See research/01-webcam-hand-motor.md "Two tapping paradigms".
        # 1.2 Hz is what 75 recorded runs of THIS pipeline actually produce
        # (observed 0.38-2.42 Hz) — about half the age-matched norm, a gap the
        # practice plan exists to test. It is the observed centre, not a
        # normative rate, and not the pace to coach toward: see
        # docs/TAPPING_PRACTICE_PLAN.md §2.
        expected_rate_hz=1.2,
        max_rate_hz=5.0,               # debounce ceiling — 100 ms, unchanged
        min_taps=6,                    # 5 intervals — below that an SD is noise
        trim_taps=2,
        cv_typical=15.0,
        cv_monitor=25.0,
        thresholds_note="Provisional bands - to be calibrated against normative data.",
        # 0.5 Hz (interval 2 s) — below the whole observed distribution, so it
        # catches an abandoned or barely-moving attempt and nothing else.
        # Distinguishing a genuine max-effort run from a merely comfortable one
        # is a coaching problem, not a scoring one: see the practice plan.
        min_effort_hz=0.5,
        instructions=(
            "Using the hand you write with:",
            "Tap your INDEX FINGER and THUMB together",
            "as BIG and as FAST as you can.",
            "Open wide, close fully - keep going for 20 seconds.",
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
