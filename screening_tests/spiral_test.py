"""
Spiral Tracing Test for Early Alzheimer's Screening
=====================================================
Self-paced Archimedes-spiral trace with the index fingertip in the air. There is
no dot to chase: the user traces the spiral outward at their own pace and the run
is scored on the *quality of the movement* (smoothness / jitter), matching the
clinical pen test. See docs/SPIRAL_TEST_PLAN.md.

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

import cv2
import mediapipe as mp
import numpy as np

from core.hand_utils import (HAND_CONNECTIONS, make_landmark_filters,
                             smooth_landmarks, preprocess_for_mediapipe)
from core.camera import (select_camera_source, open_capture,
                         create_display_window, window_closed)
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.ui import theme
from core.ui.anim import CountUp, ease_out_cubic, fade_in_out, lerp
from core.ui.components import Canvas, draw_hand_skeleton, get_font
from core.spiral.geometry import (scale_spiral_to_frame, nearest_spiral_point,
                                 SPIRAL_TURNS, SPIRAL_NUM_POINTS)
from core.spiral.metrics import compute_metrics, live_smoothness_status

APP_VERSION = "0.3.0"
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

# ── Test Configuration ────────────────────────────────────────────────────
RECORDING_MAX      = 60       # safety cap (s); the run ends on completion first
WARMUP_DURATION    = 8        # unscored practice seconds
COUNTDOWN_FROM     = 3

# Spiral geometry (SPIRAL_TURNS / SPIRAL_NUM_POINTS imported from the engine)
SPIRAL_LINE_THICK  = 3

# Marker used for the warmup pacing dot and the center start dot (not scored).
GUIDE_DOT_RADIUS   = 12

# Self-paced end condition: the trace finishes when the user's swept progress
# reaches this fraction of the spiral (they've traced out to the rim).
END_PROGRESS_FRAC  = 0.985

# Preparation phase: fingertip must reach the spiral center to start
CENTER_THRESHOLD   = 40       # px from center that counts as "on the start dot"
PREPARE_HOLD       = 0.6      # seconds held at center before scoring begins

# Fingertip proximity thresholds (pixels) -- warmup coaching colour only
FINGERTIP_IDX      = 8        # MediaPipe landmark: index fingertip
CLOSE_THRESHOLD    = 30       # "on track"
FAR_THRESHOLD      = 60       # "drifting"

# Radius (px) below which the fingertip is too near the spiral center for its
# angle about the center to be meaningful -- don't advance the swept angle there.
ANGLE_MIN_RADIUS   = 18.0

# Live-smoothness coaching: recompute the fingertip colour band from a rolling
# window this often (s) over this many recent seconds of the raw fingertip path.
LIVE_CHECK_EVERY   = 0.4
LIVE_WINDOW_S      = 4.0

# ── States ────────────────────────────────────────────────────────────────
IDLE, INSTRUCTION, COUNTDOWN, WARMUP, PREPARE, RECORDING, COMPLETE = (
    "idle", "instruction", "countdown", "warmup", "prepare", "recording",
    "complete")

INSTRUCTIONS = [
    "Using your preferred hand, trace the spiral outward",
    "from the center to the edge - at your own",
    "comfortable pace. There is no dot to chase.",
    "Just move as smoothly and steadily as you can.",
]


# ── Warmup proximity colour (spatial guide only, not scored) ────────────────

def proximity_status(dev):
    if dev < CLOSE_THRESHOLD:
        return "success"
    if dev < FAR_THRESHOLD:
        return "warning"
    return "danger"


class Toasts:
    """One coach message at a time; base-duration fade in/out (§6.2)."""

    def __init__(self):
        self.msg = ""
        self.status = "info"
        self.t0 = -1e9
        self.hold = 2.0

    def show(self, msg: str, status: str = "info", hold: float = 2.0,
             now: float | None = None):
        now = time.time() if now is None else now
        if msg == self.msg and now - self.t0 < self.hold + 0.4:
            return
        self.msg, self.status, self.t0, self.hold = msg, status, now, hold

    def render(self, canvas: Canvas, now: float):
        a = fade_in_out(self.t0, now, theme.DUR_BASE, self.hold)
        canvas.toast(self.msg, self.status, a)


class App:
    def __init__(self, cap):
        self.cap = cap
        # Ask for 60 fps (MJPG) so the raw fingertip resolves more of the tremor
        # band; the loop measures and reports the actual rate and falls back to
        # whatever the camera delivers (docs/SPIRAL_TEST_PLAN.md §3.3).
        try:
            self.cap.set(cv2.CAP_PROP_FOURCC,
                         cv2.VideoWriter_fourcc(*"MJPG"))
            self.cap.set(cv2.CAP_PROP_FPS, 60)
        except Exception:                    # noqa: BLE001 - camera may ignore it
            pass
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.55,
        )
        self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.audio = AudioWorker()
        self.start_wav = build_tone(880, 100)
        self.tick_wav = build_tone(660, 60)
        self.done_wav = build_tone(523, 180)

        self.state = IDLE
        self.toasts = Toasts()
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
        self.warmup_points: list = []
        self.warmup_np = None

        self.frame_data: list[dict] = []
        self._max_reached_idx = 0        # user's furthest swept progress (index)
        self._angle_cum = 0.0            # fingertip angle swept about center
        self._prev_angle = None          # last raw angle, for unwrapping
        self._center_hold_start = None   # when the fingertip reached center
        self._live_status = "info"       # rolling smoothness band (fingertip hue)
        self._live_check_t = 0.0         # last live-smoothness recompute time
        self.hand_labels: dict[str, int] = {}

        self.t_state = time.time()
        self.recording_start = None
        self.results = None
        self.saved_path = None
        self.countup: CountUp | None = None

    def goto(self, state: str, now: float):
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
        """Return (smoothed_landmarks, raw_fingertip) or (None, None). The raw
        fingertip is the *unfiltered* index-tip (x, y) in normalized [0,1] space
        -- jitter measurement runs on it because the One-Euro smoothing used for
        display would erase the signal (docs/SPIRAL_TEST_PLAN.md §3.1)."""
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        if not result.hand_landmarks:
            return None, None
        # Frame is flipped to selfie view, matching MediaPipe's handedness
        # convention -- the reported label IS the user's true hand.
        if result.handedness:
            label = result.handedness[0][0].category_name.lower()
            self.hand_labels[label] = self.hand_labels.get(label, 0) + 1
        raw = result.hand_landmarks[0][FINGERTIP_IDX]
        raw_tip = (raw.x, raw.y)
        smoothed = smooth_landmarks(result.hand_landmarks[0],
                                    self.lm_filters_x, self.lm_filters_y, now)
        return smoothed, raw_tip

    def _fingertip_px(self, landmarks, c: Canvas):
        return (int(landmarks[FINGERTIP_IDX][0] * c.w),
                int(landmarks[FINGERTIP_IDX][1] * c.h))

    def _draw_proximity(self, c: Canvas, tip, sp_np):
        """Connector + fingertip marker colored by proximity to the spiral
        template. Returns deviation (px) -- the fingertip's distance to the
        nearest point on the drawn spiral, the literature-standard accuracy
        metric for Archimedes-spiral tracing."""
        _, dev, nx, ny = nearest_spiral_point(tip[0], tip[1], sp_np)
        status = proximity_status(dev)
        c.polyline([tip, (nx, ny)], status, thickness=1, alpha=0.8)
        c.dot(tip[0], tip[1], 8, status)
        return dev

    @staticmethod
    def _pct_of_radius(dev_px, b):
        """Express a radial error as a percentage of the spiral's outer radius
        (r = b*theta_max), making it dimensionless -- independent of camera
        resolution and on-screen spiral size, and reproducible across setups."""
        radius = b * SPIRAL_TURNS * 2 * math.pi
        return (dev_px / radius * 100.0) if radius > 1e-6 else 0.0

    def _radial_deviation(self, tip, cx, cy, b):
        """Deviation of the fingertip from the ideal Archimedes spiral, measured
        radially at the angle the fingertip has swept about the center (the
        spiral "unwound" to r = b*theta). Correspondence is by swept angle, not
        nearest Euclidean point -- so sitting on the wrong arm, or weaving among
        the tightly spaced inner arms, produces a large error instead of hiding
        inside the ~one-gap tolerance of a nearest-point search.

        Returned as a percentage of the spiral's outer radius (see
        _pct_of_radius), so the scored value and its thresholds are dimensionless
        and reproducible rather than tied to this camera's pixel scale."""
        dx = tip[0] - cx
        dy = cy - tip[1]                 # screen y is inverted vs. spiral math y
        r  = math.hypot(dx, dy)
        if r < ANGLE_MIN_RADIUS:         # too near center: angle is unstable
            self._prev_angle = None
            return self._pct_of_radius(abs(r - b * max(self._angle_cum, 0.0)), b)
        ang = math.atan2(dy, dx)
        if self._prev_angle is None and self._angle_cum == 0.0 and b > 1e-6:
            # First exit from the center dead-zone: seed the swept angle to the
            # ideal theta for this radius rather than losing the angle swept
            # below ANGLE_MIN_RADIUS. Near the center all arms coincide, so this
            # is unambiguous -- and it stops honest traces reading a phantom
            # ~ANGLE_MIN_RADIUS of deviation. (Re-acquisition after a hand drop
            # keeps its progress, since _angle_cum is already non-zero there.)
            self._angle_cum = r / b
        elif self._prev_angle is not None:
            d = ang - self._prev_angle
            if d > math.pi:
                d -= 2 * math.pi
            elif d < -math.pi:
                d += 2 * math.pi
            self._angle_cum += d
        self._prev_angle = ang
        return self._pct_of_radius(abs(r - b * max(self._angle_cum, 0.0)), b)

    def _guide_dot(self, c: Canvas, gx, gy):
        c.dot(gx, gy, GUIDE_DOT_RADIUS, "warning", outline="text", outline_w=2)

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 118, 212
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, "Spiral Tracing Test", role="h1", anchor="mm")
        c.text(w // 2, py + 74, "Measures movement smoothness and jitter -",
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 98, "markers studied in cognitive decline.",
               role="body", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        bx, by = px + theme.SPACE[4], py + 132
        b = c.button(bx, by, bw, 48, "Start Test", variant="primary",
                     hovered=self.hover(bx, by, bw, 48), icon="play")
        c.disclaimer()
        if self.hit(b):
            self.reset_run()
            self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        w, h = c.w, c.h
        lines = INSTRUCTIONS
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 34, "Your Task", role="h2", anchor="mm",
               color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        c.text(w // 2, py + 84 + len(lines) * 30,
               f"{WARMUP_DURATION}s practice, then trace the spiral once at your pace.",
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, "I'm Ready", variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.hit(b):
            self.goto(COUNTDOWN, now)

    def screen_countdown(self, c: Canvas, now: float):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining <= 0:
            self._start_warmup(now)
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
        c.text(w // 2, h // 2 - 100, "Get ready...", role="h2", anchor="mm",
               color="text-muted")
        if int(elapsed) != getattr(self, "_last_tick", -1):
            self._last_tick = int(elapsed)
            self.audio.play(self.tick_wav)

    def _start_warmup(self, now: float):
        self.goto(WARMUP, now)

    def _start_prepare(self, now: float):
        self._center_hold_start = None
        self.goto(PREPARE, now)

    def _start_recording(self, now: float):
        self.recording_start = now
        self.frame_data = []
        self._max_reached_idx = 0
        self._angle_cum = 0.0            # start of trace = zero swept angle
        self._prev_angle = None
        self._live_status = "info"
        self._live_check_t = now
        # fresh filters so warm-up smoothing lag doesn't bleed into display
        new_x, new_y = make_landmark_filters()
        self.lm_filters_x[:] = new_x
        self.lm_filters_y[:] = new_y
        self.audio.play(self.start_wav)
        self.goto(RECORDING, now)

    def screen_warmup(self, c: Canvas, now: float, landmarks):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = WARMUP_DURATION - elapsed
        if remaining <= 0:
            self._start_prepare(now)
            return

        c.polyline(self.warmup_points, "text-muted", thickness=3, alpha=0.4)
        wu_idx = int((elapsed / WARMUP_DURATION) * len(self.warmup_points)) \
            % len(self.warmup_points)
        gx, gy = self.warmup_points[wu_idx]
        self._guide_dot(c, gx, gy)

        if landmarks is not None:
            self._draw_proximity(c, self._fingertip_px(landmarks, c), self.warmup_np)

        pw = min(480, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, h - 160
        c.panel(px, py, pw, 88)
        c.text(w // 2, py + 26, "Practice - not scored yet", role="body_l",
               anchor="mm", color="warning")
        c.text(w // 2, py + 52, f"Scored test begins in {remaining:.0f} s",
               role="body", color="text-muted", anchor="mm")
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       elapsed / WARMUP_DURATION, color="warning",
                       label="warm-up")
        if landmarks is None:
            self.toasts.show("Follow the dot around the circle", "warning", now=now)

    def screen_prepare(self, c: Canvas, now: float, landmarks):
        w, h = c.w, c.h
        cx, cy = self.spiral_center

        # faint reference spiral so the user sees where the trace will begin
        c.polyline(self.spiral_points, "text-muted",
                   thickness=SPIRAL_LINE_THICK, alpha=0.30)
        # start target: threshold zone + the start dot at the spiral center
        c.ring(cx, cy, CENTER_THRESHOLD, "info", thickness=2, alpha=0.6)
        self._guide_dot(c, cx, cy)

        at_center = False
        if landmarks is not None:
            tip = self._fingertip_px(landmarks, c)
            dist = math.hypot(tip[0] - cx, tip[1] - cy)
            at_center = dist < CENTER_THRESHOLD
            status = "success" if at_center else "info"
            c.polyline([tip, (cx, cy)], status, thickness=1, alpha=0.7)
            c.dot(tip[0], tip[1], 8, status)

        held = 0.0
        if at_center:
            if self._center_hold_start is None:
                self._center_hold_start = now
            held = now - self._center_hold_start
            if held >= PREPARE_HOLD:
                self._start_recording(now)
                return
            # progress ring closes around the target as they hold steady
            c.ring(cx, cy, CENTER_THRESHOLD + 8, "success", thickness=4,
                   sweep_deg=360 * (held / PREPARE_HOLD)
                   if not theme.REDUCED_MOTION else 360)
        else:
            self._center_hold_start = None

        pw = min(480, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, h - 150
        c.panel(px, py, pw, 78)
        c.text(w // 2, py + 26, "Get ready to start", role="body_l",
               anchor="mm", color="brand")
        msg = ("Hold steady..." if at_center
               else "Move your fingertip onto the center dot to begin.")
        c.text(w // 2, py + 52, msg, role="body", color="text-muted", anchor="mm")
        if landmarks is None:
            self.toasts.show("Show your hand, then touch the center dot",
                             "warning", now=now)

    def screen_recording(self, c: Canvas, now: float, landmarks, raw_tip):
        w, h = c.w, c.h
        elapsed = now - self.recording_start
        end_idx = int(END_PROGRESS_FRAC * (SPIRAL_NUM_POINTS - 1))

        # faint full template -- a spatial reference, NOT a pacer (no moving dot)
        c.polyline(self.spiral_points, "text-muted",
                   thickness=SPIRAL_LINE_THICK, alpha=0.40)

        # fingertip tracking. Jitter is measured on the RAW fingertip; the
        # smoothed skeleton position is used only to draw the on-screen marker.
        if raw_tip is not None:
            cx, cy = self.spiral_center
            fx, fy = raw_tip[0] * c.w, raw_tip[1] * c.h
            dev = self._radial_deviation((fx, fy), cx, cy, self.spiral_b)
            self.frame_data.append({'t': now, 'fx': fx, 'fy': fy, 'dev': dev})

            # user-driven progress: the furthest template index reached
            idx, _, _, _ = nearest_spiral_point(fx, fy, self.spiral_np)
            self._max_reached_idx = max(self._max_reached_idx, idx)

            self._update_live_status(now)
            dtip = self._fingertip_px(landmarks, c)
            c.dot(dtip[0], dtip[1], 8, self._live_status)

            if self._max_reached_idx >= end_idx:      # reached the rim → done
                self._finish(now)
                return
        else:
            self._prev_angle = None    # don't fabricate a jump on re-acquisition
            self.toasts.show("Keep your hand in the frame", "warning", now=now)

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
        c.text(theme.SAFE_MARGIN + 14, 76, f"Time   {elapsed:.0f} s",
               role="body_sb", mono=True)
        c.text(theme.SAFE_MARGIN + 14, 104, f"Trace  {prog * 100:.0f} %",
               role="body_sb", mono=True)

        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       prog, color="success", label="trace out to the edge")

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
        self.results = compute_metrics(ts, xs, ys, dev, self.spiral_np)
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
        t0 = self.recording_start or 0.0
        trace_s = (self.frame_data[-1]['t'] - t0) if self.frame_data else 0.0
        raw = {
            "samples": [[round(fd['t'] - t0, 3), round(fd['fx'], 1),
                         round(fd['fy'], 1), round(fd['dev'], 2)]
                        for fd in self.frame_data],
            "spiral": {"center": list(self.spiral_center),
                       "num_points": SPIRAL_NUM_POINTS, "turns": SPIRAL_TURNS},
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
            words, lines, cur = reason.split(), [], ""
            for word in words:
                if len(cur) + len(word) + 1 > 48:
                    lines.append(cur)
                    cur = word
                else:
                    cur = f"{cur} {word}".strip()
            lines.append(cur)
            lines = lines[:3]
            btn_off = 108 + len(lines) * 26 + 12
        ph = btn_off + bh + 14

        px, py = (w - pw) // 2, max(56, (h - ph) // 2)
        c.panel(px, py, pw, ph, alpha=0.9)
        c.text(w // 2, py + 30, "Spiral Tracing - Results", role="h2",
               anchor="mm")

        if r["scoreable"]:
            status = r["status"]
            idx_val = self.countup.value(now) if self.countup \
                else (r["smoothness_index"] or 0.0)
            c._dirty = True
            c.draw.text((w // 2, py + 90), f"{idx_val:.0f}",
                        font=get_font("mono", 56),
                        fill=theme.rgba(status, 1.0), anchor="mm")
            c.text(w // 2, py + 126, "Smoothness index (0-100, higher = smoother)",
                   role="caption", color="text-muted", anchor="mm")
            c.badge(w // 2, py + 140, r["label"], status)
            col_w = (pw - 3 * theme.SPACE[4]) // 2
            for i, (label, val) in enumerate(rows):
                rx = px + theme.SPACE[4] + (i % 2) * (col_w + theme.SPACE[4])
                ry = py + 190 + (i // 2) * 24
                c.text(rx, ry, label, role="caption", color="text-muted")
                c.text(rx + col_w, ry, val, role="caption", anchor="ra", mono=True)
            c.text(w // 2, py + note_off,
                   "Smoothness via SPARC. Provisional bands - screening, not "
                   "diagnosis.",
                   role="caption", color="text-muted", anchor="mm")
            c.text(w // 2, py + caveat_off,
                   "* tremor metrics are coarse at this frame rate.",
                   role="caption", color="text-muted", anchor="mm")
            if self.saved_path:
                c.text(w // 2, py + saved_off,
                       f"Saved: results/{self.saved_path.name}",
                       role="caption", color="text-muted", anchor="mm")
        else:
            c.badge(w // 2, py + 52, "Couldn't score this run", "warning")
            for i, line in enumerate(lines):
                c.text(w // 2, py + 108 + i * 26, line, role="body",
                       color="text-muted", anchor="mm")

        bw = 160
        bx, by = w // 2 - bw // 2, py + btn_off
        b = c.button(bx, by, bw, bh, "Try Again", variant="primary",
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
                self.spiral_points, self.warmup_points, self.spiral_center, \
                    self.spiral_b = scale_spiral_to_frame(fw, fh)
                self.spiral_np = np.array(self.spiral_points, dtype=np.float32)
                self.warmup_np = np.array(self.warmup_points, dtype=np.float32)
                self.spiral_ready = True

            landmarks, raw_tip = self.detect_hand(frame, now)
            if landmarks is not None:
                draw_hand_skeleton(frame, landmarks, HAND_CONNECTIONS)

            c = Canvas(frame)
            chips = [("Hand detected", "success") if landmarks is not None
                     else ("Show your hand", "warning")]
            if self.fps < 24:
                chips.append((f"{self.fps:.0f} fps", "warning"))
            c.status_bar(chips, "Spiral Tracing")

            if self.state == IDLE:
                self.screen_idle(c, now)
            elif self.state == INSTRUCTION:
                self.screen_instruction(c, now)
            elif self.state == COUNTDOWN:
                self.screen_countdown(c, now)
            elif self.state == WARMUP:
                self.screen_warmup(c, now, landmarks)
            elif self.state == PREPARE:
                self.screen_prepare(c, now, landmarks)
            elif self.state == RECORDING:
                self.screen_recording(c, now, landmarks, raw_tip)
            elif self.state == COMPLETE:
                self.screen_complete(c, now)

            self.toasts.render(c, now)

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
    print("=" * 52)
    print("  Spiral Tracing Test")
    print("  Click 'Start Test' in the camera window.  Q to quit.")
    print("=" * 52)
    source = select_camera_source()
    cap = open_capture(source)
    if cap is None:
        print("[ERROR] Could not open camera.")
        sys.exit(1)
    App(cap).run()


if __name__ == "__main__":
    main()
