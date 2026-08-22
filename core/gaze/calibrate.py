"""
3-point gaze calibration (OCULOMOTOR_TEST_PLAN.md §2.2): look at
center → left → right dots; the median iris ratio at each maps the raw signal
to a signed screen position and sets the central deadband. Pure logic, no
OpenCV — unit-testable with synthetic traces (parallels
core/tapping/detector.py `Calibrator`).

Convention: `GazeMap.position()` returns +1 at the *right* calibration target
and −1 at the *left* one. Because the calibration dots are drawn at the same
screen positions as the trial targets, this holds regardless of whether the
camera frame is mirrored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

STAGES = ("center", "left", "right")

STAGE_FRAMES = 30        # ~1 s of valid samples per point at 30 fps
SETTLE_S = 0.6           # ignore samples right after a dot appears (eye travel)
STAGE_TIMEOUT_S = 12.0   # per-stage "having trouble?" coaching threshold
MIN_SEPARATION = 0.025   # min |side − center| ratio gap for a usable map
DEADBAND_MIN = 0.30      # deadband bounds, in normalized position units
DEADBAND_MAX = 0.55
DEADBAND_NOISE_K = 3.0   # deadband = K × center noise (normalized), clamped


@dataclass(frozen=True)
class GazeMap:
    center: float
    left: float
    right: float
    deadband: float

    def position(self, ratio: float) -> float:
        """Signed horizontal gaze position: +1 at the right target, −1 at the
        left target, 0 at center. Clamped to ±1.5 (beyond-target glances)."""
        d = ratio - self.center
        dr = self.right - self.center
        dl = self.left - self.center
        if d * dr > 0:
            pos = d / dr
        elif d * dl > 0:
            pos = -d / dl
        else:
            pos = 0.0
        return max(-1.5, min(1.5, pos))


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _sd(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))


class GazeCalibrator:
    """Guided 3-point calibration. Feed `update(t, ratio)` every frame while
    the current stage's dot is shown (ratio None = no face / blink); read
    `stage` to know which dot to draw. Ends with `done` or `failed`."""

    def __init__(self, now: float):
        self._stage_i = 0
        self._stage_t0 = now
        self._samples: dict[str, list[float]] = {s: [] for s in STAGES}
        self.done = False
        self.failed = False
        self.fail_reason: str | None = None
        self._map: GazeMap | None = None

    @property
    def stage(self) -> str:
        return STAGES[min(self._stage_i, len(STAGES) - 1)]

    @property
    def stage_progress(self) -> float:
        return min(1.0, len(self._samples[self.stage]) / STAGE_FRAMES)

    @property
    def progress(self) -> float:
        """0→1 gauge across all three points, for the calibration UI."""
        return min(1.0, (self._stage_i + self.stage_progress) / len(STAGES))

    def stage_timed_out(self, t: float) -> bool:
        return (t - self._stage_t0) > STAGE_TIMEOUT_S

    def update(self, t: float, ratio: float | None) -> bool:
        """Feed one frame. Returns True on the frame a stage completes
        (so the UI can advance its dot / play a tick)."""
        if self.done or self.failed:
            return False
        if ratio is None or (t - self._stage_t0) < SETTLE_S:
            return False
        samples = self._samples[self.stage]
        samples.append(ratio)
        if len(samples) < STAGE_FRAMES:
            return False
        if self._stage_i < len(STAGES) - 1:
            self._stage_i += 1
            self._stage_t0 = t
        else:
            self._finish()
        return True

    def _finish(self) -> None:
        c = _median(self._samples["center"])
        l = _median(self._samples["left"])
        r = _median(self._samples["right"])
        dl, dr = l - c, r - c
        if abs(dl) < MIN_SEPARATION or abs(dr) < MIN_SEPARATION:
            self.failed = True
            self.fail_reason = ("Eye movement between the dots was too small "
                                "to measure - move a little closer and retry.")
            return
        if dl * dr > 0:
            self.failed = True
            self.fail_reason = ("The left and right readings overlapped - "
                                "keep your head still and retry.")
            return
        half_range = (abs(dl) + abs(dr)) / 2
        noise = _sd(self._samples["center"]) / half_range
        deadband = max(DEADBAND_MIN, min(DEADBAND_MAX, DEADBAND_NOISE_K * noise))
        self._map = GazeMap(center=c, left=l, right=r, deadband=deadband)
        self.done = True

    def result(self) -> GazeMap:
        if self._map is None:
            raise RuntimeError("Calibration not complete")
        return self._map
