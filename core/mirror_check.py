"""
The once-per-camera mirroring check (core/orientation.py has the why).

ensure_orientation(cap) returns at once for a camera whose answer is saved,
which is every launch after the first. Otherwise it opens a short check
window: raise your right hand beside your face and hold it there for a
second. The answer is saved, applied to `cap`, and the window closes before
the tool opens its own.

Nothing moves and the camera picture stays on screen throughout, so the hand
cannot drift out of frame unnoticed. The face comes from the same Face
Landmarker the eye-movement test uses (model/face_landmarker.task).

Q, Esc or the window's close button skips the check: nothing is saved, the
frames stay as the camera sends them, and the next launch asks again.
"""

from __future__ import annotations

import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

import cv2
from core import quiet       # keep above mediapipe: silences its startup log
import mediapipe as mp

from core import i18n, orientation
from core.camera import Capture, create_display_window, show, window_closed
from core.hand_utils import HAND_CONNECTIONS
from core.ui import theme
from core.ui.components import Canvas, draw_hand_skeleton

HAND_MODEL = str(_REPO_ROOT / "model" / "hand_landmarker.task")
FACE_MODEL = str(_REPO_ROOT / "model" / "face_landmarker.task")
WIN = "Camera check  |  Q to skip"
NOSE_TIP = 1                  # Face Landmarker mesh index
DONE_S = 1.5                  # the answer stays up this long before the tool opens


def ensure_orientation(cap: Capture) -> None:
    saved = orientation.load(cap.source)
    if saved is not None:
        cap.mirrored = saved
        return
    cap.mirrored = False            # the check must read the camera's own picture
    try:
        result = _run_check(cap)
    except Exception as exc:        # a missing model must not stop the test itself
        print("[WARNING] " + i18n.ct("Camera mirroring check could not run: {error}",
                                     error=exc))
        result = None
    if result is None:
        print("[INFO] " + i18n.ct("Camera mirroring check skipped - frames are "
                                  "used as the camera sends them. It will be "
                                  "asked again next launch."))
        return
    cap.mirrored = result
    if not orientation.save(cap.source, result):
        print("[WARNING] " + i18n.ct("Could not save the mirroring answer; "
                                     "it will be asked again next launch."))
    print("[INFO] " + (i18n.ct("Camera picture is mirrored - corrected.") if result
                       else i18n.ct("Camera picture is not mirrored.")))


def _landmarkers():
    vision = mp.tasks.vision
    hand_opts = vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=HAND_MODEL),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,                # two in view must be seen, to be refused
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.6,
    )
    face_opts = vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=FACE_MODEL),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
    )
    with quiet.muted_native_stderr():
        hands = vision.HandLandmarker.create_from_options(hand_opts)
        try:
            face = vision.FaceLandmarker.create_from_options(face_opts)
        except Exception:
            hands.close()
            raise
    return hands, face


def _prompt(n_hands: int, face_x, hand_x, label) -> tuple[str, str]:
    """(instruction, status) for this frame, most pressing first."""
    if face_x is None:
        return i18n.t("Show your face to the camera"), "warning"
    if n_hands > 1:
        return i18n.t("Show one hand only"), "warning"
    if (hand_x is not None and label is not None
            and abs(hand_x - face_x) >= orientation.SIDE_MARGIN
            and orientation.frame_side(hand_x, face_x, label) is None):
        return i18n.t("Use your right hand, palm to the camera"), "warning"
    return i18n.t("Raise your right hand beside your face"), "info"


def _run_check(cap: Capture) -> bool | None:
    hands, face = _landmarkers()
    vote = orientation.SideVote()
    answer: bool | None = None
    done_t = 0.0
    window_ready = False
    last_ms = -1
    try:
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                continue
            if not window_ready:
                create_display_window(WIN, frame.shape[1], frame.shape[0])
                window_ready = True
            now = time.time()
            ms = max(last_ms + 1, int(now * 1000))   # VIDEO mode wants strictly rising
            last_ms = ms
            img = mp.Image(image_format=mp.ImageFormat.SRGB,
                           data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            hres = hands.detect_for_video(img, ms)
            fres = face.detect_for_video(img, ms)

            n_hands = len(hres.hand_landmarks or [])
            lms = label = hand_x = None
            if n_hands == 1:
                lms = [(p.x, p.y, p.z) for p in hres.hand_landmarks[0]]
                label = hres.handedness[0][0].category_name
                hand_x = sum(p[0] for p in lms) / len(lms)
            nose = fres.face_landmarks[0][NOSE_TIP] if fres.face_landmarks else None
            face_x = nose.x if nose is not None else None

            if answer is None:
                answer = vote.feed(now, hand_x, face_x, label)
                if answer is not None:
                    done_t = now
            elif now - done_t >= DONE_S:
                return answer

            if lms is not None:
                draw_hand_skeleton(frame, lms, HAND_CONNECTIONS,
                                   highlight=vote.side is not None)
            c = Canvas(frame)
            if nose is not None:
                c.dot(int(nose.x * c.w), int(nose.y * c.h), 5, "brand")
            _draw(c, answer, vote.progress(now),
                  _prompt(n_hands, face_x, hand_x, label))
            show(WIN, c.compose())

            key = cv2.waitKey(5) & 0xFF
            if key in (ord("q"), 27) or window_closed(WIN):
                return None
        return None
    finally:
        hands.close()
        face.close()
        if window_ready:
            cv2.destroyWindow(WIN)
            cv2.waitKey(1)


def _draw(c: Canvas, answer: bool | None, frac: float,
          prompt: tuple[str, str]) -> None:
    w = c.w
    pw = min(560, w - 2 * theme.SAFE_MARGIN)
    px, py, ph = (w - pw) // 2, theme.SAFE_MARGIN, 150
    c.panel(px, py, pw, ph)
    c.text(w // 2, py + 30, i18n.t("Camera check"), role="h2", anchor="mm")
    if answer is None:
        line, status = prompt
    else:
        line = (i18n.t("Picture is mirrored. It will be corrected")
                if answer else i18n.t("Picture is not mirrored"))
        status, frac = "success", 1.0
    c.text(w // 2, py + 68, line, role="body_l",
           color="warning" if status == "warning" else "text", anchor="mm")
    c.progress_bar(px + 24, py + 96, pw - 48, frac,
                   color="success" if status == "success" else "brand")
    c.text(w // 2, py + 128, i18n.t("Checked once per camera. Press Q to skip"),
           role="caption", color="text-muted", anchor="mm")
