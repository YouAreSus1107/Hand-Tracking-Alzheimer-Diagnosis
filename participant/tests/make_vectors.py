"""
Dump golden vectors from the **normative** Python tapping engine
(WEB_PLATFORM_PLAN.md §3, "the parity discipline").

    python participant/tests/make_vectors.py

Writes participant/tests/vectors.json: synthetic distance signals plus the
detector and metric output Python produces for each. `parity.mjs` replays the
same inputs through the JS port and asserts agreement.

Regenerate this whenever the Python engine changes — Python lands first, then
the vectors, then the JS.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from types import SimpleNamespace

from core import framing
from core.hand_utils import make_landmark_filters, smooth_landmarks
from core.tapping.detector import Calibrator, TapDetector, thumb_index_distance
from core.tapping.metrics import compute_metrics
from core.tapping.modes import MODES

OUT = Path(__file__).resolve().parent / "vectors.json"
FPS = 30.0


def signal(rate_hz: float, seconds: float, jitter: float, seed: int,
           amp: float = 1.0, drift: float = 0.0) -> list[tuple[float, float]]:
    """A synthetic thumb-index distance trace: open ≈ 1.0, closed ≈ 0.15."""
    rng = random.Random(seed)
    samples = []
    phase = 0.0
    t = 0.0
    while t < seconds:
        step = rate_hz * (1.0 + drift * t) * (1.0 + rng.uniform(-jitter, jitter))
        phase += step / FPS
        d = 0.15 + amp * 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
        samples.append((round(t, 6), round(d, 6)))
        t += 1.0 / FPS
    return samples


def slip_signal(rate_hz: float, seconds: float, slip_at: int, reopen: float,
                seed: int) -> list[tuple[float, float]]:
    """A steady trace where the hand only half re-opens around one closure,
    so the detector's hysteresis never re-arms and one real tap goes
    uncounted -- the missed tap core/tapping/gaps.py forgives."""
    rng = random.Random(seed)
    period = 1.0 / rate_hz
    n = int(seconds * rate_hz)
    closures = [0.3 + k * period for k in range(n)]
    peaks = [1.0] * (n - 1)
    peaks[slip_at - 1] = reopen      # the one half re-opening before it
    knots = []
    for k, c in enumerate(closures):
        knots.append((c, 0.15))
        if k + 1 < n:
            knots.append(((c + closures[k + 1]) / 2, peaks[k]))
    samples, t, j = [], 0.0, 0
    while t < closures[-1]:
        while j + 1 < len(knots) and knots[j + 1][0] < t:
            j += 1
        if t < knots[0][0]:
            d = 1.0
        else:
            (t0, d0), (t1, d1) = knots[j], knots[j + 1]
            w = (t - t0) / (t1 - t0)
            d = d0 + (d1 - d0) * 0.5 * (1 - math.cos(math.pi * w))
        samples.append((round(t, 6), round(d + rng.uniform(-0.005, 0.005), 6)))
        t += 1.0 / FPS
    return samples


def landmark_case(seed: int) -> dict:
    """A 21-landmark frame, to pin thumb_index_distance()'s normalisation."""
    rng = random.Random(seed)
    pts = [[round(rng.uniform(0.1, 0.9), 6), round(rng.uniform(0.1, 0.9), 6),
            round(rng.uniform(-0.1, 0.1), 6)] for _ in range(21)]
    return {"landmarks": pts, "expect": thumb_index_distance(pts)}


def _hand(cx: float, cy: float, open_: float, rng: random.Random) -> list[list[float]]:
    """21 landmarks of a plausible hand centred on (cx, cy): wrist below,
    fingers above, thumb tip and index tip `open_` apart. Small noise."""
    pts = []
    for i in range(21):
        finger, joint = (i - 1) // 4, (i - 1) % 4
        if i == 0:
            x, y = cx, cy + 0.12
        else:
            x = cx + (finger - 2) * 0.035
            y = cy + 0.06 - (joint + 1) * 0.03
        pts.append([x + rng.gauss(0, 0.002), y + rng.gauss(0, 0.002),
                    rng.uniform(-0.05, 0.05)])
    pts[4][0], pts[4][1] = cx - open_ / 2, cy - 0.02
    pts[8][0], pts[8][1] = cx + open_ / 2, cy - 0.04
    return [[round(v, 6) for v in p] for p in pts]


