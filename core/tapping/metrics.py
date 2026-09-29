"""
Metrics: tap-time + distance series → scored biomarkers. Pure functions,
unit-testable against synthetic signals (FINGER_TAPPING_REVISION_PLAN.md §C3).

Derived per run:
  frequency_hz          taps per second
  mean_iti_ms / iiv_ms  inter-tap interval mean and SD (ddof=1)
  cv_pct                IIV / mean · 100 — the scale-invariant headline
  amplitude_mean / cv   valley-to-peak excursion per tap (span-normalized)
  decrement_pct_per_s   slope of instantaneous rate over the trial (fatigue)
  sync_sd_ms            paced only: SD of tap-to-nearest-beat latency
"""

from __future__ import annotations

import math

from core.framing import overlaps

from .confidence import confidence, straddles_band
from .gaps import count_interruptions, label_gaps, restore_missed_tap
from .modes import TapMode

_BANDS = ("success", "warning", "danger")

def _sd(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(var)


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _slope(xs: list[float], ys: list[float]) -> float | None:
    """Least-squares slope of ys over xs."""
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom < 1e-9:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def band(cv_pct: float, mode: TapMode) -> tuple[str, str]:
    """(status_token, plain-language label) for a CV% value. Status tokens map
    to the style-guide clinical semantics — always shown with icon + word."""
    if cv_pct < mode.cv_typical:
        return "success", "Within typical range"
    if cv_pct < mode.cv_monitor:
        return "warning", "Mild variability - consider monitoring"
    return "danger", "Elevated variability - recommend follow-up"


def _pairs(tap_times: list[float], blackouts=None):
    """Consecutive tap pairs, minus any that touch a blackout -- a stretch when
    the hand was part-way out of frame and the run was paused. The interval
    spanning a pause is not a real one, so it is dropped rather than scored."""
    return [(tap_times[i], tap_times[i + 1]) for i in range(len(tap_times) - 1)
            if not overlaps(tap_times[i], tap_times[i + 1], blackouts)]


def _interval_stats(mode: TapMode, tap_times: list[float],
                    blackouts=None) -> dict | None:
    """Return the shared temporal core for a run or compatibility sub-window."""
    if len(tap_times) < 2:
        return None
    iti_all = [(b - a) * 1000 for a, b in _pairs(tap_times, blackouts)]
    if not iti_all:
        return None
    cutoff = mode.max_iti_ms if mode.paced else 3.0 * _median(iti_all)
    iti = [v for v in iti_all if v <= cutoff]
    if len(iti) < 2:
        return None
    mean_iti = sum(iti) / len(iti)
    iiv = _sd(iti)
    if iiv is None or mean_iti <= 0:
        return None
    return {"iti_all": iti_all, "iti": iti, "cutoff": cutoff,
            "mean_iti_ms": mean_iti, "iiv_ms": iiv,
            "cv_pct": iiv / mean_iti * 100.0,
            "frequency_hz": 1000.0 / mean_iti,
            "rejected_frac": (len(iti_all) - len(iti)) / len(iti_all)}


def compute_metrics(mode: TapMode,
                    tap_times: list[float],
                    series: list[tuple[float, float]],
                    t_start: float,
                    t_end: float,
                    beat_times: list[float] | None = None,
                    hand_visible_ratio: float = 1.0,
                    camera_fps: float | None = None,
                    near_miss: int = 0,
                    blackouts: list[tuple[float, float]] | None = None) -> dict:
    """Score one recording. Always returns a dict; `scoreable` is False with a
    specific human-readable `reason` when a score can't be computed (audit A10).

    `blackouts` are (start, end) stretches, on the same clock as the taps,
    when the hand was out of frame (core/framing.py); intervals touching them
    are excluded. None -- the remote port's only case -- changes nothing.

    One missed tap is forgiven (core/tapping/gaps.py): when the only long
    interval in the run is a full closure the detector failed to count, that
    tap is restored and the run rescored. The forgiveness may move the verdict
    by one band at most -- if restoring a single inferred tap would turn a
    Follow-up into Typical, the evidence rests on the inference alone, so the
    run keeps its measured score. Pauses and partial closures always count.
    `cv_pct_unrepaired` keeps the score before any repair."""
    kw = dict(beat_times=beat_times, hand_visible_ratio=hand_visible_ratio,
              camera_fps=camera_fps, near_miss=near_miss, blackouts=blackouts)
    out = _score(mode, tap_times, series, t_start, t_end, **kw)
    scored = scored_taps(mode, tap_times)
    labels = label_gaps(scored, series, blackouts) if out["scoreable"] else []
    out.update(missed_tap_forgiven=0, cv_pct_unrepaired=out["cv_pct"],
               interruptions=count_interruptions(labels) if out["scoreable"] else None)
    if not out["scoreable"]:
        return out
    t_new = restore_missed_tap(scored, series, blackouts)
    if t_new is None:
        return out
    fixed = _score(mode, sorted(tap_times + [t_new]), series, t_start, t_end, **kw)
    if (not fixed["scoreable"]
            or _BANDS.index(out["status"]) - _BANDS.index(fixed["status"]) > 1):
        return out
    fixed.update(missed_tap_forgiven=1, cv_pct_unrepaired=out["cv_pct"],
                 interruptions=out["interruptions"])
    return fixed


def scored_taps(mode: TapMode, tap_times: list[float]) -> list[float]:
    """The taps that count: the ramp-up trim, when enough taps remain."""
    if len(tap_times) - mode.trim_taps >= mode.min_taps:
        return tap_times[mode.trim_taps:]
    return tap_times


def _score(mode: TapMode, tap_times: list[float],
           series: list[tuple[float, float]], t_start: float, t_end: float,
           beat_times=None, hand_visible_ratio: float = 1.0,
           camera_fps: float | None = None, near_miss: int = 0,
           blackouts=None) -> dict:
    """compute_metrics() without the missed-tap repair."""
    out: dict = {
        "scoreable": False,
        "reason": None,
        "taps": len(tap_times),
        "duration_s": round(t_end - t_start, 2),
        "frequency_hz": None, "mean_iti_ms": None, "iiv_ms": None,
        "cv_pct": None, "amplitude_mean": None, "amplitude_cv_pct": None,
        "decrement_pct_per_s": None, "sync_sd_ms": None,
        "mean_latency_ms": None, "hits": None, "misses": None,
        "status": None, "label": None,
        "n_intervals": None, "cv_ci_low_pct": None, "cv_ci_high_pct": None,
        "confidence_pct": None, "band_edge": None,
        "taps_w10": None, "frequency_hz_w10": None, "cv_pct_w10": None,
        "near_miss_taps": near_miss, "opening_shrink_ratio": None,
    }

    if len(tap_times) < mode.min_taps:
        if hand_visible_ratio < 0.8:
            out["reason"] = ("Your hand was out of view for part of the test - "
                             "keep it in the frame and try again.")
        elif near_miss >= max(2, len(tap_times)):
            out["reason"] = (f"{near_miss} closures were too shallow to count as "
                             "taps - open the hand fully between taps.")
        else:
            out["reason"] = (f"Only {len(tap_times)} taps detected - at least "
                             f"{mode.min_taps} are needed for a reliable score.")
        return out

    # Explicit ramp-up trim: only when enough taps remain (audit A10).
    taps = scored_taps(mode, tap_times)

    stats = _interval_stats(mode, taps, blackouts)
    iti = stats["iti"] if stats else []
    if len(iti) < mode.min_taps - 1:
        out["reason"] = ("Tapping was too irregular to score - large pauses "
                         "interrupted the rhythm. Try to keep a continuous motion.")
        return out

    mean_iti = stats["mean_iti_ms"]
    cv = stats["cv_pct"]
    cutoff = stats["cutoff"]
    out.update(mean_iti_ms=mean_iti, iiv_ms=stats["iiv_ms"], cv_pct=cv,
               frequency_hz=stats["frequency_hz"], n_intervals=len(iti))

    # Floor for having a rhythm at all. Below roughly one tap every two
    # seconds the hand is pausing between taps rather than tapping, and CV%
    # is then measuring the pauses. This is deliberately set below the whole
    # observed range of real runs — it rejects an abandoned attempt, not a
    # merely unhurried one. CV% cannot tell a genuine maximum effort from a
    # comfortable pace, and a scoring gate is the wrong place to try: the
    # remedy for "fast" meaning different things to different people is
    # coaching the pace during practice (docs/tests/TAPPING_PRACTICE_PLAN.md).
    if mode.min_effort_hz and stats["frequency_hz"] < mode.min_effort_hz:
        out["reason"] = (
            f"Tapping was too slow to score a rhythm "
            f"({stats['frequency_hz']:.1f} taps/s - long pauses between taps "
            f"leave no steady rhythm to measure). Try to keep a continuous "
            f"tapping motion.")
        return out

    quality = confidence(n_intervals=len(iti), cv_pct=cv, mean_iti_ms=mean_iti,
        band_width_pct=mode.cv_band_width, camera_fps=camera_fps,
        hand_visible_ratio=hand_visible_ratio, rejected_frac=stats["rejected_frac"],
        near_miss=near_miss, taps=len(tap_times))
    out["confidence_pct"] = quality["confidence_pct"]
    out["cv_ci_low_pct"] = quality["cv_ci_low_pct"]
    out["cv_ci_high_pct"] = quality["cv_ci_high_pct"]
    out["band_edge"] = int(straddles_band(quality["cv_ci_low_pct"],
        quality["cv_ci_high_pct"], mode.cv_typical, mode.cv_monitor))

    taps_w10 = [t for t in tap_times if t <= t_start + mode.compat_window_s]
    out["taps_w10"] = len(taps_w10)
    compat_taps = taps_w10
    if len(compat_taps) - mode.trim_taps >= mode.min_taps:
        compat_taps = compat_taps[mode.trim_taps:]
    compat = _interval_stats(mode, compat_taps, blackouts)
    if compat:
        out["frequency_hz_w10"] = compat["frequency_hz"]
        out["cv_pct_w10"] = compat["cv_pct"]

    # Speed decrement: slope of instantaneous rate at interval midpoints,
    # as % of mean rate per second (negative = slowing over the trial).
    mids, rates = [], []
    for a, b in _pairs(taps, blackouts):
        iti_i = (b - a) * 1000
        if iti_i <= cutoff:
            mids.append((a + b) / 2 - t_start)
            rates.append(1000.0 / iti_i)
    sl = _slope(mids, rates)
    if sl is not None and rates:
        mean_rate = sum(rates) / len(rates)
        if mean_rate > 0:
            out["decrement_pct_per_s"] = sl / mean_rate * 100.0

    # Amplitude per tap: max-min of the distance signal between taps.
    amps = []
    for a, b in _pairs(taps, blackouts):
        seg = [d for (t, d) in series if a <= t < b]
        if len(seg) >= 2:
            amps.append(max(seg) - min(seg))
    if len(amps) >= 2:
        out["amplitude_mean"] = sum(amps) / len(amps)
        a_sd = _sd(amps)
        if a_sd is not None and out["amplitude_mean"] > 0:
            out["amplitude_cv_pct"] = a_sd / out["amplitude_mean"] * 100.0
    # Shrinking openings (the "sequence effect" neurologists look for): the
    # last quarter of openings over the first. Information only -- on HUBU-FIS
    # it did not separate impaired from unimpaired hands (AUC 0.57).
    if len(amps) >= 8:
        k = max(3, len(amps) // 4)
        first = sum(amps[:k]) / k
        if first > 0:
            out["opening_shrink_ratio"] = (sum(amps[-k:]) / k) / first

    # Paced sync: nearest-beat assignment (replaces the mis-centered window
    # of audit A2 — no window edge to fall off).
    if mode.paced and beat_times:
        first_tap: dict[int, float] = {}
        half = mode.interval_s / 2
        for tt in tap_times:
            j = min(range(len(beat_times)), key=lambda k: abs(beat_times[k] - tt))
            if abs(tt - beat_times[j]) <= half and j not in first_tap:
                first_tap[j] = tt
        lats = [(first_tap[j] - beat_times[j]) * 1000 for j in sorted(first_tap)]
        out["hits"] = len(first_tap)
        out["misses"] = len(beat_times) - len(first_tap)
        if len(lats) >= 2:
            out["mean_latency_ms"] = sum(lats) / len(lats)
            out["sync_sd_ms"] = _sd(lats)

    out["status"], out["label"] = band(cv, mode)
    out["scoreable"] = True
    return out
