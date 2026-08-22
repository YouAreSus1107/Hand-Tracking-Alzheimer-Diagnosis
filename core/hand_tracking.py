"""
Hand Tracking / UDP Broadcast + Live Data Inspector
====================================================
Uses OpenCV + MediaPipe Tasks API to detect hand landmarks from a webcam,
draws the skeleton overlay, and broadcasts the 21 landmark positions (x, y, z)
per hand over UDP to 127.0.0.1:5052 for any downstream consumer.

On top of the raw tracker this is a *data inspector*: it overlays, live, the
same signals the screening tests record so you can watch what finger_tapping.py
"sees" outside a scored run and inspect raw landmark values while debugging
tracking lag / drift / occlusion:

  - Tap signal + events -- thumb->index scale-invariant distance, tap count /
    rate, open/closed state, and a soft fingertip ripple + skeleton brighten on
    each tap. A tap registers when the distance drops below a fixed 0.20
    threshold (hysteresis re-opens at 0.30). Reuses thumb_index_distance and
    TapDetector from core/tapping/detector.py.
  - Raw landmark readout -- a compact table of key landmarks (wrist, fingertips)
    with x / y / z.

Overlay is styled with the shared core/ui Canvas toolkit per
docs/UI_STYLE_GUIDE.md. UDP broadcast is unchanged.

Keys:  q quit   c reset counters   r toggle raw-landmark readout
"""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))  # keep first: hand_utils import path

import cv2
from core import quiet          # keep above mediapipe: silences its startup log
import mediapipe as mp

from core.hand_utils import (HAND_CONNECTIONS, make_landmark_filters,
                             smooth_landmarks, preprocess_for_mediapipe)
from core.camera import open_capture
from core.tapping.detector import TapDetector, thumb_index_distance
from core.ui import theme
from core.ui.anim import ease_out_cubic, lerp
from core.ui.components import Canvas, draw_hand_skeleton

MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

# ── UDP ────────────────────────────────────────────────────────────────────
UDP_IP = "127.0.0.1"
UDP_PORT = 5052

# ── Tap detection tuning (mirrors the max-speed tapping mode) ───────────────
MIN_INTERTAP_S = 0.5 / 5.0      # fastest plausible tap at ~5 Hz max-speed
EMA_ALPHA = 0.6                 # detector smoothing (EMA_ALPHA_FAST)
TAP_CLOSE = 0.20               # tap registers when normalized distance < this
TAP_OPEN = 0.30                # hysteresis: must re-open above this before next tap

# ── Inspector layout ───────────────────────────────────────────────────────
PANEL_W = 210
PLOT_LO = 0.0                  # sparkline y-axis floor (span-normalized distance)
PLOT_HI = 1.2                  # sparkline y-axis roof; samples above clamp to it
KEY_LANDMARKS = [(0, "Wrist"), (4, "Thumb"), (8, "Index"),
                 (12, "Middle"), (16, "Ring"), (20, "Pinky")]


class HandState:
    """Per-hand inspector state; persists while a hand comes and goes so the
    tap history isn't lost on a brief occlusion."""

    def __init__(self):
        self.detector = self._new_detector()
        self.flash_t = -1e9              # last tap time (ripple + skeleton glow)
        self.tap_px = (0, 0)             # fingertip midpoint of that tap

    @staticmethod
    def _new_detector() -> TapDetector:
        # Fixed threshold instead of per-session calibration: a tap fires when
        # the distance drops below TAP_CLOSE and re-arms above TAP_OPEN.
        det = TapDetector(MIN_INTERTAP_S, EMA_ALPHA, 0.0, 1.0)
        det.close_at, det.open_at = TAP_CLOSE, TAP_OPEN
        return det

    def reset(self):
        self.__init__()


