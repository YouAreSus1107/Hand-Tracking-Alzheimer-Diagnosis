"""
One prompt channel for the live tests (UI_STYLE_GUIDE.md §5, §7).

Every corrective prompt -- hand out of view, hand at the edge, off the line,
too close, pace -- used to be its own toast call, and whichever ran last in a
frame won: prompts flickered over each other and landed on top of the bottom
panels. Now screens *ask* for a prompt each frame and the Coach decides:

  * one prompt at a time, always in the same place (PROMPT_Y above the
    bottom edge, a slot the screens keep clear) and the same style;
  * the most important request wins (PRI_*, highest first);
  * a prompt stays up at least MIN_SHOW_S before a different one may replace
    it, so none is overwritten before it can be read;
  * once nothing asks for it, it lingers LINGER_S and fades.

House style for prompt text: a short command in sentence case, no dash
clauses, no trailing punctuation ("Move your hand back from the screen").
"""

from __future__ import annotations

from core.ui import theme
from core.ui.anim import ease_out_cubic
from core.ui.components import Canvas

# Priorities, highest first.
PRI_HAND = 50      # no hand at all
PRI_EDGE = 40      # hand part-way out of the picture
PRI_LINE = 30      # fingertip off the arm it is tracing
PRI_SETUP = 20     # before/around the start: distance, calibration trouble
PRI_PACE = 10      # practice pace and smoothness

MIN_SHOW_S = 1.0
LINGER_S = 0.6
PROMPT_Y = 96      # pill top, measured up from the bottom edge
STATUS = "warning"  # one colour for every prompt


class Coach:
    def __init__(self):
        self.msg: str | None = None
        self.shown_at = -1e9       # when the current prompt appeared
        self.asked_at = -1e9       # last frame something asked for it
        self._asks: list[tuple[int, str]] = []

    def say(self, msg: str, priority: int) -> None:
        """Request a prompt for this frame (already translated)."""
        if msg:
            self._asks.append((priority, msg))

    def clear(self) -> None:
        self.msg = None
        self._asks.clear()

    def _pick(self, now: float) -> None:
        asks, self._asks = self._asks, []
        if not asks:
            return
        top = max(asks, key=lambda a: a[0])[1]
        if top == self.msg:
            self.asked_at = now
        elif (self.msg is None or now - self.shown_at >= MIN_SHOW_S
              or now - self.asked_at > LINGER_S):
            self.msg, self.shown_at, self.asked_at = top, now, now
        elif any(m == self.msg for _, m in asks):
            self.asked_at = now      # still wanted; hold it until MIN_SHOW_S

    def render(self, canvas: Canvas, now: float) -> None:
        self._pick(now)
        if self.msg is None:
            return
        fade = theme.DUR_BASE
        gone = now - self.asked_at - LINGER_S
        if gone >= fade:
            self.msg = None
            return
        a_in = 1.0 if theme.REDUCED_MOTION else ease_out_cubic(
            min(1.0, (now - self.shown_at) / fade))
        a_out = 1.0 if gone <= 0 else 1.0 - gone / fade
        canvas.toast(self.msg, STATUS, max(0.0, min(a_in, a_out)),
                     y=canvas.h - PROMPT_Y)
