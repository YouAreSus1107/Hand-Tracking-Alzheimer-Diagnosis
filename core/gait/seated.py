"""
Seated tier of the walking test (GAIT_TEST_PLAN.md §3, blocks A1-A2): leg
agility and five sit-to-stands, from a side-on camera. Pure and stdlib-only;
the run loop feeds it raw pixel landmarks, one frame at a time.

Leg agility (UPDRS 3.8) is the finger-tapping construct in the leg, so it
reuses core/tapping's TapDetector unchanged: the signal is knee lift in thigh
lengths, and a stamp is the "close". The detector's rolling envelope matters
here for the same reason it does for fingers -- the lift shrinks over ten
seconds, and that shrinking is the decrement being measured.

Sit-to-stand (UPDRS 3.9) is read from how far the hip is above the knee, in
thigh lengths. Seated side-on, the thigh lies flat and its full length is in
the picture; standing, it hangs below the hip. So one number goes from about
0 to about 1 with no calibration object, whatever the chair height.
"""

from __future__ import annotations

from core.framing import overlaps
from core.tapping.detector import TapDetector
from core.tapping.metrics import _median, _sd, _slope

# ── Leg agility ────────────────────────────────────────────────────────────
# Knee lift the detector expects before its envelope has adapted (~1.3 s):
# a stamping foot lifts the knee roughly a fifth to a third of a thigh
# length. Only the seed; the thresholds then follow the lift actually made.
LIFT_SEED = 0.25
MAX_STAMP_HZ = 6.0          # debounce ceiling, well above any real stamping
EMA_ALPHA = 0.6
MIN_STAMPS = 6              # the same floor as finger tapping's min_taps


def knee_lift(knee_y: float, ref_y: float, thigh_px: float) -> float | None:
    """Knee height above its seated rest position, in thigh lengths."""
    if thigh_px <= 1e-6:
        return None
    return (ref_y - knee_y) / thigh_px


class LegRecorder:
    """One leg's 10 s of stamping."""

    def __init__(self):
        self.detector = TapDetector(min_intertap_s=0.5 / MAX_STAMP_HZ,
                                    ema_alpha=EMA_ALPHA,
                                    d_closed=0.0, d_open=LIFT_SEED)

    def update(self, t: float, lift: float | None) -> bool:
        return self.detector.update(t, lift)

    @property
    def stamps(self) -> list[float]:
        return self.detector.tap_times

    @property
    def series(self) -> list[tuple[float, float]]:
        return self.detector.series


def analyse_leg(stamps: list[float], series: list[tuple[float, float]],
                blackouts=None) -> dict:
    """Rate, rhythm and lift for one leg. Intervals that span a stretch the
    camera could not trust are dropped rather than scored as slow stamps."""
    out: dict = {"n_stamps": len(stamps), "scored": False}
    if len(stamps) < MIN_STAMPS:
        out["reason"] = "Too few stamps were seen to score this leg."
        return out
    intervals = [b - a for a, b in zip(stamps, stamps[1:])
                 if not overlaps(a, b, blackouts)]
    if len(intervals) < MIN_STAMPS - 1:
        out["reason"] = "The leg was out of view for too much of the block."
        return out
    # peak lift between consecutive stamps = one cycle's amplitude
    amps = []
    for a, b in zip(stamps, stamps[1:]):
        seg = [d for t, d in series if a < t < b]
        if seg:
            amps.append(max(seg))
    mean_iv = sum(intervals) / len(intervals)
    sd_iv = _sd(intervals)
    out.update(
        scored=True,
        rate_hz=round(1.0 / mean_iv, 2) if mean_iv > 0 else None,
        cv_pct=round(100.0 * sd_iv / mean_iv, 1) if sd_iv is not None else None,
        amp_pct=round(100.0 * _median(amps), 1) if amps else None,
        amp_decrement_pct=_decrement(amps),
        rate_slope=_rate_slope(stamps),
        intervals=len(intervals),
    )
    return out


def _decrement(amps: list[float]) -> float | None:
    """Change in lift from the first third of the cycles to the last, as % of
    the first. Negative = the lift shrank, the bradykinesia sequence effect."""
    n = len(amps)
    if n < 6:
        return None
    k = n // 3
    first = sum(amps[:k]) / k
    last = sum(amps[-k:]) / k
    if first <= 1e-6:
        return None
    return round(100.0 * (last - first) / first, 1)


def _rate_slope(stamps: list[float]) -> float | None:
    """Change in stamping rate over the block, Hz per second."""
    if len(stamps) < 4:
        return None
    mids = [(a + b) / 2 for a, b in zip(stamps, stamps[1:])]
    rates = [1.0 / (b - a) for a, b in zip(stamps, stamps[1:]) if b > a]
    s = _slope(mids[:len(rates)], rates)
    return round(s, 3) if s is not None else None


