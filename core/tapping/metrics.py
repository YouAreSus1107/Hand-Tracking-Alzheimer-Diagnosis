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

from .confidence import confidence, straddles_band
from .modes import TapMode


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


def _interval_stats(mode: TapMode, tap_times: list[float]) -> dict | None:
    """Return the shared temporal core for a run or compatibility sub-window."""
    if len(tap_times) < 2:
        return None
    iti_all = [(tap_times[i + 1] - tap_times[i]) * 1000
               for i in range(len(tap_times) - 1)]
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
                    near_miss: int = 0) -> dict:
    """Score one recording. Always returns a dict; `scoreable` is False with a
    specific human-readable `reason` when a score can't be computed (audit A10)."""
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
        "near_miss_taps": near_miss,
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
    taps = tap_times
    if len(taps) - mode.trim_taps >= mode.min_taps:
        taps = taps[mode.trim_taps:]

    stats = _interval_stats(mode, taps)
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
    compat = _interval_stats(mode, compat_taps)
    if compat:
        out["frequency_hz_w10"] = compat["frequency_hz"]
        out["cv_pct_w10"] = compat["cv_pct"]

    # Speed decrement: slope of instantaneous rate at interval midpoints,
    # as % of mean rate per second (negative = slowing over the trial).
    mids, rates = [], []
    for i in range(len(taps) - 1):
        iti_i = (taps[i + 1] - taps[i]) * 1000
        if iti_i <= cutoff:
            mids.append((taps[i] + taps[i + 1]) / 2 - t_start)
            rates.append(1000.0 / iti_i)
    sl = _slope(mids, rates)
    if sl is not None and rates:
        mean_rate = sum(rates) / len(rates)
        if mean_rate > 0:
            out["decrement_pct_per_s"] = sl / mean_rate * 100.0

    # Amplitude per tap: max-min of the distance signal between taps.
    amps = []
    for i in range(len(taps) - 1):
        seg = [d for (t, d) in series if taps[i] <= t < taps[i + 1]]
        if len(seg) >= 2:
            amps.append(max(seg) - min(seg))
    if len(amps) >= 2:
        out["amplitude_mean"] = sum(amps) / len(amps)
        a_sd = _sd(amps)
        if a_sd is not None and out["amplitude_mean"] > 0:
            out["amplitude_cv_pct"] = a_sd / out["amplitude_mean"] * 100.0

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
