"""
Spiral Tracing Test for Early Alzheimer's Screening
=====================================================
Self-paced Archimedes-spiral trace with the index fingertip in the air. There is
no dot to chase: the user traces the spiral outward at their own pace and the run
is scored on the *quality of the movement* (smoothness / jitter), matching the
clinical pen test. See docs/tests/SPIRAL_TEST_PLAN.md.

Before the scored run the user traces a smaller practice spiral the same way,
coached live on pace (a speed gauge and a soft band marking where the
recommended pace would have them), on staying near the line, and on
smoothness (core/spiral/practice.py). Practice samples are never saved.

Headline metric (core/spiral/metrics.py):
  Smoothness index -- SPARC (Spectral Arc Length; Balasubramanian et al. 2015),
                      mapped to 0-100 (higher = smoother).
Support metrics:
  Norm. Jerk       -- dimensionless jerk of the position path.
  Velocity CV%     -- speed coefficient of variation (Schroter V-Rel 2003).
  Tremor power/freq-- detrended-position tremor-band readout (coarse at 30 fps).
  Completion %     -- fraction of the template traced (data-quality gate).

Jitter is measured on the RAW fingertip; the One-Euro smoothing used for display
would erase it. Reference: Kachouri et al. (2021), Schroter et al. (2003),
Namkoong & Roh (2024), Balasubramanian et al. (2015).

This file is the run loop + rendering only; the scoring engine lives in
core/spiral/, and UI/camera/audio/persistence in core/ (see UI_STYLE_GUIDE.md).
Results auto-save to results/ as JSON + a CSV index row.

Run:  python screening_tests/spiral_test.py     Quit: press 'q'
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))  # keep first: hand_utils import path

# Stdlib-only, and above the heavy imports on purpose: cv2 + mediapipe take
# ~2 s warm and ~10 s cold, and nothing reaches the console until they land.
from core import i18n
from core.splash import Splash, IMPORT_STEPS
_splash = Splash("Spiral Tracing Test",
                 "Click 'Start Test' in the camera window.  Q to quit.",
                 IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
_splash.step()               # OpenCV in
from core import quiet       # keep above mediapipe: silences its startup log
import mediapipe as mp
_splash.step()               # MediaPipe in
import numpy as np

from core.hand_utils import (HAND_CONNECTIONS, make_landmark_filters,
                             smooth_landmarks, preprocess_for_mediapipe,
                             true_hand)
from core.camera import (select_camera_source, open_capture,
                         create_display_window, window_closed, pause_before_exit)
from core.mirror_check import ensure_orientation
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.ui import theme
from core.ui.anim import CountUp, ease_out_cubic, lerp
from core.ui.components import Canvas, draw_hand_skeleton, get_font
from core.spiral.geometry import (scale_spiral_to_frame, practice_coefficient,
                                 SPIRAL_TURNS, SPIRAL_NUM_POINTS,
                                 PRACTICE_TURNS)
from core.spiral.progress import SpiralProgress
from core import framing
from core.ui.framing_ui import framing_chips, draw_framing
from core.ui.coach import (Coach, PROMPT_Y, PRI_HAND, PRI_LINE, PRI_SETUP,
                           PRI_PACE)
from core.spiral.metrics import compute_metrics, live_smoothness_status
from core.spiral.practice import (arc_length, target_speed_px_s,
                                  recommended_time_s, pace_band,
                                  progress_speed, expected_index,
                                  coach_message, practice_summary, MSG_START,
                                  MSG_OFF_LINE, PACE_TOLERANCE)

_splash.done()   # imports are in; the camera prompt follows immediately

APP_VERSION = "0.3.0"
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

# ── Test Configuration ────────────────────────────────────────────────────
RECORDING_MAX      = 60       # safety cap (s); the run ends on completion first
PRACTICE_MAX_S     = 30       # safety cap on the unscored practice spiral
COUNTDOWN_FROM     = 3

# Spiral geometry (SPIRAL_TURNS / SPIRAL_NUM_POINTS imported from the engine)
SPIRAL_LINE_THICK  = 3

# Practice pace zone: the stretch of the practice spiral, either side of where
# the recommended pace would put the fingertip now, drawn as a soft band.
PACE_ZONE_FRAC     = 0.06     # half-width, as a fraction of the spiral's points
PACE_ZONE_THICK    = 16

# Marker used for the center start dot (not scored).
GUIDE_DOT_RADIUS   = 12

# Self-paced end condition: the trace finishes when the user's swept progress
# reaches this fraction of the spiral (they've traced out to the rim).
END_PROGRESS_FRAC  = 0.985

# Preparation phase: fingertip must reach the spiral center to start
CENTER_THRESHOLD   = 40       # px from center that counts as "on the start dot"
PREPARE_HOLD       = 0.6      # seconds held at center before scoring begins

FINGERTIP_IDX      = 8        # MediaPipe landmark: index fingertip

# Resume marker shown while the fingertip is off its own arm (progress frozen).
RESUME_RING_RADIUS = 14

# Live-smoothness coaching: recompute the fingertip colour band from a rolling
# window this often (s) over this many recent seconds of the raw fingertip path.
LIVE_CHECK_EVERY   = 0.4
LIVE_WINDOW_S      = 4.0

# ── States ────────────────────────────────────────────────────────────────
(IDLE, INSTRUCTION, COUNTDOWN, PRACTICE, PRACTICE_DONE, PREPARE, RECORDING,
 COMPLETE) = ("idle", "instruction", "countdown", "practice", "practice_done",
              "prepare", "recording", "complete")

# Speed-gauge readout per pace band: (label, status token).
PACE_LABELS = {"slow": ("Too slow", "warning"), "good": ("Good", "success"),
               "fast": ("Too fast", "warning")}

INSTRUCTIONS = [
    "Using your preferred hand, trace the spiral outward",
    "from the center to the edge - at your own",
    "comfortable pace. There is no dot to chase.",
    "Just move as smoothly and steadily as you can.",
]


class App:
    def __init__(self, cap):
        # 60 fps (MJPG) is requested by open_capture so the raw fingertip
        # resolves more of the tremor band; the loop measures and reports the
        # actual rate and falls back to whatever the camera delivers
        # (docs/tests/SPIRAL_TEST_PLAN.md §3.3).
        self.cap = cap
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.55,
        )
        with quiet.muted_native_stderr():
            self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.audio = AudioWorker()
        self.start_wav = build_tone(880, 100)
        self.tick_wav = build_tone(660, 60)
        self.done_wav = build_tone(523, 180)

        self.state = IDLE
        self.coach = Coach()           # the one place prompts appear
        self.framing = framing.FramingMonitor()
        self._raw_pts = None
        self.lm_filters_x, self.lm_filters_y = make_landmark_filters()

        self.mouse = (0, 0)
        self.click: tuple[int, int] | None = None
        self.fps = 30.0
        self._last_frame_t: float | None = None

        self.reset_run()

    # ── run-scoped state ──────────────────────────────────────────────────
    def reset_run(self):
        self.spiral_ready = False
        self.spiral_points: list = []
        self.spiral_np = None
        self.spiral_center = (0, 0)
        self.spiral_b = 0.0              # Archimedes coefficient r = b*theta
        self.practice_points: list = []
        self.practice_len = 0.0          # practice spiral arc length (px)
        self.target_speed = 0.0          # recommended progress speed (px/s)

        self.frame_data: list[dict] = []
        self._max_reached_idx = 0        # user's furthest honest progress (index)
        self.tracker: SpiralProgress | None = None
        self._center_hold_start = None   # when the fingertip reached center
        self._live_status = "info"       # rolling smoothness band (fingertip hue)
        self._live_check_t = 0.0         # last live-smoothness recompute time
        self.hand_labels: dict[str, int] = {}

        self.t_state = time.time()
        self.recording_start = None
        self.results = None
        self.saved_path = None
        self.countup: CountUp | None = None
        self.reset_practice()

    def reset_practice(self):
        """Practice-only state, kept apart from frame_data so nothing traced
        in practice can reach the scored session."""
        self._center_hold_start = None
        self._p_started = False
        self._p_start_t = 0.0
        self._p_max_idx = 0
        self._p_tracker: SpiralProgress | None = None
        self._p_samples: list[tuple[float, float, float]] = []  # raw (t, x, y)
        self._p_arc_hist: list[tuple[float, float]] = []        # (t, arc px)
        self._p_paces: list = []
        self._p_on_line: list[bool] = []
        self._p_speed = None
        self._p_pace = None
        self._p_smooth = "info"
        self._p_coach = (MSG_START, "info")
        self._p_coach_t = 0.0
        self._p_summary = None

    def goto(self, state: str, now: float):
        self.coach.clear()       # a prompt never outlives its screen
        self.state = state
        self.t_state = now

    # ── input ─────────────────────────────────────────────────────────────
    def on_mouse(self, event, x, y, flags, param):
        self.mouse = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            self.click = (x, y)

    def hit(self, rect) -> bool:
        if self.click is None or rect is None:
            return False
        x, y, w, h = rect
        cx, cy = self.click
        return x <= cx <= x + w and y <= cy <= y + h

    def hover(self, x, y, w, h) -> bool:
        mx, my = self.mouse
        return x <= mx <= x + w and y <= my <= y + h

    # ── per-frame pipeline ────────────────────────────────────────────────
    def detect_hand(self, frame, now: float):
        """Return (smoothed_landmarks, raw_fingertip, raw_points), or Nones.
        raw_points are all 21 unfiltered (x, y) for the framing check. The raw
        fingertip is the *unfiltered* index-tip (x, y) in normalized [0,1] space
        -- jitter measurement runs on it because the One-Euro smoothing used for
        display would erase the signal (docs/tests/SPIRAL_TEST_PLAN.md §3.1)."""
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        if not result.hand_landmarks:
            return None, None, None
        # Frame is flipped to selfie view, so MediaPipe's label names the
        # OTHER hand -- true_hand() undoes that (core/hand_utils.py).
        if result.handedness:
            label = true_hand(result.handedness[0][0].category_name,
                              selfie=True)
            self.hand_labels[label] = self.hand_labels.get(label, 0) + 1
        raw = result.hand_landmarks[0][FINGERTIP_IDX]
        raw_tip = (raw.x, raw.y)
        raw_pts = [(lm.x, lm.y) for lm in result.hand_landmarks[0]]
        smoothed = smooth_landmarks(result.hand_landmarks[0],
                                    self.lm_filters_x, self.lm_filters_y, now)
        return smoothed, raw_tip, raw_pts

    def _fingertip_px(self, landmarks, c: Canvas):
        return (int(landmarks[FINGERTIP_IDX][0] * c.w),
                int(landmarks[FINGERTIP_IDX][1] * c.h))

    def _draw_resume(self, c: Canvas, points, idx: int, tip):
        """Off the arm: progress is frozen, so mark where it stopped and link
        the fingertip back to it. A fixed point to return to, not a pacer."""
        rx, ry = points[max(0, min(len(points) - 1, idx))]
        c.polyline([tip, (rx, ry)], "warning", thickness=1, alpha=0.7)
        c.ring(rx, ry, RESUME_RING_RADIUS, "warning", thickness=2)
        c.dot(tip[0], tip[1], 8, "warning")
        self.coach.say(i18n.t(MSG_OFF_LINE), PRI_LINE)

    def _guide_dot(self, c: Canvas, gx, gy):
        c.dot(gx, gy, GUIDE_DOT_RADIUS, "warning", outline="text", outline_w=2)

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 118, 212
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, i18n.t("Spiral Tracing Test"), role="h1",
               anchor="mm")
        c.text(w // 2, py + 74,
               i18n.t("Measures movement smoothness and jitter -"),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 98, i18n.t("markers studied in cognitive decline."),
               role="body", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        bx, by = px + theme.SPACE[4], py + 132
        b = c.button(bx, by, bw, 48, i18n.t("Start Test"), variant="primary",
                     hovered=self.hover(bx, by, bw, 48), icon="play")
        c.disclaimer()
        if self.hit(b):
            self.reset_run()
            self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        w, h = c.w, c.h
        # keyed, not line by line: Chinese sets its own line breaks
        lines = i18n.tk("spiral.instructions", INSTRUCTIONS)
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 34, i18n.t("Your Task"), role="h2", anchor="mm",
               color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        c.text(w // 2, py + 84 + len(lines) * 30,
               i18n.t("First a short practice spiral with pace tips, "
                      "then the scored spiral."),
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, i18n.t("I'm Ready"), variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.hit(b):
            self.goto(COUNTDOWN, now)

    def screen_countdown(self, c: Canvas, now: float):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining <= 0:
            self._start_practice(now)
            return
        frac_sec = elapsed - int(elapsed)
        c.ring(w // 2, h // 2, 64, "brand", thickness=4,
               sweep_deg=360 * (1 - frac_sec) if not theme.REDUCED_MOTION else 360)
        scale = lerp(1.3, 1.0, ease_out_cubic(frac_sec / 0.3)) \
            if not theme.REDUCED_MOTION else 1.0
        c._dirty = True
        c.draw.text((w // 2, h // 2), str(remaining),
                    font=get_font("bold", int(64 * scale)),
                    fill=theme.rgba("text", 1.0), anchor="mm")
        c.text(w // 2, h // 2 - 100, i18n.t("Get ready..."), role="h2",
               anchor="mm",
               color="text-muted")
        if int(elapsed) != getattr(self, "_last_tick", -1):
            self._last_tick = int(elapsed)
            self.audio.play(self.tick_wav)

    def _start_practice(self, now: float):
        self.reset_practice()
        self.goto(PRACTICE, now)

    def _start_prepare(self, now: float):
        self._center_hold_start = None
        self.goto(PREPARE, now)

    def _start_recording(self, now: float):
        self.recording_start = now
        self.frame_data = []
        self._max_reached_idx = 0
        self.tracker = SpiralProgress(self.spiral_center, self.spiral_b,
                                      SPIRAL_TURNS, SPIRAL_NUM_POINTS)
        self.framing = framing.FramingMonitor()   # counts cover the scored run
        self._live_status = "info"
        self._live_check_t = now
        # fresh filters so practice smoothing lag doesn't bleed into display
        new_x, new_y = make_landmark_filters()
        self.lm_filters_x[:] = new_x
        self.lm_filters_y[:] = new_y
        self.audio.play(self.start_wav)
        self.goto(RECORDING, now)

    def _center_hold(self, c: Canvas, now: float, landmarks):
        """Start gate shared by practice and the scored run: the fingertip
        must rest on the center dot for PREPARE_HOLD s. Draws the target and
        returns (at_center, done)."""
        cx, cy = self.spiral_center
        c.ring(cx, cy, CENTER_THRESHOLD, "info", thickness=2, alpha=0.6)
        self._guide_dot(c, cx, cy)

        if landmarks is None:
            self.coach.say(i18n.t("Show your hand to the camera"), PRI_HAND)
        else:
            # Advice only, never a gate: whole-hand fit under the lowest arm
            # would need the patient ~2 m back, so this asks for "further",
            # and the bottom arm can be skipped if it still clips.
            hg = framing.hang(self._raw_pts)
            if hg is not None and hg > self.hang_budget:
                self.coach.say(i18n.t(framing.MOVE_BACK), PRI_SETUP)

        at_center = False
        if landmarks is not None and not self.framing.untrusted:
            tip = self._fingertip_px(landmarks, c)
            at_center = math.hypot(tip[0] - cx, tip[1] - cy) < CENTER_THRESHOLD
            status = "success" if at_center else "info"
            c.polyline([tip, (cx, cy)], status, thickness=1, alpha=0.7)
            c.dot(tip[0], tip[1], 8, status)

        if not at_center:
            self._center_hold_start = None
            return False, False
        if self._center_hold_start is None:
            self._center_hold_start = now
        held = now - self._center_hold_start
        if held >= PREPARE_HOLD:
            self._center_hold_start = None
            return True, True
        # progress ring closes around the target as they hold steady
        c.ring(cx, cy, CENTER_THRESHOLD + 8, "success", thickness=4,
               sweep_deg=360 * (held / PREPARE_HOLD)
               if not theme.REDUCED_MOTION else 360)
        return True, False

    def _hold_message(self, at_center: bool) -> str:
        return i18n.t("Hold steady..." if at_center
                      else "Move your fingertip onto the center dot to begin.")

    # ── practice (unscored) ───────────────────────────────────────────────
    def _phase_panel(self, c: Canvas, lines):
        """Bottom-centre panel of (text, colour) lines, stacked so its bottom
        edge stays clear of the Coach's prompt slot -- the two never overlap."""
        w, h = c.w, c.h
        ph = 14 + 26 * len(lines)
        pw = min(480, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, h - PROMPT_Y - 8 - ph
        c.panel(px, py, pw, ph)
        for i, (text, color) in enumerate(lines):
            c.text(w // 2, py + 20 + 26 * i, text, role="body", anchor="mm",
                   color=color)

    def _pace_gauge(self, c: Canvas):
        """Top-left speed gauge: a slow / good / fast track scaled 0 to twice
        the recommended pace, with a marker at the current progress speed."""
        x, y, gw, gh = theme.SAFE_MARGIN, 60, 240, 64
        c.panel(x, y, gw, gh, alpha=0.75, radius=12, shadow=False)
        c.text(x + 14, y + 12, i18n.t("Pace"), role="body_sb")
        label, status = PACE_LABELS.get(self._p_pace, ("-", "text-muted"))
        c.text(x + gw - 14, y + 12, i18n.t(label), role="body_sb",
               color=status, anchor="ra")

        bx, by, bw, bh = x + 14, y + 42, gw - 28, 10
        lo = (1.0 - PACE_TOLERANCE) / 2.0    # zone edges on a 0..2x scale
        hi = (1.0 + PACE_TOLERANCE) / 2.0
        c._dirty = True
        for f0, f1, tok, a in ((0.0, lo, "warning", 0.35),
                               (lo, hi, "success", 0.6),
                               (hi, 1.0, "warning", 0.35)):
            c.draw.rectangle([bx + int(bw * f0), by, bx + int(bw * f1), by + bh],
                             fill=theme.rgba(tok, a))
        if self._p_speed is not None and self.target_speed > 0:
            f = max(0.0, min(1.0, self._p_speed / (2 * self.target_speed)))
            mx = bx + int(bw * f)
            c.draw.rounded_rectangle([mx - 2, by - 5, mx + 2, by + bh + 5],
                                     radius=2, fill=theme.rgba("text", 1.0))

    def screen_practice(self, c: Canvas, now: float, landmarks, raw_tip):
        w, h = c.w, c.h
        pts = self.practice_points
        n = len(pts)

        if not self._p_started:
            c.polyline(pts, "text-muted", thickness=SPIRAL_LINE_THICK,
                       alpha=0.40)
            at_center, done = self._center_hold(c, now, landmarks)
            if done:
                self._p_started = True
                self._p_start_t = now
                self._p_tracker = SpiralProgress(
                    self.spiral_center, practice_coefficient(self.spiral_b),
                    PRACTICE_TURNS, n)
                self._p_coach_t = now
                self.audio.play(self.tick_wav)
                return
            self._phase_panel(c, [
                (i18n.t("Practice - not scored yet"), "warning"),
                (self._hold_message(at_center), "text-muted")])
            return

        elapsed = now - self._p_start_t

        # pace zone first, so the template line stays visible on top of it
        ei = expected_index(elapsed, self.target_speed, self.practice_len, n)
        half = max(4, int(PACE_ZONE_FRAC * n))
        c.polyline(pts[max(0, ei - half):min(n, ei + half + 1)], "info",
                   thickness=PACE_ZONE_THICK, alpha=0.45)
        c.polyline(pts, "text-muted", thickness=SPIRAL_LINE_THICK, alpha=0.40)

        if raw_tip is not None and self.framing.untrusted:
            # part-way out of frame: follow the angle, keep nothing
            self._p_tracker.update(raw_tip[0] * w, raw_tip[1] * h, now,
                                   trusted=False)
        elif raw_tip is not None and landmarks is not None:
            fx, fy = raw_tip[0] * w, raw_tip[1] * h
            self._p_samples.append((now, fx, fy))
            _, self._p_max_idx, on_arm, _ = self._p_tracker.update(fx, fy, now)
            step = self.practice_len / max(1, n - 1)
            self._p_arc_hist.append((now, self._p_max_idx * step))

            tip = self._fingertip_px(landmarks, c)
            if on_arm:
                c.dot(tip[0], tip[1], 8, "success")
            else:
                self._draw_resume(c, pts, self._p_max_idx, tip)
            self._update_practice_coach(now, on_arm)

            if self._p_max_idx >= int(END_PROGRESS_FRAC * (n - 1)):
                self._finish_practice(now)
                return
        else:
            self._p_tracker.reset_angle()
            self.coach.say(i18n.t("Show your hand to the camera"), PRI_HAND)

        if self._p_max_idx > 1:
            c.polyline(pts[:self._p_max_idx + 1], "brand", thickness=2,
                       alpha=0.9)

        if elapsed >= PRACTICE_MAX_S:
            self._finish_practice(now)
            return

        self._pace_gauge(c)
        # corrections go through the prompt channel; "good" lives on the gauge
        msg, status = self._p_coach
        if status == "warning":
            self.coach.say(i18n.t(msg),
                           PRI_LINE if msg == MSG_OFF_LINE else PRI_PACE)
        self._phase_panel(c, [(i18n.t("Practice - not scored yet"),
                               "warning")])
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       self._p_max_idx / max(1, n - 1), color="warning",
                       label=i18n.t("practice"))

    def _update_practice_coach(self, now: float, on_line: bool):
        """Refresh pace, smoothness and the coach line (throttled, so the
        advice holds still long enough to be read)."""
        self._p_on_line.append(on_line)
        if now - self._p_coach_t < LIVE_CHECK_EVERY:
            return
        self._p_coach_t = now
        self._p_speed = progress_speed(self._p_arc_hist, now)
        self._p_pace = pace_band(self._p_speed, self.target_speed)
        self._p_paces.append(self._p_pace)
        recent = [s for s in self._p_samples if s[0] >= now - LIVE_WINDOW_S]
        if len(recent) >= 20:
            self._p_smooth = live_smoothness_status(
                [s[0] for s in recent], [s[1] for s in recent],
                [s[2] for s in recent])
        self._p_coach = coach_message(self._p_pace, on_line, self._p_smooth)

    def _finish_practice(self, now: float):
        self.audio.play(self.done_wav)
        self._p_summary = practice_summary(
            now - self._p_start_t,
            recommended_time_s(self.practice_points, self.target_speed),
            self._p_paces, self._p_on_line)
        self.goto(PRACTICE_DONE, now)

    def screen_practice_done(self, c: Canvas, now: float):
        """Practice feedback only -- deliberately no score or band, so the
        practice run cannot be read as a result."""
        w, h = c.w, c.h
        s = self._p_summary
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        ph = 290
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph, alpha=0.9)
        c.text(w // 2, py + 32, i18n.t("Practice complete"), role="h2",
               anchor="mm", color="brand")

        gp, lp = s["good_pace_pct"], s["on_line_pct"]
        rows = [("Your time", f"{s['duration_s']:.0f} s"),
                ("Recommended time", f"{s['recommended_s']:.0f} s"),
                ("Time at a good pace", f"{gp:.0f} %" if gp is not None else "-"),
                ("Time near the line", f"{lp:.0f} %" if lp is not None else "-")]
        rx0 = px + theme.SPACE[4]
        rx1 = px + pw - theme.SPACE[4]
        for i, (label, val) in enumerate(rows):
            ry = py + 66 + i * 28
            c.text(rx0, ry, i18n.t(label), role="body", color="text-muted")
            c.text(rx1, ry, val, role="body_sb", anchor="ra", mono=True)
        c.text(w // 2, py + 196, i18n.t(s["takeaway"]), role="body_l",
               anchor="mm")

        inner = pw - 2 * theme.SPACE[4]
        bw = (inner - theme.SPACE[3]) // 2
        by = py + ph - 64
        bx1 = px + theme.SPACE[4]
        bx2 = bx1 + bw + theme.SPACE[3]
        again = c.button(bx1, by, bw, 48, i18n.t("Practice Again"),
                         variant="ghost", hovered=self.hover(bx1, by, bw, 48))
        go = c.button(bx2, by, bw, 48, i18n.t("Start Test"), variant="success",
                      hovered=self.hover(bx2, by, bw, 48), icon="check")
        c.disclaimer()
        if self.hit(again):
            self._start_practice(now)
        elif self.hit(go):
            self._start_prepare(now)

    def screen_prepare(self, c: Canvas, now: float, landmarks):
        w, h = c.w, c.h

        # faint reference spiral so the user sees where the trace will begin
        c.polyline(self.spiral_points, "text-muted",
                   thickness=SPIRAL_LINE_THICK, alpha=0.30)
        at_center, done = self._center_hold(c, now, landmarks)
        if done:
            self._start_recording(now)
            return

        self._phase_panel(c, [(i18n.t("Get ready to start"), "brand"),
                              (self._hold_message(at_center), "text-muted")])

    def screen_recording(self, c: Canvas, now: float, landmarks, raw_tip):
        w, h = c.w, c.h
        elapsed = now - self.recording_start
        end_idx = int(END_PROGRESS_FRAC * (SPIRAL_NUM_POINTS - 1))

        # faint full template -- a spatial reference, NOT a pacer (no moving dot)
        c.polyline(self.spiral_points, "text-muted",
                   thickness=SPIRAL_LINE_THICK, alpha=0.40)

        # fingertip tracking. Jitter is measured on the RAW fingertip; the
        # smoothed skeleton position is used only to draw the on-screen marker.
        # A hand partly out of frame jitters (core/framing.py): nothing is
        # recorded and progress does not move, but the fingertip is still
        # followed round, so a stretch the camera could not see (usually the
        # bottom arm) can simply be traced through and skipped.
        if raw_tip is not None and self.framing.untrusted:
            self.tracker.update(raw_tip[0] * c.w, raw_tip[1] * c.h, now,
                                trusted=False)
        elif raw_tip is not None:
            fx, fy = raw_tip[0] * c.w, raw_tip[1] * c.h
            # Progress follows the swept angle and only advances while the
            # fingertip is on its own arm, so drifting onto the next arm
            # freezes it instead of skipping a layer (core/spiral/progress.py).
            dev, self._max_reached_idx, on_arm, _ = self.tracker.update(
                fx, fy, now)
            self.frame_data.append({'t': now, 'fx': fx, 'fy': fy, 'dev': dev})

            self._update_live_status(now)
            dtip = self._fingertip_px(landmarks, c)
            if on_arm:
                c.dot(dtip[0], dtip[1], 8, self._live_status)
            else:
                self._draw_resume(c, self.spiral_points, self._max_reached_idx,
                                  dtip)

            if self._max_reached_idx >= end_idx:      # reached the rim → done
                self._finish(now)
                return
        else:
            self.tracker.reset_angle()  # re-sync the angle on re-acquisition
            self.coach.say(i18n.t("Show your hand to the camera"), PRI_HAND)

        # traced-so-far highlight follows the USER's progress, not a clock
        if self._max_reached_idx > 1:
            c.polyline(self.spiral_points[:self._max_reached_idx + 1], "brand",
                       thickness=2, alpha=0.9)

        if elapsed >= RECORDING_MAX:                  # safety cap
            self._finish(now)
            return

        # live HUD (top-left, under status bar)
        prog = self._max_reached_idx / max(1, SPIRAL_NUM_POINTS - 1)
        c.panel(theme.SAFE_MARGIN, 60, 200, 76, alpha=0.75, radius=12,
                shadow=False)
        # translated label, mono value: the digits stay tabular as they tick
        val_x = theme.SAFE_MARGIN + 186
        c.text(theme.SAFE_MARGIN + 14, 76, i18n.t("Time"), role="body_sb")
        c.text(val_x, 76, f"{elapsed:.0f} s", role="body_sb", anchor="ra",
               mono=True)
        c.text(theme.SAFE_MARGIN + 14, 104, i18n.t("Trace"), role="body_sb")
        c.text(val_x, 104, f"{prog * 100:.0f} %", role="body_sb", anchor="ra",
               mono=True)

        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       prog, color="success",
                       label=i18n.t("trace out to the edge"))

    def _update_live_status(self, now: float):
        """Recompute the rolling smoothness band from the recent raw fingertip
        (throttled) so the live fingertip colour tracks how the run scores."""
        if now - self._live_check_t < LIVE_CHECK_EVERY:
            return
        self._live_check_t = now
        recent = [fd for fd in self.frame_data if fd['t'] >= now - LIVE_WINDOW_S]
        if len(recent) < 20:
            return
        self._live_status = live_smoothness_status(
            [fd['t'] for fd in recent], [fd['fx'] for fd in recent],
            [fd['fy'] for fd in recent])

    def _finish(self, now: float):
        self.audio.play(self.done_wav)
        # Engine scores the RAW fingertip path (jitter channel); dev is the
        # secondary swept-angle accuracy series computed live.
        ts = [fd['t'] for fd in self.frame_data]
        xs = [fd['fx'] for fd in self.frame_data]
        ys = [fd['fy'] for fd in self.frame_data]
        dev = [fd['dev'] for fd in self.frame_data]
        self.results = compute_metrics(ts, xs, ys, dev, self.spiral_np,
                                       blackouts=self.framing.finish())
        if self.results["scoreable"]:
            self.countup = CountUp(self.results["smoothness_index"] or 0.0,
                                   time.time(), theme.DUR_SLOW)
        else:
            self.countup = None
        self._save_session()
        self.goto(COMPLETE, now)

    def _save_session(self):
        hand = max(self.hand_labels, key=self.hand_labels.get) \
            if self.hand_labels else None
        metrics = {k: v for k, v in self.results.items() if k != "reason"}
        if self.tracker is not None:
            # provenance, not part of the score: frames rejected as tracking
            # glitches, and frames spent off the arm being traced
            metrics["glitch_frames"] = self.tracker.glitch_frames
            metrics["off_arm_frames"] = self.tracker.off_arm_frames
        # frames with the hand part-way out of the picture, excluded above
        metrics["edge_clipped_pct"] = round(self.framing.clipped_pct, 1)
        metrics["edge_blackouts"] = len(self.framing.finish())
        t0 = self.recording_start or 0.0
        trace_s = (self.frame_data[-1]['t'] - t0) if self.frame_data else 0.0
        raw = {
            "samples": [[round(fd['t'] - t0, 3), round(fd['fx'], 1),
                         round(fd['fy'], 1), round(fd['dev'], 2)]
                        for fd in self.frame_data],
            # frame + radius make the template reproducible now that the
            # spiral is no longer centred with a fixed 0.4 radius
            "spiral": {"center": list(self.spiral_center),
                       "num_points": SPIRAL_NUM_POINTS, "turns": SPIRAL_TURNS,
                       "frame": list(self.frame_size),
                       "radius": round(self.spiral_b * SPIRAL_TURNS
                                       * 2 * math.pi, 2)},
        }
        try:
            self.saved_path = save_session(
                test="spiral", mode="air_spiral", hand=hand,
                duration_s=round(trace_s, 2),
                device={"camera_fps": round(self.fps, 1),
                        "resolution": "640x480", "app_version": APP_VERSION},
                metrics=metrics, raw=raw)
        except OSError as e:
            self.saved_path = None
            print(f"[WARN] Could not save session: {e}")

    def screen_complete(self, c: Canvas, now: float):
        w, h = c.w, c.h
        r = self.results
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        bh = 42

        # ── measure content first, then size the panel to fit (button never
        #    overlaps the metric rows / notes) ──
        if r["scoreable"]:
            tf = r.get("tremor_power_frac")
            th = r.get("tremor_dominant_hz")
            rows = [("SPARC", f"{r['sparc']:.2f}"
                     if r['sparc'] is not None else "-"),
                    ("Velocity CV", f"{r['vel_cv_pct']:.1f} %"
                     if r['vel_cv_pct'] is not None else "-"),
                    ("Norm. jerk", f"{r['norm_jerk']:.2e}"
                     if r['norm_jerk'] is not None else "-"),
                    ("Tremor power*", f"{tf * 100:.0f} %" if tf is not None else "-"),
                    ("Tremor freq*", f"{th:.1f} Hz" if th else "-"),
                    ("Completion", f"{r['completion_pct']:.0f} %"),
                    ("Mean speed", f"{r['vel_mean_px_s']:.0f} px/s"
                     if r['vel_mean_px_s'] is not None else "-"),
                    ("Data frames", f"{len(self.frame_data)}")]
            rows = rows[:8]
            nlines = (len(rows) + 1) // 2
            note_off = 190 + nlines * 24 + 6
            caveat_off = note_off + 18
            saved_off = caveat_off + 18
            btn_off = (saved_off if self.saved_path else caveat_off) + 24
        else:
            reason = r.get("reason") or "Something went wrong - please try again."
            # i18n.wrap, not split(): Chinese has no spaces to break on.
            lines = i18n.wrap(i18n.t(reason), 48)[:3]
            btn_off = 108 + len(lines) * 26 + 12
        ph = btn_off + bh + 14

        px, py = (w - pw) // 2, max(56, (h - ph) // 2)
        c.panel(px, py, pw, ph, alpha=0.9)
        c.text(w // 2, py + 30, i18n.t("Spiral Tracing - Results"), role="h2",
               anchor="mm")

        if r["scoreable"]:
            status = r["status"]
            idx_val = self.countup.value(now) if self.countup \
                else (r["smoothness_index"] or 0.0)
            c._dirty = True
            c.draw.text((w // 2, py + 90), f"{idx_val:.0f}",
                        font=get_font("mono", 56),
                        fill=theme.rgba(status, 1.0), anchor="mm")
            c.text(w // 2, py + 126,
                   i18n.t("Smoothness index (0-100, higher = smoother)"),
                   role="caption", color="text-muted", anchor="mm")
            c.badge(w // 2, py + 140, i18n.t(r["label"]), status)
            col_w = (pw - 3 * theme.SPACE[4]) // 2
            for i, (label, val) in enumerate(rows):
                rx = px + theme.SPACE[4] + (i % 2) * (col_w + theme.SPACE[4])
                ry = py + 190 + (i // 2) * 24
                c.text(rx, ry, i18n.t(label), role="caption",
                       color="text-muted")
                c.text(rx + col_w, ry, val, role="caption", anchor="ra", mono=True)
            c.text(w // 2, py + note_off,
                   i18n.t("Smoothness via SPARC. Provisional bands - "
                          "screening, not diagnosis."),
                   role="caption", color="text-muted", anchor="mm")
            c.text(w // 2, py + caveat_off,
                   i18n.t("* tremor metrics are coarse at this frame rate."),
                   role="caption", color="text-muted", anchor="mm")
            if self.saved_path:
                c.text(w // 2, py + saved_off,
                       i18n.t("Saved: results/{name}",
                              name=self.saved_path.name),
                       role="caption", color="text-muted", anchor="mm")
        else:
            c.badge(w // 2, py + 52, i18n.t("Couldn't score this run"),
                    "warning")
            for i, line in enumerate(lines):
                c.text(w // 2, py + 108 + i * 26, line, role="body",
                       color="text-muted", anchor="mm")

        bw = 160
        bx, by = w // 2 - bw // 2, py + btn_off
        b = c.button(bx, by, bw, bh, i18n.t("Try Again"), variant="primary",
                     hovered=self.hover(bx, by, bw, bh))
        c.disclaimer()
        if self.hit(b):
            self.reset_run()
            self.goto(IDLE, now)

    # ── main loop ─────────────────────────────────────────────────────────
    def run(self):
        win = "Spiral Tracing Test  |  Q or window ✕ to quit"
        window_ready = False
        while self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)
            if not window_ready:
                create_display_window(win, frame.shape[1], frame.shape[0])
                cv2.setMouseCallback(win, self.on_mouse)
                window_ready = True
            now = time.time()
            if self._last_frame_t is not None:
                dt = max(1e-3, now - self._last_frame_t)
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)
            self._last_frame_t = now

            fh, fw = frame.shape[:2]
            if not self.spiral_ready:
                self.spiral_points, self.practice_points, self.spiral_center, \
                    self.spiral_b = scale_spiral_to_frame(fw, fh)
                self.frame_size = (fw, fh)
                self.hang_budget = (1.0 - framing.EDGE_CLIP
                                    - max(p[1] for p in self.spiral_points) / fh)
                self.spiral_np = np.array(self.spiral_points, dtype=np.float32)
                self.practice_len = arc_length(self.practice_points)
                self.target_speed = target_speed_px_s(self.spiral_points)
                self.spiral_ready = True

            landmarks, raw_tip, self._raw_pts = self.detect_hand(frame, now)
            self.framing.update(self._raw_pts, now)
            if landmarks is not None:
                draw_hand_skeleton(frame, landmarks, HAND_CONNECTIONS)

            c = Canvas(frame)
            c.status_bar(framing_chips(self.framing, landmarks, self.fps),
                         i18n.t("Spiral Tracing"))

            if self.state == IDLE:
                self.screen_idle(c, now)
            elif self.state == INSTRUCTION:
                self.screen_instruction(c, now)
            elif self.state == COUNTDOWN:
                self.screen_countdown(c, now)
            elif self.state == PRACTICE:
                self.screen_practice(c, now, landmarks, raw_tip)
            elif self.state == PRACTICE_DONE:
                self.screen_practice_done(c, now)
            elif self.state == PREPARE:
                self.screen_prepare(c, now, landmarks)
            elif self.state == RECORDING:
                self.screen_recording(c, now, landmarks, raw_tip)
            elif self.state == COMPLETE:
                self.screen_complete(c, now)

            if self.state in (PRACTICE, PREPARE, RECORDING):
                draw_framing(c, self.framing, self._raw_pts, self.coach,
                             tracing=True)
            self.coach.render(c, now)

            cv2.imshow(win, c.compose())
            self.click = None
            if cv2.waitKey(5) & 0xFF == ord("q"):
                break
            if window_closed(win):
                break

        self.cap.release()
        cv2.destroyAllWindows()
        self.landmarker.close()
        self.audio.close()
        print("\n[INFO] Spiral tracing test closed.")


def main():
    # banner already printed by the splash, above the heavy imports
    source = select_camera_source()
    print("[INFO] Opening camera and loading the hand model - a few seconds...")
    cap = open_capture(source, fps=60)
    if cap is None:
        print("[ERROR] Could not open camera.")
        pause_before_exit()
        sys.exit(1)
    ensure_orientation(cap)   # once per camera: undo its own mirroring
    App(cap).run()


if __name__ == "__main__":
    main()
