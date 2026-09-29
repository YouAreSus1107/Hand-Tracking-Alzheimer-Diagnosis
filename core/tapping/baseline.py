"""
Baseline: this person's tapping against their own usual. Pure, stdlib only.

CV% measures rhythm, and a slow but even tapper has an even rhythm: on
HUBU-FIS, 6 of the 15 UPDRS-2 hands graded Typical tapped at 0.6-0.86 Hz
against a healthy median of 1.67. A fixed speed threshold cannot catch them at
home, because at home "as fast as you can" means different things to different
people (27% of one healthy person's runs were under 1 Hz). What is comparable
is the same person, same hand, same mode, over time.

The numbers below come from replaying this rule over that person's history in
time order (2026-09, read-only): single runs swing +/-26% in rate, day medians
+/-8%, so the rule looks at the median of the last RATE_WINDOW runs and only
fires on a large drop. Result: 0 of 26 healthy checks flagged, 13 of 26
simulated 50% slowdowns caught. Opening size is steadier per person but
depends on the camera, and the same replay gave 18% false flags, so it is
reported, never scored. The thresholds rest on one person's ~40 good runs and
are deliberately conservative -- revisit them as history grows.

The verdict change this feeds is one-way (finger_tapping.py): a Typical run
that is also far slower than usual becomes Monitor. Nothing is ever lowered.
"""

from __future__ import annotations

MIN_RUNS = 10          # good runs needed before any comparison
MIN_DAYS = 3           # ...spread over at least this many days
BASE_RUNS = 30         # the baseline is the median of the latest this many
MIN_CONFIDENCE = 45.0  # runs below this are not genuine attempts to learn from
RATE_WINDOW = 5        # this run plus the previous 4
RATE_FLOOR = 0.55      # "slower than usual" below this share of the baseline
OPEN_WINDOW = 3        # opening size: this run plus the previous 2

# The label a Typical run gets when it is also far slower than usual.
SLOWER_LABEL = "Slower than your usual - consider monitoring"


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None          # NaN guard


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def eligible(rows: list[dict], profile_id: str | None, hand: str | None,
             mode: str) -> list[dict]:
    """Earlier good runs of this person's same hand and mode, oldest first.

    `rows` are index.csv rows (core/session.load_index), so every value may be
    a string. No profile means no baseline: runs nobody claimed may be anyone's.
    """
    if not profile_id:
        return []
    out = []
    for r in rows:
        if (r.get("profile_id") != profile_id or r.get("hand") != hand
                or r.get("mode") != mode or str(r.get("scoreable")) != "True"):
            continue
        rate, conf = _num(r.get("frequency_hz")), _num(r.get("confidence_pct"))
        if rate is None or conf is None or conf < MIN_CONFIDENCE:
            continue
        out.append({"ts": r.get("timestamp") or "", "day": (r.get("timestamp") or "")[:10],
                    "rate": rate, "opening": _num(r.get("amplitude_mean")),
                    "camera": r.get("camera_name") or ""})
    return sorted(out, key=lambda x: x["ts"])


def compare(prior: list[dict], rate_hz: float | None, confidence: float | None,
            opening: float | None = None, camera: str | None = None) -> dict:
    """Compare this run with the person's usual.

    `prior` comes from eligible(). The most recent RATE_WINDOW-1 of them join
    this run in the "recent" median and are left out of the baseline, so a
    slowdown already under way cannot drag its own reference down with it.
    """
    out = {"baseline_runs": len(prior), "baseline_rate_hz": None,
           "rate_vs_usual": None, "slower_than_usual": 0,
           "opening_vs_usual": None}
    if rate_hz is None or confidence is None or confidence < MIN_CONFIDENCE:
        return out
    recent_prior = prior[-(RATE_WINDOW - 1):] if RATE_WINDOW > 1 else []
    pool = prior[:len(prior) - len(recent_prior)]
    if len(pool) < MIN_RUNS or len({p["day"] for p in pool}) < MIN_DAYS:
        return out
    base = _median([p["rate"] for p in pool[-BASE_RUNS:]])
    if base <= 0:
        return out
    ratio = _median([p["rate"] for p in recent_prior] + [rate_hz]) / base
    out.update(baseline_rate_hz=base, rate_vs_usual=ratio,
               slower_than_usual=int(ratio < RATE_FLOOR))

    if opening and camera:
        same = [p for p in prior if p["camera"] == camera and p["opening"]]
        recent_o = same[-(OPEN_WINDOW - 1):] if OPEN_WINDOW > 1 else []
        pool_o = same[:len(same) - len(recent_o)]
        if len(pool_o) >= MIN_RUNS:
            base_o = _median([p["opening"] for p in pool_o[-BASE_RUNS:]])
            if base_o > 0:
                out["opening_vs_usual"] = _median(
                    [p["opening"] for p in recent_o] + [opening]) / base_o
    return out
