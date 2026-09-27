"""
Hand framing (pure) -- is the whole hand inside the camera frame?

When part of the hand leaves the image, MediaPipe does not report the hand as
lost. It keeps regressing all 21 landmarks, guesses the hidden ones, and the
guesses jitter. Everything downstream then measures that jitter: the spiral's
raw fingertip path, and the tapping test's thumb-index distance, which can
register taps that never happened. Many older patients do not notice their hand
drifting to the edge, so this cannot be left to the instructions.

Landmarks are normalised to [0, 1], and MediaPipe places hidden ones at or
beyond the border, so a landmark within EDGE_CLIP of an edge means the hand
itself is already cut off there. All 21 landmarks count: they are joint
centres, so a clipped palm degrades the fingertip estimate too.

Levels:
  "ok"      -- the whole hand is comfortably inside.
  "near"    -- a landmark is within EDGE_NEAR of an edge; warn, keep the data.
  "clipped" -- a landmark is at or past an edge; the data is not trusted.
  "lost"    -- no hand detected at all.

FramingMonitor debounces the way back: clipped/lost is entered on the first
bad frame, but only cleared once the hand has stayed inside for CLEAR_HOLD_S,
because tracking is still settling in the frames after the hand returns.
It records each untrusted stretch as a (start, end) blackout, opened
PRE_ROLL_S early, since the hand is usually already drifting just before it
reaches the edge.

Stdlib-only; shared by the spiral and finger-tapping tests.
"""

from __future__ import annotations

EDGE_CLIP = 0.02      # within 2 % of the frame of an edge (or past it)
EDGE_NEAR = 0.07      # within 7 %: warn before it becomes a problem
CLEAR_HOLD_S = 0.4    # fully in view this long before trusting it again
PRE_ROLL_S = 0.15     # a blackout starts this much before the first bad frame

OK, NEAR, CLIPPED, LOST = "ok", "near", "clipped", "lost"
EDGES = ("left", "right", "top", "bottom")


def edge_state(points) -> tuple[str, tuple[str, ...]]:
    """(level, edges) for one frame's normalised (x, y[, z]) landmarks.
    `edges` lists the frame edges the hand is clipped at, or else near."""
    if not points:
        return LOST, ()
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    gaps = {"left": min(xs), "right": 1.0 - max(xs),
            "top": min(ys), "bottom": 1.0 - max(ys)}
    clipped = tuple(e for e in EDGES if gaps[e] < EDGE_CLIP)
    if clipped:
        return CLIPPED, clipped
    near = tuple(e for e in EDGES if gaps[e] < EDGE_NEAR)
    if near:
        return NEAR, near
    return OK, ()


class FramingMonitor:
    """Per-frame framing with a debounced 'untrusted' flag and a blackout log."""

    def __init__(self):
        self.level = OK
        self.edges: tuple[str, ...] = ()
        self.untrusted = False        # debounced: clipped or lost, not yet clear
        self.frames = 0
        self.clipped_frames = 0       # raw clipped frames (lost not counted)
        self.lost_frames = 0
        self.blackouts: list[tuple[float, float]] = []
        self._bad_since: float | None = None
        self._clear_since: float | None = None
        self._last_t: float | None = None

    def update(self, points, t: float) -> str:
        """Feed one frame (None when no hand). Returns the raw level."""
        self.frames += 1
        self._last_t = t
        self.level, self.edges = edge_state(points)
        bad = self.level in (CLIPPED, LOST)
        if self.level == CLIPPED:
            self.clipped_frames += 1
        elif self.level == LOST:
            self.lost_frames += 1

        if bad:
            self._clear_since = None
            if not self.untrusted:
                self.untrusted = True
                self._bad_since = t
        elif self.untrusted:
            if self._clear_since is None:
                self._clear_since = t
            if t - self._clear_since >= CLEAR_HOLD_S:
                self.untrusted = False
                self._close(t)
        return self.level

    def _close(self, t: float):
        if self._bad_since is not None:
            self.blackouts.append((self._bad_since - PRE_ROLL_S, t))
        self._bad_since = None
        self._clear_since = None

    def finish(self) -> list[tuple[float, float]]:
        """Close any open blackout at the last frame; return the log."""
        if self.untrusted and self._last_t is not None:
            self._close(self._last_t)
        return self.blackouts

    @property
    def clipped_pct(self) -> float:
        return 100.0 * self.clipped_frames / self.frames if self.frames else 0.0


def overlaps(t0: float, t1: float, blackouts) -> bool:
    """True if [t0, t1] touches any blackout interval."""
    return any(t0 <= b1 and t1 >= b0 for b0, b1 in blackouts or ())


def hint(edges, tracing: bool = False) -> str:
    """Coaching line for a clipped/near hand. Deliberately says 'toward the
    middle' rather than left/right: the picture is mirrored, and an older
    patient told 'move left' has to work out whose left.

    `tracing` is the spiral, where the fingertip has to stay on the line: off
    the bottom there means the hand is too big in the picture (the palm hangs
    below the fingertip), and raising it would only pull the finger off the
    spiral -- so the advice is to sit back instead."""
    if tracing and "bottom" in edges:
        return MOVE_BACK
    if "bottom" in edges and len(edges) == 1:
        return "Raise your hand a little"
    if "top" in edges and len(edges) == 1:
        return "Lower your hand a little"
    return "Move your hand toward the middle"


# The same words as the bottom-edge hint on the spiral, so the pre-start
# distance advice and the live prompt read as one instruction.
MOVE_BACK = "Move your hand back from the screen"


def hang(points, tip_idx: int = 8) -> float | None:
    """How far the hand reaches below the fingertip, in frame heights. On the
    spiral this is what has to fit under the lowest arm."""
    if not points:
        return None
    return max(p[1] for p in points) - points[tip_idx][1]
