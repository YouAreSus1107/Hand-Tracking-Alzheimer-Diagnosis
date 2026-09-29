"""
On-screen side of core/framing.py, shared by the spiral, finger-tapping and
tremor tests: the status-bar chip and the edge warning (UI_STYLE_GUIDE.md
§2.4, §5).
"""

from __future__ import annotations

from core import framing, i18n
from core.framing import FramingMonitor
from core.ui.coach import Coach, PRI_EDGE
from core.ui.components import Canvas


def framing_chips(mon: FramingMonitor, landmarks, fps: float):
    """Status-bar chips: hand presence, including 'at the edge'."""
    if landmarks is None:
        chips = [(i18n.t("Show your hand"), "warning")]
    elif mon.level == framing.CLIPPED:
        chips = [(i18n.t("Hand at the edge"), "warning")]
    elif mon.level == framing.NEAR:
        chips = [(i18n.t("Near the edge"), "warning")]
    else:
        chips = [(i18n.t("Hand detected"), "success")]
    if fps < 24:
        chips.append((f"{fps:.0f} fps", "warning"))
    return chips


def draw_framing(c: Canvas, mon: FramingMonitor, raw_pts, coach: Coach, *,
                 tracing: bool = False):
    """Edge band (+ inward chevron once clipped) and, once clipped, a prompt
    through the shared Coach channel. A hand merely near the edge gets the
    thin band only -- a warning before the data is lost, without nagging.
    One colour throughout: how bad it is shows in the band's weight and the
    chevron, never a second hue.

    The coach is checked on every call, not just when a hand is clipped: a
    wrong object here used to crash the tremor test only once a hand reached
    the edge, which in a live run is the first moment nobody is watching the
    console. `tracing` is keyword-only for the same reason -- a stray
    positional argument (the tremor test passed `now`) must fail loudly
    instead of silently switching the hint text."""
    if not isinstance(coach, Coach):
        raise TypeError(f"draw_framing needs a core.ui.coach.Coach, "
                        f"got {type(coach).__name__}")
    if mon.level not in (framing.CLIPPED, framing.NEAR) or not raw_pts:
        return
    along = (sum(p[0] for p in raw_pts) / len(raw_pts),
             sum(p[1] for p in raw_pts) / len(raw_pts))
    clipped = mon.level == framing.CLIPPED
    c.edge_alert(mon.edges, "warning", along, strong=clipped)
    if clipped:
        coach.say(i18n.t(framing.hint(mon.edges, tracing)), PRI_EDGE)
