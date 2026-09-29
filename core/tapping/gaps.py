"""
Gaps: what happened in the long intervals between taps. Pure, stdlib only.

A long interval has three possible causes, and only one is our fault:

  missed_tap       the fingers closed fully, but the hand only half re-opened
                   before, so the detector's hysteresis never re-armed and one
                   real tap went uncounted. The interval comes out ~2x its
                   neighbours with a full closure near its middle. The detector's
                   near-miss counter does not see this (the dip never crossed the
                   open threshold first), so it is found here, in the trace.
  partial_closure  a closure started near the middle but never reached the
                   usual closed floor: a hesitation or an incomplete tap.
  pause            no closure at all: the hand stopped.

Only a missed_tap is ever forgiven, and only when it is the single long
interval in an otherwise steady run (`restore_missed_tap`). Pauses and partial
closures are Parkinsonian signs and always count -- a gate that treated such
signs as bad data hid 10 of 26 severe patients on HUBU-FIS (see CLAUDE.md).

Evidence for the rule (2026-09, read-only prototypes; both datasets are now
development data, so these are not confirmatory numbers):
  * one missed tap -- an interval of ~2.0x the median -- adds 14-20 CV points
    and was behind 2 of the 6 unimpaired HUBU-FIS hands graded above Typical;
  * restoring every ~2x interval also restored taps in patients (68 taps in
    37 videos) and cost sensitivity 73% -> 69%; requiring a single long
    interval and a full closure kept it at 73% while cutting healthy
    EHWGesture false alarms 35 -> 22.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from core.framing import overlaps

LONG = 1.5                  # an interval this much longer than its neighbours
MISSED_LO, MISSED_HI = 1.7, 2.3   # a missed tap doubles one interval
MID_LO, MID_HI = 0.25, 0.75       # the lost closure sits near the middle
MIN_DIP = 0.25              # dip prominence vs the run's median cycle excursion
FULL_CLOSE = 0.25           # a full closure reaches within this share of an
                            # excursion of the run's usual closed floor
NEIGHBOURS = 3              # intervals each side for the local median


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _local_median(iti: list[float], k: int) -> float:
    nb = iti[max(0, k - NEIGHBOURS):k] + iti[k + 1:k + 1 + NEIGHBOURS]
    return _median(nb) if nb else _median(iti)


class _Trace:
    """The distance series with the run-level figures every gap is judged by."""

    def __init__(self, series: list[tuple[float, float]], taps: list[float]):
        self.ts = [t for t, _ in series]
        self.ds = [d for _, d in series]
        floors, amps, lags = [], [], []
        for a, b in zip(taps, taps[1:]):
            i0, i1 = self.span(a, b)
            if i1 - i0 < 3:
                continue
            seg = self.ds[i0:i1]
            amps.append(max(seg) - min(seg))
            # the closure belonging to the tap at `a` sits in the first half
            half = i0 + max(1, (i1 - i0) // 2)
            m = min(range(i0, half), key=lambda q: self.ds[q])
            floors.append(self.ds[m])
            lags.append(self.ts[m] - a)
        self.ok = len(amps) >= 3
        if self.ok:
            self.amp = _median(amps)
            self.floor = _median(floors)
            # a restored tap is placed this far before its closure minimum, so
            # it sits on the same footing as the taps the detector timed
            self.lag = _median(lags)

    def span(self, a: float, b: float) -> tuple[int, int]:
        return bisect_left(self.ts, a), bisect_right(self.ts, b)

    def mid_dip(self, a: float, b: float) -> int | None:
        """Index of the deepest prominent dip in the middle of (a, b)."""
        i0, i1 = self.span(a, b)
        if i1 - i0 < 5:
            return None
        best = None
        for q in range(i0 + 1, i1 - 1):
            frac = (self.ts[q] - a) / (b - a)
            if not MID_LO <= frac <= MID_HI:
                continue
            if self.ds[q] <= self.ds[q - 1] and self.ds[q] < self.ds[q + 1]:
                prom = min(max(self.ds[i0:q + 1]), max(self.ds[q:i1])) - self.ds[q]
                if prom >= MIN_DIP * self.amp and (best is None or self.ds[q] < self.ds[best]):
                    best = q
        return best


def _scored_pairs(taps: list[float], blackouts=None) -> list[tuple[float, float]]:
    return [(a, b) for a, b in zip(taps, taps[1:]) if not overlaps(a, b, blackouts)]


def label_gaps(taps: list[float], series: list[tuple[float, float]],
               blackouts=None) -> list[tuple[float, float, str]]:
    """(start, end, kind) for every interval over LONG x its neighbours."""
    pairs = _scored_pairs(taps, blackouts)
    if len(pairs) < 4 or not series:
        return []
    tr = _Trace(series, taps)
    if not tr.ok:
        return []
    iti = [b - a for a, b in pairs]
    out = []
    for k, (a, b) in enumerate(pairs):
        ratio = iti[k] / _local_median(iti, k)
        if ratio <= LONG:
            continue
        q = tr.mid_dip(a, b)
        if q is None:
            kind = "pause"
        elif tr.ds[q] > tr.floor + FULL_CLOSE * tr.amp:
            kind = "partial_closure"
        elif MISSED_LO <= ratio <= MISSED_HI:
            kind = "missed_tap"
        else:
            kind = "pause"        # a full closure, but not on the beat of one lost tap
        out.append((a, b, kind))
    return out


def count_interruptions(labels: list[tuple[float, float, str]]) -> int:
    return sum(kind != "missed_tap" for _, _, kind in labels)


def restore_missed_tap(taps: list[float], series: list[tuple[float, float]],
                       blackouts=None) -> float | None:
    """The time of the one tap to restore, or None.

    Only when the run has exactly one long interval and it is a missed_tap:
    a single slip in an otherwise steady run. `taps` are the scored taps
    (after the ramp-up trim), so the check covers the intervals that count."""
    labels = label_gaps(taps, series, blackouts)
    if len(labels) != 1 or labels[0][2] != "missed_tap":
        return None
    a, b, _ = labels[0]
    tr = _Trace(series, taps)
    q = tr.mid_dip(a, b)
    t = tr.ts[q] - tr.lag
    return t if a < t < b else None
