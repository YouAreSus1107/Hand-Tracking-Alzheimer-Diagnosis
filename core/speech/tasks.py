"""
Speech task registry — the single source of truth for every speech paradigm
(SPEECH_TEST_PLAN.md §2), the speech counterpart of core/tapping/modes.py
TapMode and core/gaze/tasks.py SaccadeTask. Durations, limits, bands and the
on-screen copy all hang off one entry, so configuration and the instructions a
person reads can never drift apart.

Two parts, one per task type:
  SpeechTask     "pa-ta-ka" diadochokinesis — rate, rhythm and sequencing.
                 The pa-pa-pa mode was dropped: pa-ta-ka already measures its
                 rate, and adds the sequencing a single syllable cannot.
  PhonationTask  a sustained "ahhh" — voice stability (jitter, shimmer, HNR,
                 vocal tremor), phase 3 of the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_NOTE = "Provisional bands - to be calibrated against normative data."


@dataclass(frozen=True)
class SpeechTask:
    key: str
    title: str                  # e.g. "Pa-Ta-Ka"
    utterance: str              # what the person says, shown large on screen
    # The syllable cycle the person is asked to repeat, as consonant labels.
    # The optional phoneme recogniser (core/speech/phonemes.py) scores
    # sequencing against it; the envelope engine never reads it.
    cycle: tuple[str, ...]
    duration_s: float           # recorded (and scored) window
    trim_s: float               # ramp-up dropped before scoring (plan §2.1)
    # Fastest physically plausible syllable rate. Drives the minimum gap
    # between two detected syllables — the debounce, as max_rate_hz does for
    # tapping. Diadochokinetic rates top out near 8 syll/s in healthy adults.
    max_rate_hz: float
    # Absolute floor below which the recording is not a DDK attempt at all
    # (someone stopped, or said it once). Rejects an abandoned run, nothing else.
    min_effort_hz: float
    min_syllables: int          # below this an interval SD is noise
    cv_typical: float           # rhythm CV% below this → within typical range
    cv_monitor: float           # below this → monitor; above → follow-up
    thresholds_note: str
    instructions: tuple = field(default_factory=tuple)
    summary: str = ""
    sample_rate: int = 16000    # DDK energy sits well below 8 kHz; the
                                # phoneme model expects exactly 16 kHz
    kind: str = "ddk"

    @property
    def min_gap_s(self) -> float:
        return 1.0 / self.max_rate_hz

    @property
    def cv_band_width(self) -> float:
        """Width of the middle band — the confidence score measures its error
        bar against this, exactly as the tapping test does."""
        return self.cv_monitor - self.cv_typical


@dataclass(frozen=True)
class PhonationTask:
    key: str
    title: str
    utterance: str
    duration_s: float           # recorded window
    # Only the steady middle is scored: jitter and shimmer are unreliable at
    # the onset and release of a vowel (plan §2.1).
    skip_start_s: float
    skip_end_s: float
    min_voiced_s: float         # voiced time needed inside the scored segment
    f0_floor_hz: float          # Praat pitch range — wide enough for adult
    f0_ceiling_hz: float        # male and female voices without a profile
    jitter_typical: float       # jitter (local) % below this → typical
    jitter_monitor: float       # below this → monitor; above → follow-up
    thresholds_note: str
    instructions: tuple = field(default_factory=tuple)
    summary: str = ""
    sample_rate: int = 44100    # perturbation measures want the full band
    kind: str = "phonation"


# DDK bands. Deliberately the same edges as the tapping test's provisional
# bands, because the metric has the same shape (CV% of a repetition interval)
# and no DDK-specific normative cut-off has been transcribed yet. PROVISIONAL —
# not a cited clinical cut-off (SPEECH_TEST_PLAN.md §6).
TASKS: dict[str, SpeechTask] = {
    "ptk": SpeechTask(
        key="ptk",
        title="Pa-Ta-Ka",
        utterance="pa-ta-ka",
        cycle=("pa", "ta", "ka"),
        duration_s=8.0,
        trim_s=1.0,
        max_rate_hz=10.0,
        min_effort_hz=1.5,
        min_syllables=10,
        cv_typical=15.0,
        cv_monitor=25.0,
        thresholds_note=_NOTE,
        instructions=(
            "Take a breath, then say",
            "PA-TA-KA  PA-TA-KA  PA-TA-KA ...",
            "as FAST and as EVENLY as you can,",
            "without stopping, for 8 seconds.",
        ),
        summary="Sequential motion rate: speed, rhythm and sequencing.",
    ),
}

DEFAULT_TASK = "ptk"

# Phonation bands. The lower edge is the MDVP pathology threshold for jitter
# (local), 1.04% — the figure Praat's own documentation quotes; the upper edge
# (2×) is not from a source. PROVISIONAL, and the AD voice-acoustic evidence is
# thinner than the speech-rate evidence (SPEECH_TEST_PLAN.md §1.1, §6).
PHONATION = PhonationTask(
    key="ahh",
    title="Sustained Ahh",
    utterance="ahhh",
    duration_s=6.0,
    skip_start_s=1.0,
    skip_end_s=0.5,
    min_voiced_s=2.5,
    f0_floor_hz=75.0,
    f0_ceiling_hz=600.0,
    jitter_typical=1.04,
    jitter_monitor=2.08,
    thresholds_note=_NOTE,
    instructions=(
        "Take a breath, then say",
        "AHHHHHHHH ...",
        "at a comfortable pitch, as STEADY as you can,",
        "for 6 seconds.",
    ),
    summary="Sustained vowel: voice stability and vocal tremor.",
)
