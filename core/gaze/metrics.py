"""
Metrics: trial results → run endpoints (OCULOMOTOR_TEST_PLAN.md §3.3). Pure
functions, unit-testable (parallels core/tapping/metrics.py).

Headline: anti-saccade error rate % (best AD discriminator — Opwonya 2022,
SMD 1.59). Latency is quantised to ±1 frame at webcam rates and carries an
unknown fixed camera+display offset, so the robust latency readout is
Anti − Pro (the offset is common to both blocks and cancels); absolutes are
reported as secondary values.
"""

from __future__ import annotations

import math

from .detector import TrialResult

# Anti-saccade error-rate bands (§6): healthy webcam median ≈ 5.8%
# (lab healthy 2–25%); AD mean ≈ 25.4% (Crawford 2005).
ERROR_TYPICAL_PCT = 20.0
ERROR_MONITOR_PCT = 40.0
THRESHOLDS_NOTE = ("Bands anchored to published healthy (~6%) and AD (~25%) "
                   "anti-saccade error rates; short screening form, not a norm.")

MIN_VALID_PRO = 8            # of 16 scored prosaccade trials
MIN_VALID_ANTI = 12          # of 24 scored anti-saccade trials
MIN_FACE_RATIO = 0.8
# Frames whose iris was readable, as a fraction of frames with a face. Low
# here with a high face ratio means the lids, not the framing, cost the run.
MIN_GAZE_RATIO = 0.7


def _sd(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))


def band(error_rate_pct: float) -> tuple[str, str]:
    """(status_token, plain-language label) — shown with icon + word, never
    color alone (style guide §2.4)."""
    if error_rate_pct < ERROR_TYPICAL_PCT:
        return "success", "Within typical range"
    if error_rate_pct < ERROR_MONITOR_PCT:
        return "warning", "Mildly elevated - consider monitoring"
    return "danger", "Elevated - recommend follow-up"


def block_stats(trials: list[TrialResult]) -> dict:
    """Per-block counts + latency stats. Latencies use correct trials only."""
    valid = [t for t in trials if t.valid]
    errors = [t for t in valid if t.is_error]
    corrected = [t for t in errors if t.corrected]
    lats = [t.latency_ms for t in valid if t.outcome == "correct"]
    mean_lat = sum(lats) / len(lats) if lats else None
    lat_sd = _sd(lats)
    return {
        "trials": len(trials),
        "valid": len(valid),
        "errors": len(errors),
        "errors_corrected": len(corrected),
        "anticipatory": sum(1 for t in trials if t.outcome == "anticipatory"),
        "no_response": sum(1 for t in trials if t.outcome == "no_response"),
        "face_lost": sum(1 for t in trials if t.outcome == "face_lost"),
        "error_rate_pct": (len(errors) / len(valid) * 100) if valid else None,
        "corrected_rate_pct": (len(corrected) / len(valid) * 100) if valid else None,
        "mean_latency_ms": mean_lat,
        "latency_cv_pct": (lat_sd / mean_lat * 100)
                          if (lat_sd is not None and mean_lat) else None,
    }


def compute_metrics(pro_trials: list[TrialResult],
                    anti_trials: list[TrialResult],
                    face_visible_ratio: float = 1.0,
                    gaze_valid_ratio: float = 1.0) -> dict:
    """Score one run (pro block + anti block). Always returns a dict;
    `scoreable` is False with a specific human-readable `reason` when the
    headline can't be computed (mirrors the tapping test's honest handling)."""
    pro = block_stats(pro_trials)
    anti = block_stats(anti_trials)
    out: dict = {
        "scoreable": False,
        "reason": None,
        "error_rate_pct": anti["error_rate_pct"],
        "corrected_rate_pct": anti["corrected_rate_pct"],
        "antisaccade_latency_ms": anti["mean_latency_ms"],
        "prosaccade_latency_ms": pro["mean_latency_ms"],
        "anti_minus_pro_ms": None,
        "latency_cv_pct": anti["latency_cv_pct"],
        "anticipatory_count": pro["anticipatory"] + anti["anticipatory"],
        "valid_trials": pro["valid"] + anti["valid"],
        "valid_anti_trials": anti["valid"],
        "valid_pro_trials": pro["valid"],
        "face_visible_ratio": round(face_visible_ratio, 3),
        "gaze_valid_ratio": round(gaze_valid_ratio, 3),
        "pro_block": pro,
        "anti_block": anti,
        "status": None, "label": None,
    }

    if anti["valid"] < MIN_VALID_ANTI:
        if face_visible_ratio < MIN_FACE_RATIO:
            out["reason"] = ("Your face was out of view for part of the test - "
                             "sit facing the camera and try again.")
        elif gaze_valid_ratio < MIN_GAZE_RATIO:
            out["reason"] = (
                f"Your eyes could only be read on "
                f"{gaze_valid_ratio * 100:.0f}% of frames - add light, and "
                f"raise the camera to eye level so your eyelids don't cover "
                f"the iris.")
        elif anti["no_response"] > anti["valid"]:
            out["reason"] = ("Too few eye movements were detected - the dot "
                             "may be hard to see, or the room too dark.")
        else:
            out["reason"] = (f"Only {anti['valid']} valid anti-saccade trials - "
                             f"at least {MIN_VALID_ANTI} are needed for a "
                             f"reliable score.")
        return out

    if (pro["mean_latency_ms"] is not None
            and anti["mean_latency_ms"] is not None):
        out["anti_minus_pro_ms"] = (anti["mean_latency_ms"]
                                    - pro["mean_latency_ms"])
    if pro["valid"] < MIN_VALID_PRO:
        out["latency_note"] = ("Prosaccade baseline had too few valid trials - "
                               "latency comparison is unreliable.")

    out["status"], out["label"] = band(anti["error_rate_pct"])
    out["scoreable"] = True
    return out
