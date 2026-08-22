"""
Saccade event extraction (OCULOMOTOR_TEST_PLAN.md §3.2): per-trial gaze
positions → onset / direction / latency / correctness. Pure logic, no OpenCV —
unit-testable with synthetic traces (parallels core/tapping/detector.py
`TapDetector`).

Timing is anchored to t₀ = the frame the target dot was first actually
rendered (the caller stamps it). Onset = the first frame after t₀ where the
signed gaze position leaves the deadband and keeps that sign for ≥2 frames
(debounce against single-frame tracker noise).

Validity filters (Antoniades et al. 2013):
  latency < MIN_LATENCY_MS      → anticipatory/express, excluded
  no onset within the window    → no_response, excluded
  face lost for much of trial   → face_lost, excluded
An anti-saccade error whose gaze later crosses to the correct side within the
hold window counts as a *corrected* error.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_LATENCY_MS = 90.0        # below this a saccade cannot be stimulus-driven
RESPONSE_WINDOW_MS = 800.0   # no deadband exit by then → no_response
DEBOUNCE_FRAMES = 2          # consecutive same-sign frames to confirm onset
FACE_LOST_FRAC = 0.4         # >this fraction of frames missing → face_lost

# Outcome values: "correct", "error_uncorrected", "error_corrected",
# "anticipatory", "no_response", "face_lost".
VALID_OUTCOMES = ("correct", "error_uncorrected", "error_corrected")


@dataclass(frozen=True)
class TrialResult:
    target_dir: int              # +1 right, −1 left
    direction: int | None        # first-saccade direction; None if no onset
    latency_ms: float | None
    outcome: str
    corrected: bool              # anti error later self-corrected

    @property
    def valid(self) -> bool:
        return self.outcome in VALID_OUTCOMES

    @property
    def is_error(self) -> bool:
        return self.outcome in ("error_uncorrected", "error_corrected")


class SaccadeTrial:
    """One trial's detector. Feed `update(t, pos)` every frame the target is
    on screen (pos None = face lost / blink), then `finalize()`."""

    def __init__(self, t0: float, target_dir: int, deadband: float,
                 is_anti: bool):
        self.t0 = t0
        self.target_dir = target_dir
        self.deadband = deadband
        self.is_anti = is_anti
        self._run_sign = 0           # sign of the current out-of-deadband run
        self._run_len = 0
        self._run_t0 = 0.0           # time of the run's first frame
        self._onset_t: float | None = None
        self._onset_dir: int | None = None
        self._corrected = False
        self._frames = 0
        self._missing = 0
        self.series: list[tuple[float, float | None]] = []   # (t−t0, pos)

    def update(self, t: float, pos: float | None) -> None:
        self._frames += 1
        self.series.append((t - self.t0, pos))
        if pos is None:
            self._missing += 1
            self._run_sign, self._run_len = 0, 0
            return
        sign = 0
        if pos > self.deadband:
            sign = 1
        elif pos < -self.deadband:
            sign = -1

        if sign == 0 or sign != self._run_sign:
            self._run_sign, self._run_len = sign, 0
            self._run_t0 = t
        if sign != 0:
            self._run_len += 1
            if self._run_len >= DEBOUNCE_FRAMES:
                if self._onset_t is None:
                    within = (self._run_t0 - self.t0) * 1000 <= RESPONSE_WINDOW_MS
                    if within:
                        self._onset_t = self._run_t0
                        self._onset_dir = sign
                elif (self._onset_dir is not None
                      and sign != self._onset_dir):
                    # crossed to the other side after the first saccade
                    self._corrected = True

    def finalize(self) -> TrialResult:
        if self._onset_t is None:
            missing_frac = self._missing / self._frames if self._frames else 1.0
            outcome = "face_lost" if missing_frac > FACE_LOST_FRAC else "no_response"
            return TrialResult(self.target_dir, None, None, outcome, False)

        latency = (self._onset_t - self.t0) * 1000
        if latency < MIN_LATENCY_MS:
            return TrialResult(self.target_dir, self._onset_dir, latency,
                               "anticipatory", False)

        toward = self._onset_dir == self.target_dir
        error = toward if self.is_anti else not toward
        if not error:
            outcome = "correct"
            corrected = False
        else:
            corrected = self._corrected
            outcome = "error_corrected" if corrected else "error_uncorrected"
        return TrialResult(self.target_dir, self._onset_dir, latency,
                           outcome, corrected)