class Inspector:
    def __init__(self, cap):
        self.cap = cap
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.65,
        )
        with quiet.muted_native_stderr():
            self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        # Per-hand One-Euro filter sets (separate filters for left/right hand).
        self.lm_filters = {'L': make_landmark_filters(),
                           'R': make_landmark_filters()}
        self.hands: dict[str, HandState] = {}

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.show_raw = True
        self.fps = 30.0
        self._last_frame_t: float | None = None

    def state_for(self, side: str) -> HandState:
        if side not in self.hands:
            self.hands[side] = HandState()
        return self.hands[side]

    # ── per-frame detection + UDP ─────────────────────────────────────────
    def process(self, frame, now: float) -> list[dict]:
        """Detect hands, update tap detection, broadcast UDP. Returns a list of
        render descriptors (one per detected hand)."""
        h, w = frame.shape[:2]
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        detected: list[dict] = []
        if not result.hand_landmarks:
            return detected

        # At most one hand per side: if MediaPipe reports two of the same
        # handedness, keep only the higher-confidence one (never two Lefts /
        # two Rights -- only a single hand, or one Left + one Right).
        best: dict[str, tuple[float, int]] = {}
        for i in range(len(result.hand_landmarks)):
            cat = result.handedness[i][0]
            s = cat.category_name[0]
            if s not in best or cat.score > best[s][0]:
                best[s] = (cat.score, i)
        keep = {idx for _, idx in best.values()}

        for i, hand_landmarks in enumerate(result.hand_landmarks):
            if i not in keep:
                continue
            # Frame is NOT flipped (preserves UDP pixel-x for consumers), so this
            # is MediaPipe's raw label, not the user's true hand.
            side = result.handedness[i][0].category_name[0]      # "L" or "R"
            fx, fy = self.lm_filters[side]
            smoothed = smooth_landmarks(hand_landmarks, fx, fy, now)
            d = thumb_index_distance(smoothed)

            hs = self.state_for(side)
            tapped = hs.detector.update(now, d)
            if tapped:
                hs.flash_t = now
                hs.tap_px = (int((smoothed[4][0] + smoothed[8][0]) / 2 * w),
                             int((smoothed[4][1] + smoothed[8][1]) / 2 * h))

            # ── UDP broadcast (unchanged pixel-scaled payload) ────────────
            vals = []
            for lm in smoothed:
                vals.extend([int(lm[0] * w), int(lm[1] * h), int(lm[2] * w)])
            msg = side + ":[" + ",".join(str(v) for v in vals) + "]"
            self.sock.sendto(msg.encode("utf-8"), (UDP_IP, UDP_PORT))

            detected.append({"side": side, "hs": hs, "lm": smoothed, "d": d})
        return detected

    # ── rendering ─────────────────────────────────────────────────────────
    def render(self, frame, detected: list[dict], now: float):
        # skeletons drawn directly on the frame (composited under the panels)
        for hd in detected:
            hs = hd["hs"]
            draw_hand_skeleton(frame, hd["lm"], HAND_CONNECTIONS,
                               highlight=(now - hs.flash_t) < 0.15)

        c = Canvas(frame)
        chips = [("Hand detected", "success") if detected
                 else ("Show your hand", "warning")]
        if self.fps < 24:
            chips.append((f"{self.fps:.0f} fps", "warning"))
        c.status_bar(chips)

        # Sides are unique (deduped in process): Left -> left column, Right -> right.
        for hd in detected:
            col_x = (theme.SAFE_MARGIN if hd["side"] == "L"
                     else c.w - PANEL_W - theme.SAFE_MARGIN)
            self._render_hand(c, now, hd, col_x)

        self._render_feedback(c, detected, now)
        c.disclaimer()
        return c.compose()

    def _render_hand(self, c: Canvas, now: float, hd: dict, col_x: int):
        hs, smoothed, d = hd["hs"], hd["lm"], hd["d"]
        name = "Left" if hd["side"] == "L" else "Right"
        y, ph = 56, 116
        c.panel(col_x, y, PANEL_W, ph)
        c.text(col_x + 12, y + 10, f"{name} hand", role="body_sb")

        closed = hs.detector._closed
        c.chip(col_x + 12, y + 38, "Closed" if closed else "Open",
               status="brand" if closed else "info", icon=False)
        c.text(col_x + 12, y + 74,
               f"Dist {d:.2f}" if d is not None else "Dist  --",
               role="caption", color="text-muted", mono=True)
        taps = len(hs.detector.tap_times)
        recent = [t for t in hs.detector.tap_times if t > now - 5]
        rate = ((len(recent) - 1) / (recent[-1] - recent[0])
                if len(recent) >= 2 and recent[-1] > recent[0] else 0.0)
        c.text(col_x + 12, y + 94, f"Taps {taps}   {rate:.1f} Hz",
               role="caption", color="text-muted", mono=True)

        # live distance signal + a dot per tap; y clamped to a fixed range so
        # wide-open excursions ride the roof instead of blowing over it (§5)
        sy = c.h - 26 - 8 - 70
        c.sparkline(col_x, sy, PANEL_W, 70, hs.detector.series,
                    hs.detector.tap_times, now, lo=PLOT_LO, hi=PLOT_HI)

        if self.show_raw and smoothed is not None:
            self._render_raw(c, col_x, smoothed)

    def _render_raw(self, c: Canvas, col_x: int, smoothed):
        ry, rph = 180, 180
        c.panel(col_x, ry, PANEL_W, rph)
        c.text(col_x + 12, ry + 8, "Landmarks Coordination", role="body_sb")
        for hx, htxt in ((100, "x"), (150, "y"), (200, "z")):
            c.text(col_x + hx, ry + 30, htxt, role="caption",
                   color="text-muted", anchor="ra")
        for i, (idx, nm) in enumerate(KEY_LANDMARKS):
            yy = ry + 50 + i * 20
            lm = smoothed[idx]
            c.text(col_x + 12, yy, nm, role="caption")
            for vx, val in ((100, lm[0]), (150, lm[1]), (200, lm[2])):
                c.text(col_x + vx, yy, f"{val:.2f}", role="caption",
                       mono=True, anchor="ra")

    def _render_feedback(self, c: Canvas, detected: list[dict], now: float):
        if theme.REDUCED_MOTION:
            return
        for hd in detected:
            hs = hd["hs"]
            if now - hs.flash_t < 0.25:
                p = (now - hs.flash_t) / 0.25
                c.ring(hs.tap_px[0], hs.tap_px[1],
                       lerp(10, 42, ease_out_cubic(p)), "success",
                       thickness=2, alpha=1.0 - p)
        recent = max((hd["hs"].flash_t for hd in detected), default=-1e9)
        c.border_glow("brand", 0.4 * max(0.0, 1 - (now - recent) / 0.2))

    # ── main loop ─────────────────────────────────────────────────────────
    def run(self):
        win = "Hand Detection 3D - Data Inspector  |  Q to quit"
        cv2.namedWindow(win)
        while self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                print("[WARNING] Ignoring empty camera frame.")
                continue
            now = time.time()
            if self._last_frame_t is not None:
                dt = max(1e-3, now - self._last_frame_t)
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)
            self._last_frame_t = now

            detected = self.process(frame, now)
            cv2.imshow(win, self.render(frame, detected, now))

            key = cv2.waitKey(5) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("c"):
                for hs in self.hands.values():
                    hs.reset()
            elif key == ord("r"):
                self.show_raw = not self.show_raw

        self.cap.release()
        cv2.destroyAllWindows()
        self.landmarker.close()
        self.sock.close()
        print("\n[INFO] Hand tracking stopped. Goodbye!")


def _select_source():
    print("\n--- Camera Selection ---")
    print("1. Default Laptop/USB Camera")
    print("2. Phone Camera (via IP Webcam app or similar)")
    choice = input("Enter 1 or 2 [Default 1]: ").strip()
    if choice == "2":
        print("\nTo use your phone, install an app like 'IP Webcam' (Android).")
        print("Ensure your phone and computer are on the SAME Wi-Fi network.")
        return input("Enter the video stream URL "
                     "(e.g., http://192.168.1.5:8080/video): ").strip()
    return 0


def main():
    source = _select_source()
    cap = open_capture(source)
    if cap is None:
        print(f"[ERROR] Could not open camera source: {source}. "
              "Please check your connection.")
        sys.exit(1)

    print("=" * 52)
    print("  Hand Detection 3D - Data Inspector")
    print("=" * 52)
    print(f"  Broadcasting UDP landmarks to {UDP_IP}:{UDP_PORT}")
    print("  Keys:  q quit   c reset counters   r toggle raw readout")
    print(f"  A tap registers when thumb-index distance drops below {TAP_CLOSE}.")
    print("=" * 52)

    Inspector(cap).run()


if __name__ == "__main__":
    main()
