"""
Is this camera's picture mirrored?

Some cameras hand OpenCV a mirrored picture, most do not, and nothing in the
image can tell the two apart: a mirrored right hand *is* a left hand, pixel for
pixel. So it is asked once per camera (core/mirror_check.py) and remembered
here, and core/camera.open_capture() flips a mirrored camera's frames straight
after reading them. Every tool therefore sees the same unmirrored picture
whichever camera is plugged in, and flips it for selfie view itself as before.

The check: the user raises their right hand beside their face. On an
unmirrored picture that hand sits to the image's LEFT of the face; on a
mirrored one, to its right. That geometry decides, and needs nothing from
MediaPipe but positions -- no movement, no convention about labels.

MediaPipe's handedness label only confirms it. On an unmirrored picture it
names the real hand (core/hand_utils.true_hand), so the raised right hand
reads "Right"; mirrored, it reads "Left". A frame where the label and the
position disagree -- usually the back of the hand, or a misread -- is simply
not counted, so a doubtful frame delays the answer and never flips it.

What no check can catch is the user raising their LEFT hand: position and
label then agree on the wrong answer. That is what the camera chip's
"Picture" setting is for.

Stdlib-only and import-cheap: launcher.py reads and writes the same answers
for the camera chip's "Picture" setting.
"""

from __future__ import annotations

import json
from pathlib import Path

# Shared with core/camera.py's backend cache: one git-ignored file of
# per-camera runtime facts. Its keys are "<source>|<w>x<h>|<fps>", so the
# "mirror" key cannot collide with them.
CACHE_PATH = Path(__file__).resolve().parents[1] / ".camera_cache.json"
_KEY = "mirror"

# ── the hold ───────────────────────────────────────────────────────────────
SIDE_MARGIN = 0.08    # hand centre at least this far from the nose (frame widths)
HOLD_S = 1.0          # one side held this long decides
MIN_FRAMES = 8        # ...over at least this many frames (a 5 fps stall cannot)
GAP_S = 0.30          # a longer run of unusable frames restarts the hold


def source_key(source: int | str) -> str:
    return str(source).strip()


def _read() -> dict:
    try:
        data = json.loads(CACHE_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load(source: int | str) -> bool | None:
    """True mirrored, False not, None never checked."""
    entry = _read().get(_KEY)
    if not isinstance(entry, dict):
        return None
    value = entry.get(source_key(source))
    return value if isinstance(value, bool) else None


def save(source: int | str, mirrored: bool | None) -> bool:
    """Remember the answer; None forgets it so the next launch asks again.
    Returns False when the file cannot be written (read-only checkout)."""
    data = _read()
    entry = data.get(_KEY)
    if not isinstance(entry, dict):
        entry = {}
    if mirrored is None:
        entry.pop(source_key(source), None)
    else:
        entry[source_key(source)] = bool(mirrored)
    data[_KEY] = entry
    try:
        CACHE_PATH.write_text(json.dumps(data), "utf-8")
    except OSError:
        return False
    return True


def frame_side(hand_x: float | None, face_x: float | None,
               label: str | None) -> bool | None:
    """What one frame says: True mirrored, False not, None unusable.

    `hand_x`/`face_x` are normalised image x of the one hand in view and the
    nose, or None when there is not exactly one of each. `label` is
    MediaPipe's raw handedness for that hand.
    """
    if hand_x is None or face_x is None:
        return None
    dx = hand_x - face_x
    if abs(dx) < SIDE_MARGIN:
        return None
    mirrored = dx > 0
    if label != ("Left" if mirrored else "Right"):
        return None
    return mirrored


class SideVote:
    """One side held steadily for HOLD_S decides."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.side: bool | None = None
        self.start_t = 0.0
        self.last_t = 0.0
        self.frames = 0
        self.mirrored: bool | None = None

    def feed(self, t: float, hand_x: float | None, face_x: float | None,
             label: str | None) -> bool | None:
        if self.mirrored is not None:
            return self.mirrored
        side = frame_side(hand_x, face_x, label)
        if side is None:
            if self.side is not None and t - self.last_t > GAP_S:
                self.side, self.frames = None, 0
            return None
        if side != self.side or t - self.last_t > GAP_S:
            self.side, self.start_t, self.frames = side, t, 0
        self.last_t = t
        self.frames += 1
        if self.frames >= MIN_FRAMES and t - self.start_t >= HOLD_S:
            self.mirrored = side
        return self.mirrored

    def progress(self, t: float) -> float:
        if self.mirrored is not None:
            return 1.0
        if self.side is None:
            return 0.0
        return max(0.0, min(1.0, (t - self.start_t) / HOLD_S))
