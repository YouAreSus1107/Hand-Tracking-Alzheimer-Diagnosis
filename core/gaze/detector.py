"""
Saccade event extraction (OCULOMOTOR_TEST_PLAN.md §3.2): per-trial gaze
positions → onset / direction / latency / correctness. Pure logic, no OpenCV —
unit-testable with synthetic traces (parallels core/tapping/detector.py
`TapDetector`).

Timing is anchored to t₀ = the frame the target dot was first actually
rendered (the caller stamps it).

Three things make the reading tolerant of a real webcam session, all of them
lessons the tapping detector learned first:

  - **Position is measured from this trial's own baseline, not from an absolute
    zero.** The calibrated centre goes stale over a four-minute run — the head
    shifts a few millimetres and every reading carries an offset — and the eye
    is not always back on the cross when the dot appears. Against a fixed zero
    that residual offset already sits outside the deadband on frame one, so
    onset fired at ~0 ms and the trial was thrown out as *anticipatory* even
    when it contained a textbook saccade. Over the recorded session history
    that was 21% of every trial attempted. The caller passes the gaze reading
    that meant "on the cross" for this trial (the settle gate's median);
    `None` asks the trial to estimate it from its own pre-saccadic window,
    which is safe because nothing before MIN_LATENCY_MS can be a response.

  - **Two thresholds, not one.** A candidate onset opens at `onset` and is only
    accepted once that same-sign run's peak reaches `confirm`. Latency is
    stamped at the candidate's first frame, so the low threshold buys
    sensitivity while the high one keeps a drift wobble from being read as a
    saccade. Simply lowering the single deadband to 0.22 bought the same
    validity at nearly double the prosaccade error rate — people do not look
    the wrong way at a dot that often, so those were false onsets.

  - **`confirm` follows the excursion actually being performed** (see
    `SaccadeEnvelope`), because saccade amplitude in these units is not
    constant across a run: it collapses when the person drifts back from the
    camera, and a frozen threshold then reads a whole block as no-response.

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

# Two-tier onset. The candidate opens at ONSET_FRAC of the confirm threshold
# and is accepted only once the run's peak reaches the confirm threshold.
ONSET_FRAC = 0.5
# Floor on the confirm threshold, in normalized position units. This is the
# guard that stops a still eye manufacturing saccades out of tracker noise —
# the same role ADAPT_MIN_RANGE_FRAC plays in the tapping detector, and the
# same warning applies: do not lower it without re-running the replay sweep
# over results/*oculomotor*.json.
CONFIRM_MIN = 0.15
# Baseline fallback window. MIN_LATENCY_MS is 90 ms, so a sample inside it
# cannot yet be a response to the dot and is by definition pre-saccadic.
BASELINE_WINDOW_S = MIN_LATENCY_MS / 1000.0

# Settle gate (SettleGate): how long the eye must read steady, and how far it
# may wander inside that window, before a trial is allowed to start.
SETTLE_HOLD_S = 0.30
SETTLE_SPREAD = 0.18

# Outcome values: "correct", "error_uncorrected", "error_corrected",
# "anticipatory", "no_response", "face_lost".
VALID_OUTCOMES = ("correct", "error_uncorrected", "error_corrected")


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


@dataclass(frozen=True)
class TrialResult:
    target_dir: int              # +1 right, −1 left
    direction: int | None        # first-saccade direction; None if no onset
    latency_ms: float | None
    outcome: str
    corrected: bool              # anti error later self-corrected
    baseline: float = 0.0        # gaze reading that meant "on the cross"
    onset_thr: float = 0.0       # thresholds actually in force, for the report
    confirm_thr: float = 0.0
    peak: float = 0.0            # largest excursion from baseline this trial

    @property
    def valid(self) -> bool:
        return self.outcome in VALID_OUTCOMES

    @property
    def is_error(self) -> bool:
        return self.outcome in ("error_uncorrected", "error_corrected")


class SaccadeEnvelope:
    """Rolling estimate of the saccade excursion this person is *currently*
    producing, so the confirm threshold tracks it (parallels the tapping
    detector's rolling envelope).

    Calibration measures a deliberate, generous look at a dot; the excursions
    inside a block are smaller, and they shrink further as the person settles
    back from the camera. Sessions in results/ show an anti block whose peaks
    fell to 0.3–0.7 against a frozen 0.36 threshold — eighteen of twenty trials
    recorded as no-response while the person was doing the task correctly.
    """

    WINDOW = 6           # trials the median is taken over
    MIN_TRIALS = 3       # below this the calibrated seed is used unchanged
    PEAK_FRAC = 0.40     # confirm = this fraction of the recent median peak
    MIN_PEAK = 0.15      # peaks below this are a still eye, not a saccade

    def __init__(self, seed: float):
        self.seed = max(CONFIRM_MIN, seed)
        self._peaks: list[float] = []

    def confirm_threshold(self) -> float:
        """The confirm threshold for the next trial. Clamped to the calibrated
        seed above and CONFIRM_MIN below: the envelope may only make the test
        *more* forgiving than calibration, never less, and never so forgiving
        that tracker noise clears it."""
        if len(self._peaks) < self.MIN_TRIALS:
            return self.seed
        recent = _median(self._peaks[-self.WINDOW:])
        return max(CONFIRM_MIN, min(self.seed, self.PEAK_FRAC * recent))

    def observe(self, result: TrialResult) -> None:
        """Fold one finished trial's peak excursion into the estimate."""
        if result.peak > self.MIN_PEAK:
            self._peaks.append(result.peak)


class SaccadeTrial:
    """One trial's detector. Feed `update(t, pos)` every frame the target is
    on screen (pos None = face lost / blink), then `finalize()`.

    `deadband` is the confirm threshold (the calibrated value, or whatever the
    envelope has narrowed it to). `baseline` is the gaze reading that meant
    "on the cross" for this trial; pass None to have the trial estimate it from
    its own pre-saccadic window.
    """

    def __init__(self, t0: float, target_dir: int, deadband: float,
                 is_anti: bool, baseline: float | None = 0.0):
        self.t0 = t0
        self.target_dir = target_dir
        self.confirm = max(CONFIRM_MIN, deadband)
        self.onset = self.confirm * ONSET_FRAC
        self.deadband = self.confirm     # callers read it to draw the band
        self.is_anti = is_anti
        self.baseline = baseline
        self.series: list[tuple[float, float | None]] = []   # (t−t0, pos)

    def update(self, t: float, pos: float | None) -> None:
        self.series.append((t - self.t0, pos))

    def _resolved_baseline(self) -> float:
        if self.baseline is not None:
            return self.baseline
        pre = [p for dt, p in self.series
               if p is not None and dt <= BASELINE_WINDOW_S]
        return _median(pre) if pre else 0.0

    def finalize(self) -> TrialResult:
        base = self._resolved_baseline()
        frames = len(self.series)
        missing = sum(1 for _, p in self.series if p is None)

        run_sign = 0         # sign of the current out-of-deadband run
        run_len = 0
        run_t = 0.0          # time of the run's first frame
        run_peak = 0.0
        onset_t: float | None = None
        onset_dir: int | None = None
        corrected = False
        peak = 0.0

        for dt, p in self.series:
            if p is None:
                run_sign, run_len = 0, 0
                continue
            v = p - base
            peak = max(peak, abs(v))
            if v > self.onset:
                sign = 1
            elif v < -self.onset:
                sign = -1
            else:
                sign = 0

            if sign == 0 or sign != run_sign:
                run_sign, run_len, run_t, run_peak = sign, 0, dt, 0.0
            if sign == 0:
                continue
            run_len += 1
            run_peak = max(run_peak, abs(v))
            # A run is a saccade only once it is both sustained and large.
            if run_len < DEBOUNCE_FRAMES or run_peak < self.confirm:
                continue
            if onset_t is None:
                if run_t * 1000 <= RESPONSE_WINDOW_MS:
                    onset_t, onset_dir = run_t, sign
            elif sign != onset_dir:
                # crossed to the other side after the first saccade
                corrected = True

        shared = dict(baseline=base, onset_thr=self.onset,
                      confirm_thr=self.confirm, peak=peak)

        if onset_t is None:
            missing_frac = missing / frames if frames else 1.0
            outcome = "face_lost" if missing_frac > FACE_LOST_FRAC else "no_response"
            return TrialResult(self.target_dir, None, None, outcome, False,
                               **shared)

        latency = onset_t * 1000
        if latency < MIN_LATENCY_MS:
            return TrialResult(self.target_dir, onset_dir, latency,
                               "anticipatory", False, **shared)

        toward = onset_dir == self.target_dir
        error = toward if self.is_anti else not toward
        if not error:
            outcome = "correct"
            corrected = False
        else:
            outcome = "error_corrected" if corrected else "error_uncorrected"
        return TrialResult(self.target_dir, onset_dir, latency,
                           outcome, corrected, **shared)


class SettleGate:
    """Holds the trial back until the eye is actually back on the cross, and
    reports where "on the cross" was.

    The calibrated centre goes stale across a run - a few millimetres of head
    movement offsets every reading - and the eye is not always back from the
    last target when the next dot is due. The detector used to read that
    residual offset as a saccade at 0 ms and discard the trial as an early
    start; over the recorded history that cost 21% of every trial attempted.

    So the gate deliberately tests *steadiness*, never nearness to zero. An eye
    parked calmly on the cross whose map has drifted to -0.7 must pass: that
    offset is exactly what the baseline is for, and gating on |pos| would hang
    the run precisely when drift is worst. The median of the settled window is
    handed to `SaccadeTrial` as its baseline.
    """

    def __init__(self):
        self._window: list[tuple[float, float]] = []   # (t, pos)
        self._steady = False

    def reset(self) -> None:
        self._window.clear()
        self._steady = False

    def update(self, t: float, pos: float | None) -> None:
        if pos is None:
            self._window.clear()        # a blink is not a steady eye
            self._steady = False
            return
        self._window.append((t, pos))
        cutoff = t - SETTLE_HOLD_S
        while len(self._window) > 2 and self._window[0][0] < cutoff:
            self._window.pop(0)
        # Recomputed every frame rather than latched on first success: an eye
        # that settles early and then wanders during the rest of the dwell must
        # not hand over the reading it had a second ago.
        if self._window[0][0] > cutoff or len(self._window) < 3:
            self._steady = False        # window not yet a full SETTLE_HOLD_S
            return
        vals = [p for _, p in self._window]
        self._steady = (max(vals) - min(vals)) <= SETTLE_SPREAD

    @property
    def settled(self) -> bool:
        """Whether the eye is steady *now*. The caller reads this on the frame
        it decides to advance, and stops feeding the gate at that point, so the
        window it then reads is the one that passed."""
        return self._steady

    def baseline(self) -> float | None:
        """Where the eye was resting, or None when the gate timed out without
        ever settling - which asks the trial to fall back to its own
        pre-saccadic window. A wandering eye's median is not a resting point,
        and handing one over would be worse than not answering."""
        if not self._steady or not self._window:
            return None
        vals = sorted(p for _, p in self._window)
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
