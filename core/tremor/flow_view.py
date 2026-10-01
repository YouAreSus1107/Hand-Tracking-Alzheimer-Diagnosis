"""
Live view of what the tremor test actually measures: the optical flow.

The test's reading comes from optical flow on the skin (core/tremor/flow.py,
scored offline over every frame), not from MediaPipe's landmarks. Drawing the
landmark skeleton live showed people the one thing the test does NOT trust:
on a hand resting flat, MediaPipe re-guesses the fingers every frame (1-2 %
of the hand length a frame, 2026-09-30), and a skeleton that twitches on a
still hand reads as "it thinks I'm shaking" (TREMOR_TEST_PLAN.md §3c).

So the live overlay shows, per hand:
  outline  the hand's shape from the 0.3 s smoothed landmarks
           (flow.LandmarkSmoother + flow.hand_shape_mask): it sits still when
           the hand does, whatever the per-frame guesses do
  points   the skin points the flow is following, as small dots
  trace    a small seismograph of the flow's motion in the tremor band,
           on a FIXED scale (TRACE_RANGE_PCT): a still hand draws a flat
           line, a trembling one a wave

Display only. The score is still computed offline from the recorded frames;
nothing here reaches a saved session. MediaPipe keeps running live to find
the hands and check they are in frame.
"""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np

from core.tremor.flow import HandFlow, LandmarkSmoother, hand_shape_mask

TRACE_S = 3.0              # seconds of trace shown
HP_S = 0.25                # moving-average window removed: slow drift < ~4 Hz
#: Full height of the trace = +/- this share of the hand length. Fixed, never
#: auto-scaled: an auto-scaled trace blows a still hand's 0.02 % noise up to
#: full height. The flow's "detected" floor is 0.60 % RMS (~0.85 % peak), and
#: a small real tremor (0.1-0.2 % RMS) fills a third to a half of it.
TRACE_RANGE_PCT = 0.5
LOST_RESET_S = 0.5         # a hand gone this long starts afresh
TRACE_W, TRACE_H = 150, 44


class _Hand:
    def __init__(self):
        self.smooth = LandmarkSmoother()
        self.flow = HandFlow()
        self.pos: deque = deque()          # (t, x px, y px) from the flow
        self.geo = None                    # smoothed 21 points, px
        self.length = None                 # smoothed hand length, px
        self.seen = None


class LiveFlowView:
    """Call ``update(gray, t, hands_px)`` on every live frame with each
    hand's raw landmark pixels (or None), then ``draw(canvas, t)``."""

    def __init__(self, hands=("left", "right")):
        self.hands = {h: _Hand() for h in hands}

    def reset(self):
        for h in self.hands:
            self.hands[h] = _Hand()

    def update(self, gray, t: float, hands_px: dict) -> None:
        for name, st in self.hands.items():
            px = hands_px.get(name)
            if px is None and st.seen is not None and t - st.seen > LOST_RESET_S:
                self.hands[name] = st = _Hand()
            geo = st.smooth.update(t, px)
            if px is not None:
                st.seen = t
                if geo is not None:
                    st.geo = geo
                    st.length = float(np.hypot(*(geo[9] - geo[0]))) or None
            seeds = st.geo.tolist() if (px is not None and st.geo is not None) else None
            s = st.flow.update(gray, t, seeds)
            if s is not None:
                st.pos.append(s)
            while st.pos and t - st.pos[0][0] > TRACE_S + HP_S:
                st.pos.popleft()

    def trace(self, name: str, now: float) -> list[tuple[float, float]]:
        """The hand's recent motion, drift removed, in % of hand length, on
        the axis it moves most along (sign kept)."""
        st = self.hands.get(name)
        if st is None or st.length is None or len(st.pos) < 8:
            return []
        a = np.asarray(st.pos, float)
        t, xy = a[:, 0], a[:, 1:3]
        # remove the slow part: each sample minus the mean of the HP_S around it
        span = max(1, int(round(HP_S * (len(t) - 1) / max(1e-6, t[-1] - t[0]))))
        k = np.ones(span) / span
        slow = np.column_stack([np.convolve(xy[:, i], k, mode="same") for i in range(2)])
        hp = (xy - slow) / st.length * 100.0
        keep = t >= now - TRACE_S
        if keep.sum() < 4:
            return []
        hp, t = hp[keep], t[keep]
        axis = hp[:, 0] if hp[:, 0].var() >= hp[:, 1].var() else hp[:, 1]
        return list(zip(t.tolist(), axis.tolist()))

    def draw(self, c, now: float, show_trace: bool = True) -> None:
        fh, fw = c.h, c.w
        for name, st in self.hands.items():
            if st.geo is None or st.seen is None or now - st.seen > LOST_RESET_S:
                continue
            mask = hand_shape_mask((fh, fw), st.geo)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                pts = cnt.reshape(-1, 2).tolist()
                if len(pts) > 2:
                    c.polyline(pts, "brand", thickness=1, alpha=0.55, closed=True)
            for x, y in st.flow.pts.reshape(-1, 2):
                c.dot(int(x), int(y), 2, "info", alpha=0.9)
            if not show_trace:
                continue
            series = self.trace(name, now)
            if not series:
                continue
            cx = int(np.clip(st.geo[:, 0].mean() - TRACE_W / 2, 8, fw - TRACE_W - 8))
            # below the hand when there is room above the bottom bar (progress
            # and prompts), else above it: never over the hand itself
            below = st.geo[:, 1].max() + 16
            cy = below if below + TRACE_H <= fh - 72 else st.geo[:, 1].min() - 16 - TRACE_H
            cy = int(np.clip(cy, 56, fh - TRACE_H - 72))
            c.sparkline(cx, cy, TRACE_W, TRACE_H, series, [], now,
                        window_s=TRACE_S, lo=-TRACE_RANGE_PCT, hi=TRACE_RANGE_PCT)
