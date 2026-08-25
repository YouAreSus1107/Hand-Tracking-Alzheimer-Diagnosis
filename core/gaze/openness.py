"""
Adaptive eyelid-openness gate (OCULOMOTOR_TEST_PLAN.md §3.1).

The iris landmarks are only worth reading while the pupil is actually visible,
so the tracker has to know when an eye is shut. The obvious test — lid gap
divided by eye width, below a fixed number — quietly excludes people:
palpebral-fissure height varies roughly two-fold between individuals (an
epicanthic fold, hooded or ptotic lids, and plain squinting at a bright screen
all shrink it), so one absolute threshold either lets real blinks through for
wide-open eyes or reads a narrow-eyed person as blinking on *every* frame.
The second case is the damaging one: every frame's gaze is discarded,
calibration never fills, trials score as face_lost, and the status chip still
cheerfully says the face was detected.

So the threshold is per-person and learned online, per eye (ptosis is often
one-sided). Each eye keeps a rolling high percentile of its own recent
openness as the baseline for "this eye, open", and a blink is a
*proportional* collapse away from that baseline. The baseline rises fast and
falls slowly: it locks onto the open state within a fraction of a second, a
blink is far too brief to move it, and a squint has to hold for several
seconds before it is adopted as the new resting aperture. That last part is
deliberate rather than a leak — somebody who narrows their eyes and stays
there for the rest of the run should go on being measured (noisily, with the
vertical proxy dropped and the frame counted in `gaze_valid_ratio`) instead of
producing nothing at all. An absolute floor still catches an eye that is
genuinely shut before the baseline has settled.

The vertical iris proxy gets a stricter gate than the horizontal one: a
lowered lid crops the iris from above, which biases iris-y long before it
disturbs iris-x. Horizontal saccades survive a half-closed eye; the vertical
spread signal that feeds the BCEA does not.

`open_frac` (openness ÷ baseline) is what the UI meters, so the person sees
the same number the gate is judging them by — and because it is relative,
narrow eyes read as fully open rather than as a permanent warning.

Pure logic, no OpenCV and no MediaPipe — unit-tested in
screening_tests/tests/test_gaze.py.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

ABS_FLOOR = 0.07        # lid gap under 7% of eye width: shut, for anyone
BLINK_FRAC = 0.55       # proportional collapse from this eye's own baseline
VERTICAL_FRAC = 0.78    # stricter gate before the vertical proxy is trusted
NARROW_BASELINE = 0.20  # an open baseline under this reads as a narrow aperture

WINDOW_S = 2.0          # rolling window the baseline observation is taken over
PCTL = 0.80             # blinks are <10% of frames, so p80 sits in the open state
MIN_SAMPLES = 5         # below this the window's max stands in for the percentile
RISE = 0.5              # baseline tracks upward fast...
FALL = 0.02             # ...and downward slowly (~1 s window turnover + ~5 s
                        # decay before a sustained squint becomes the baseline)


@dataclass(frozen=True)
class EyeState:
    """One eye, one frame."""
    open: bool           # iris-x is trustworthy
    vertical_ok: bool    # iris-y is trustworthy too (stricter)
    openness: float      # lid gap ÷ eye width, as measured
    baseline: float      # this eye's learned open aperture
    open_frac: float     # openness ÷ baseline — what the UI meters
    narrow: bool         # this eye's open aperture is a narrow one


def _percentile(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * len(s)))]


class OpennessGate:
    """One eye's blink gate. Feed `update(t, openness)` every frame the eye is
    measurable; the returned state says whether to trust that frame's iris."""

    def __init__(self):
        self._win: deque[tuple[float, float]] = deque()
        self._baseline: float | None = None

    @property
    def baseline(self) -> float | None:
        return self._baseline

    def update(self, t: float, openness: float) -> EyeState:
        self._win.append((t, openness))
        cutoff = t - WINDOW_S
        while self._win and self._win[0][0] < cutoff:
            self._win.popleft()

        vals = [v for _, v in self._win]
        # Before the window fills, its max stands in: it starts the baseline at
        # whatever this person's eye actually measures rather than at a guess,
        # so a narrow eye is never gated out during the first frames.
        obs = _percentile(vals, PCTL) if len(vals) >= MIN_SAMPLES else max(vals)
        if self._baseline is None:
            self._baseline = obs
        else:
            k = RISE if obs > self._baseline else FALL
            self._baseline += k * (obs - self._baseline)

        base = self._baseline
        frac = openness / base if base > 1e-6 else 0.0
        is_open = openness >= ABS_FLOOR and frac >= BLINK_FRAC
        return EyeState(open=is_open,
                        vertical_ok=is_open and frac >= VERTICAL_FRAC,
                        openness=openness, baseline=base, open_frac=frac,
                        narrow=base < NARROW_BASELINE)