# ── Sit-to-stand ───────────────────────────────────────────────────────────
STAND_AT = 0.75             # stand index: standing once the hip is this high
SIT_AT = 0.30               # on the way down, below this is sitting again
RISE_START = 0.15           # a rise begins when the hip leaves the seat
ATTEMPT_MIN = 0.30          # a rise that peaks above this and falls back is a
                            # failed attempt; below it, shifting in the seat
HANDS_LOW_FRAC = 0.5        # wrist lower than halfway down the trunk = hands used
TARGET_STANDS = 5


def stand_index(hip_y: float, knee_y: float, thigh_px: float,
                seated_offset_px: float) -> float | None:
    """0 seated, ~1 standing: how far the hip rose above the knee, scaled so
    the seated pose reads 0 whatever the chair height. `seated_offset_px` is
    (knee_y - hip_y) measured while seated still."""
    span = thigh_px - seated_offset_px
    if thigh_px <= 1e-6 or span < 0.3 * thigh_px:
        return None
    return ((knee_y - hip_y) - seated_offset_px) / span


def hands_low(wrist_ys, shoulder_y: float, hip_y: float) -> bool:
    """True when either wrist is down in the lower half of the trunk or below:
    on the thighs or the armrests, i.e. pushing off. Arms crossed on the chest
    keep both wrists in the upper half."""
    torso = hip_y - shoulder_y
    if torso <= 1e-6:
        return False
    line = hip_y - HANDS_LOW_FRAC * torso
    return any(y is not None and y > line for y in wrist_ys)


class StandCounter:
    """Frame-by-frame sit-to-stand state machine."""

    SEATED, RISING, STANDING, LOWERING = "seated", "rising", "standing", "lowering"

    def __init__(self, t0: float):
        self.t0 = t0
        self.state = self.SEATED
        self.rise_start: float | None = None
        self.peak = 0.0
        self.stands: list[dict] = []        # {"start", "up", "down", "hands", "lean"}
        self.failed = 0
        self._hands = False
        self._lean = 0.0
        self.series: list[tuple[float, float]] = []

    def update(self, t: float, s: float | None, lean: float | None = None,
               hands: bool = False) -> None:
        if s is None:
            return
        self.series.append((t, s))
        if self.state == self.SEATED:
            if s > RISE_START:
                self.state = self.RISING
                self.rise_start, self.peak = t, s
                self._hands, self._lean = hands, lean or 0.0
        elif self.state == self.RISING:
            self.peak = max(self.peak, s)
            self._hands = self._hands or hands
            self._lean = max(self._lean, lean or 0.0)
            if s >= STAND_AT:
                self.stands.append({"start": self.rise_start, "up": t,
                                    "down": None, "hands": self._hands,
                                    "lean": round(self._lean, 1)})
                self.state = self.STANDING
            elif s < RISE_START * 0.66:
                if self.peak >= ATTEMPT_MIN:
                    self.failed += 1
                self.state = self.SEATED
        elif self.state == self.STANDING:
            if s < SIT_AT:
                self.state = self.LOWERING
        elif self.state == self.LOWERING:
            if s < RISE_START:
                self.stands[-1]["down"] = t
                self.state = self.SEATED
            elif s >= STAND_AT:
                self.state = self.STANDING

    @property
    def n_stands(self) -> int:
        return len(self.stands)

    @property
    def done(self) -> bool:
        """Five full stands and seated again after the fifth."""
        return (self.n_stands >= TARGET_STANDS
                and self.stands[TARGET_STANDS - 1]["down"] is not None)


def analyse_sts(counter: StandCounter, blackouts=None) -> dict:
    stands = counter.stands
    out: dict = {"n_stands": len(stands), "failed_attempts": counter.failed,
                 "scored": False}
    if not stands:
        out["reason"] = "No stand was seen - check that your hips and knees are in view."
        return out
    if any(overlaps(s["start"], s["up"], blackouts) for s in stands):
        out["hidden_rises"] = sum(overlaps(s["start"], s["up"], blackouts)
                                  for s in stands)
    rises = [s["up"] - s["start"] for s in stands]
    out.update(
        scored=True,
        completed=len(stands) >= TARGET_STANDS,
        rise_s_median=round(_median(rises), 2),
        lean_deg_median=round(_median([s["lean"] for s in stands]), 1),
        hands_used=sum(1 for s in stands if s["hands"]),
    )
    if len(stands) >= TARGET_STANDS:
        fifth = stands[TARGET_STANDS - 1]
        # Timed from the go beep. Both common end points are kept: at the
        # fifth full stand, and back in the seat after it.
        out["sts5_s"] = round(fifth["up"] - counter.t0, 2)
        if fifth["down"] is not None:
            out["sts5_sit_s"] = round(fifth["down"] - counter.t0, 2)
    return out
