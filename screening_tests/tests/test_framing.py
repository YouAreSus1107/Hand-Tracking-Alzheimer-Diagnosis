"""
Unit tests for core/framing.py -- is the whole hand inside the picture?
Pure, no camera.

Run:  python screening_tests/tests/test_framing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core import framing as fr


def hand(cx=0.5, cy=0.5, size=0.2):
    """21 points spread over a square hand-sized box around (cx, cy)."""
    pts = []
    for i in range(21):
        u, v = (i % 5) / 4 - 0.5, (i // 5) / 4 - 0.5
        pts.append((cx + u * size, cy + v * size))
    return pts


def test_centred_hand_is_ok():
    assert fr.edge_state(hand()) == (fr.OK, ())


def test_no_hand_is_lost():
    assert fr.edge_state(None)[0] == fr.LOST
    assert fr.edge_state([])[0] == fr.LOST


def test_near_and_clipped_name_the_edge():
    level, edges = fr.edge_state(hand(cy=0.86, size=0.2))   # bottom at 0.96
    assert level == fr.NEAR and edges == ("bottom",)
    level, edges = fr.edge_state(hand(cx=0.05, size=0.2))   # left past 0
    assert level == fr.CLIPPED and edges == ("left",)


def test_off_image_landmarks_count_as_clipped():
    pts = hand()
    pts[0] = (0.5, 1.08)          # MediaPipe places a hidden wrist past the edge
    assert fr.edge_state(pts) == (fr.CLIPPED, ("bottom",))


def test_corner_reports_both_edges():
    _, edges = fr.edge_state(hand(cx=0.95, cy=0.05, size=0.2))
    assert set(edges) == {"right", "top"}


def test_monitor_enters_at_once_and_clears_after_hold():
    m = fr.FramingMonitor()
    m.update(hand(), 0.0)
    assert not m.untrusted
    m.update(hand(cx=0.03), 1.0)                 # clipped
    assert m.untrusted
    m.update(hand(), 1.1)                        # back, but not settled
    assert m.untrusted
    m.update(hand(), 1.1 + fr.CLEAR_HOLD_S / 2)
    assert m.untrusted
    settled = 1.1 + fr.CLEAR_HOLD_S + 0.01
    m.update(hand(), settled)
    assert not m.untrusted
    assert m.blackouts == [(1.0 - fr.PRE_ROLL_S, settled)]


def test_bounce_back_out_restarts_the_hold():
    m = fr.FramingMonitor()
    m.update(None, 0.0)                          # lost counts as untrusted
    m.update(hand(), 0.1)
    m.update(hand(cx=0.02), 0.3)                 # out again before settling
    m.update(hand(), 0.4)
    m.update(hand(), 0.4 + fr.CLEAR_HOLD_S - 0.01)
    assert m.untrusted
    m.update(hand(), 0.4 + fr.CLEAR_HOLD_S + 0.01)
    assert not m.untrusted and len(m.blackouts) == 1


def test_near_edge_does_not_distrust_the_data():
    m = fr.FramingMonitor()
    m.update(hand(cy=0.86), 0.0)
    assert m.level == fr.NEAR and not m.untrusted


def test_finish_closes_an_open_blackout_and_counts():
    m = fr.FramingMonitor()
    m.update(hand(), 0.0)
    m.update(hand(cx=0.03), 0.5)
    m.update(hand(cx=0.03), 0.6)
    assert m.finish() == [(0.5 - fr.PRE_ROLL_S, 0.6)]
    assert m.clipped_frames == 2 and round(m.clipped_pct) == 67


def test_overlaps():
    bo = [(1.0, 2.0)]
    assert fr.overlaps(0.5, 1.0, bo)
    assert fr.overlaps(1.5, 3.0, bo)
    assert not fr.overlaps(2.1, 3.0, bo)
    assert not fr.overlaps(0.0, 1.0, None)


def test_hint_avoids_left_and_right():
    """The picture is mirrored; 'left' would make an older patient work out
    whose left. Sideways edges get 'toward the middle'."""
    for edges in (("left",), ("right",), ("left", "bottom")):
        msg = fr.hint(edges)
        assert "left" not in msg and "right" not in msg
    assert fr.hint(("bottom",)) == "Raise your hand a little"
    # on the spiral, lifting the hand would lift the fingertip off the line
    assert fr.hint(("bottom",), tracing=True) == fr.MOVE_BACK


def test_prompts_share_one_syntax():
    """Short commands, no dash clauses, no trailing punctuation."""
    from core.spiral import practice as pr
    prompts = [fr.hint(e, tr) for e in (("left",), ("top",), ("bottom",))
               for tr in (False, True)] + [
        fr.MOVE_BACK, pr.MSG_OFF_LINE, pr.MSG_SLOWER, pr.MSG_FASTER,
        pr.MSG_SMOOTHER]
    for m in prompts:
        assert " - " not in m and not m.endswith((".", "!")), m
        assert m[0].isupper() and len(m) <= 40, m


def test_hang_measures_reach_below_the_fingertip():
    pts = hand()
    pts[8] = (0.5, 0.40)
    assert abs(fr.hang(pts) - (max(p[1] for p in pts) - 0.40)) < 1e-9
    assert fr.hang(None) is None


# ── Coach: the one prompt channel (core/ui/coach.py) ───────────────────────

class _Canvas:
    h = 480

    def __init__(self):
        self.drawn = []

    def toast(self, msg, status, alpha, y=None, compact=False):
        if alpha > 0.01:
            self.drawn.append((msg, status, y))


def _frame(coach, t, *asks):
    for pri, msg in asks:
        coach.say(msg, pri)
    c = _Canvas()
    coach.render(c, t)
    return c.drawn


def test_coach_highest_priority_wins_in_one_place_and_colour():
    from core.ui import coach as co
    k = co.Coach()
    _frame(k, 0.0, (co.PRI_PACE, "pace"), (co.PRI_EDGE, "edge"))
    drawn = _frame(k, 0.5, (co.PRI_PACE, "pace"), (co.PRI_EDGE, "edge"))
    assert [d[0] for d in drawn] == ["edge"]
    assert drawn[0][1] == co.STATUS and drawn[0][2] == 480 - co.PROMPT_Y


def test_coach_does_not_let_a_prompt_be_overwritten_early():
    from core.ui import coach as co
    k = co.Coach()
    _frame(k, 0.0, (co.PRI_PACE, "pace"))
    # something more important turns up 0.3 s later: it waits its turn
    assert _frame(k, 0.3, (co.PRI_EDGE, "edge"),
                  (co.PRI_PACE, "pace"))[0][0] == "pace"
    _frame(k, co.MIN_SHOW_S + 0.01, (co.PRI_EDGE, "edge"))
    assert k.msg == "edge"                     # (fading in from this frame)


def test_coach_lingers_then_fades_and_clears_on_request():
    from core.ui import coach as co
    k = co.Coach()
    _frame(k, 0.0, (co.PRI_HAND, "hand"))
    assert _frame(k, co.LINGER_S * 0.5)        # still up, nobody asking
    assert not _frame(k, co.LINGER_S + 1.0)    # gone
    _frame(k, 5.0, (co.PRI_HAND, "hand"))
    k.clear()
    assert not _frame(k, 5.1)



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
