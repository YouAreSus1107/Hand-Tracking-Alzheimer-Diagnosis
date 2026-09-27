"""
On-screen side of core/framing.py, shared by the spiral and finger-tapping
tests: the status-bar chip and the edge warning (UI_STYLE_GUIDE.md §2.4, §5).
"""

from __future__ import annotations

from core import framing, i18n
from core.ui.coach import PRI_EDGE


def framing_chips(mon, landmarks, fps):
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


def draw_framing(c, mon, raw_pts, coach, tracing=False):
    """Edge band (+ inward chevron once clipped) and, once clipped, a prompt
    through the shared Coach channel. A hand merely near the edge gets the
    thin band only -- a warning before the data is lost, without nagging.
    One colour throughout: how bad it is shows in the band's weight and the
    chevron, never a second hue."""
    if mon.level not in (framing.CLIPPED, framing.NEAR) or not raw_pts:
        return
    along = (sum(p[0] for p in raw_pts) / len(raw_pts),
             sum(p[1] for p in raw_pts) / len(raw_pts))
    clipped = mon.level == framing.CLIPPED
    c.edge_alert(mon.edges, "warning", along, strong=clipped)
    if clipped:
        coach.say(i18n.t(framing.hint(mon.edges, tracing)), PRI_EDGE)