def one_euro_case(seed: int) -> dict:
    """A tapping hand on an uneven frame clock (jittered intervals, one
    dropped frame), smoothed the way the desktop smooths it."""
    rng = random.Random(seed)
    fx, fy = make_landmark_filters()
    frames, t = [], 0.0
    for k in range(75):
        t = round(t + (1.0 / FPS) * (2.0 if k == 40 else 1.0 + rng.uniform(-0.2, 0.2)), 6)
        open_ = 0.02 + 0.10 * (0.5 - 0.5 * math.cos(2 * math.pi * 3.0 * t))
        raw = _hand(0.5, 0.5, open_, rng)
        sm = smooth_landmarks([SimpleNamespace(x=p[0], y=p[1], z=p[2]) for p in raw],
                              fx, fy, t)
        frames.append({"t": t, "raw": raw, "smoothed": [list(p) for p in sm],
                       "d": thumb_index_distance(sm)})
    return {"frames": frames}


def framing_case(seed: int) -> dict:
    """A hand drifting off the right edge, vanishing, and coming back."""
    rng = random.Random(seed)
    mon = framing.FramingMonitor()
    frames = []
    for k in range(90):
        t = round(k / FPS, 6)
        if 40 <= k < 48:
            pts = None
        else:
            cx = 0.5 + 0.45 * max(0.0, math.sin(math.pi * k / 40))
            pts = _hand(min(cx, 0.97), 0.5, 0.05, rng)
        level = mon.update(pts, t)
        frames.append({"t": t, "points": pts, "level": level,
                       "edges": list(mon.edges), "untrusted": mon.untrusted})
    return {"frames": frames, "blackouts": [list(b) for b in mon.finish()],
            "clipped_pct": mon.clipped_pct}


HINT_EDGES = [["bottom"], ["top"], ["left"], ["right", "bottom"], ["top", "left"], []]


def run_case(name: str, mode_key: str, samples: list[tuple[float, float]],
             *, blackouts=None, camera_fps=None, hand_visible_ratio=1.0,
             near_miss_from_detector: bool = False) -> dict:
    mode = MODES[mode_key]

    cal = Calibrator()
    for t, d in samples[:90]:
        cal.update(t, d)
    d_closed, d_open = cal.result()

    det = TapDetector(mode.min_intertap_s, 0.4, d_closed, d_open)
    taps_flagged = []
    for t, d in samples:
        if det.update(t, d):
            taps_flagged.append(round(t, 6))

    kwargs = {"blackouts": blackouts, "camera_fps": camera_fps,
              "hand_visible_ratio": hand_visible_ratio,
              "near_miss": det.near_miss if near_miss_from_detector else 0}
    metrics = compute_metrics(mode, det.tap_times, det.series,
                              samples[0][0], samples[-1][0], **kwargs)
    return {
        "name": name,
        "mode": mode_key,
        "kwargs": kwargs,
        "samples": samples,
        "calibration": {
            "d_closed": d_closed, "d_open": d_open,
            "cycles": cal.cycles, "done": cal.done,
            "progress": cal.progress, "range_seen": cal.range_seen,
        },
        "detector": {
            "close_at": det.close_at, "open_at": det.open_at,
            "tap_times": taps_flagged, "smoothed": det.smoothed,
        },
        "metrics": metrics,
    }


def main() -> None:
    cases = [
        run_case("steady_5hz", "big_and_fast", signal(5.0, 10.0, 0.02, 1)),
        run_case("variable_4hz", "big_and_fast", signal(4.0, 10.0, 0.25, 2)),
        run_case("slowing", "big_and_fast", signal(5.0, 10.0, 0.05, 3, drift=-0.04)),
        run_case("too_few_taps", "big_and_fast", signal(0.6, 6.0, 0.02, 4)),
        run_case("small_amplitude", "big_and_fast", signal(5.0, 10.0, 0.08, 5, amp=0.55)),
        # 0.4 Hz: enough taps to be scored, too slow to have a rhythm. Guards
        # the min_effort_hz gate on both sides of the port.
        run_case("below_rhythm_floor", "big_and_fast", signal(0.4, 25.0, 0.02, 6)),
        # One half re-opening the detector cannot see past: guards the
        # missed-tap forgiveness (core/tapping/gaps.py) on both sides.
        run_case("one_missed_tap", "big_and_fast", slip_signal(2.0, 16.0, 16, 0.4, 7)),
        # The framing pause (core/framing.py): frames inside the blackout never
        # reach the detector, and the interval spanning it is dropped.
        run_case("paused_mid_run", "big_and_fast",
                 [s for s in signal(3.0, 20.0, 0.3, 8) if not 8.0 <= s[0] < 9.5],
                 blackouts=[[7.85, 9.9]], camera_fps=30.0,
                 hand_visible_ratio=0.93, near_miss_from_detector=True),
        run_case("two_pauses", "big_and_fast",
                 [s for s in signal(2.5, 20.0, 0.3, 9)
                  if not (4.0 <= s[0] < 4.6 or 13.0 <= s[0] < 14.2)],
                 blackouts=[[3.85, 5.0], [12.85, 14.6]], camera_fps=24.0,
                 hand_visible_ratio=0.88, near_miss_from_detector=True),
        # [] must score exactly as None does (core/framing.py docstring).
        run_case("empty_blackouts", "big_and_fast", signal(5.0, 10.0, 0.02, 1),
                 blackouts=[]),
        # A slow phone: the timing and tracking confidence factors, which the
        # cases above leave at 1.0.
        run_case("slow_phone", "big_and_fast", signal(2.0, 20.0, 0.3, 10),
                 camera_fps=15.0, hand_visible_ratio=0.78),
    ]
    payload = {
        "note": "Generated by participant/tests/make_vectors.py — do not hand-edit.",
        "fps": FPS,
        "modes": {k: {"key": m.key, "paced": m.paced, "duration_s": m.duration_s,
                      "expected_rate_hz": m.expected_rate_hz, "min_taps": m.min_taps,
                      "trim_taps": m.trim_taps, "cv_typical": m.cv_typical,
                      "cv_monitor": m.cv_monitor,
                      "max_rate_hz": m.max_rate_hz,
                      "min_effort_hz": m.min_effort_hz,
                      "min_intertap_s": m.min_intertap_s, "max_iti_ms": m.max_iti_ms}
                  for k, m in MODES.items()},
        "landmark_cases": [landmark_case(s) for s in (11, 12, 13)],
        "cases": cases,
        "one_euro_cases": [one_euro_case(21)],
        "framing_cases": [framing_case(31)],
        "framing_consts": {"EDGE_CLIP": framing.EDGE_CLIP, "EDGE_NEAR": framing.EDGE_NEAR,
                           "CLEAR_HOLD_S": framing.CLEAR_HOLD_S,
                           "PRE_ROLL_S": framing.PRE_ROLL_S},
        "hint_cases": [{"edges": e, "tracing": tr, "expect": framing.hint(tuple(e), tr)}
                       for e in HINT_EDGES for tr in (False, True)],
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(_REPO_ROOT)}  ({OUT.stat().st_size // 1024} KB)")
    for case in cases:
        m = case["metrics"]
        print(f"  {case['name']:<16} taps={m['taps']:<3} "
              f"cv={m['cv_pct'] and round(m['cv_pct'], 3)} scoreable={m['scoreable']}")


if __name__ == "__main__":
    main()
