"""
Finger Tapping Test
===================
Camera-based finger-tapping screening with two paradigms (core/tapping/modes.py):

  Big & Fast  -- self-paced maximum-speed tapping, 10 s (primary; the
                 literature-aligned paradigm: TapTalk, Suzumura, Roalf).
  Paced Rhythm -- metronome-synced tapping at 1 Hz, 30 s (rhythm + beat sync).

Headline biomarker: CV% of inter-tap intervals (scale-invariant IIV), plus
frequency, amplitude variability, speed decrement, and (paced) sync SD.

Flow: mode select -> instructions -> guided calibration (per-session adaptive
tap threshold) -> countdown -> [warm-up] -> recording -> results (auto-saved
to results/ as JSON + CSV index).

This file is the run loop + rendering only; detection, metrics, modes, audio,
persistence, and UI components live in core/ (see FINGER_TAPPING_REVISION_PLAN.md).

Run:  python screening_tests/finger_tapping.py     Quit: press 'q'
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))  # keep first: hand_utils import path

import cv2
import mediapipe as mp

from core.hand_utils import (HAND_CONNECTIONS, make_landmark_filters,
                             smooth_landmarks, preprocess_for_mediapipe)
from core.camera import (select_camera_source, open_capture,
                         create_display_window, window_closed)
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.tapping.detector import Calibrator, TapDetector, thumb_index_distance
from core.tapping.metrics import compute_metrics
from core.tapping.modes import MODES, DEFAULT_MODE, TapMode
from core.ui import theme
from core.ui.anim import CountUp, ease_out_cubic, fade_in_out, lerp
from core.ui.components import Canvas, draw_hand_skeleton, get_font

APP_VERSION = "0.2.0"
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

COUNTDOWN_FROM = 3
AUDIO_LEAD = 0.200          # fire beeps early to offset OS audio latency
EMA_ALPHA_PACED = 0.4
EMA_ALPHA_FAST = 0.6        # less smoothing lag for max-speed tapping

# ── States ─────────────────────────────────────────────────────────────────
IDLE, INSTRUCTION, CALIBRATION, COUNTDOWN, WARMUP, RECORDING, COMPLETE = (
    "idle", "instruction", "calibration", "countdown", "warmup", "recording",
    "complete")


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
        # don't restart an identical, still-visible toast
        if msg == self.msg and now - self.t0 < self.hold + 0.4:
            return
        self.msg, self.status, self.t0, self.hold = msg, status, now, hold

    def render(self, canvas: Canvas, now: float):
        a = fade_in_out(self.t0, now, theme.DUR_BASE, self.hold)
        canvas.toast(self.msg, self.status, a)


class App:
    def __init__(self, cap):
        self.cap = cap
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
        self.beep_wav = build_tone(880, 100)
        self.tick_wav = build_tone(660, 60)
        self.done_wav = build_tone(523, 180)

        self.mode: TapMode = MODES[DEFAULT_MODE]
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
        self.calibrator = Calibrator()
        self.detector: TapDetector | None = None
        self.d_closed = self.d_open = None
        self.t_state = time.time()          # entry time of current state
        self.recording_start = None
        self.grid_t0 = None                 # metronome absolute grid origin (A6)
        self.next_beat_k = 0
        self.beat_times: list[float] = []
        self.last_beat_t = -1e9
        self.ripples: list[tuple[float, int, int]] = []
        self.glow_t = -1e9
        self.hand_frames = 0
        self.visible_frames = 0
        self.hand_labels: dict[str, int] = {}
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

    # ── metronome on an absolute beat grid (fixes drift, audit A6) ────────
    def run_metronome(self, now: float):
        if not self.mode.paced or self.grid_t0 is None:
            return
        interval = self.mode.interval_s
        k_due = int((now + AUDIO_LEAD - self.grid_t0) // interval)
        if k_due >= self.next_beat_k:
            beat_t = self.grid_t0 + k_due * interval   # fire only the latest due
            self.audio.play(self.beep_wav)
            self.last_beat_t = beat_t
            if self.state == RECORDING and beat_t >= self.recording_start:
                self.beat_times.append(beat_t)
            self.next_beat_k = k_due + 1

    # ── per-frame pipeline ────────────────────────────────────────────────
    def detect_hand(self, frame, now: float):
        # Adaptive load shedding (audit A13): skip CLAHE+sharpen when slow.
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        if not result.hand_landmarks:
            return None
        # Frame is flipped to selfie view, which matches MediaPipe's handedness
        # convention -- the reported label IS the user's true hand (audit A15).
        if result.handedness:
            label = result.handedness[0][0].category_name.lower()
            self.hand_labels[label] = self.hand_labels.get(label, 0) + 1
        return smooth_landmarks(result.hand_landmarks[0],
                                self.lm_filters_x, self.lm_filters_y, now)

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 130, 236
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, "Finger Tapping Test", role="h1", anchor="mm")
        c.text(w // 2, py + 74, "Measures motor rhythm and speed -", role="body",
               color="text-muted", anchor="mm")
        c.text(w // 2, py + 98, "markers studied in early cognitive decline.",
               role="body", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        b1 = c.button(px + theme.SPACE[4], py + 128, bw, 48,
                      f"Start {MODES['big_and_fast'].title} ({MODES['big_and_fast'].duration_s:.0f} s)",
                      variant="primary",
                      hovered=self.hover(px + theme.SPACE[4], py + 128, bw, 48),
                      icon="play")
        b2 = c.button(px + theme.SPACE[4], py + 184, bw, 40,
                      f"{MODES['paced'].title} ({MODES['paced'].duration_s:.0f} s, with metronome)",
                      variant="ghost",
                      hovered=self.hover(px + theme.SPACE[4], py + 184, bw, 40))
        c.disclaimer()
        if self.hit(b1):
            self.mode = MODES["big_and_fast"]
            self.goto(INSTRUCTION, now)
        elif self.hit(b2):
            self.mode = MODES["paced"]
            self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        w, h = c.w, c.h
        lines = self.mode.instructions
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 34, f"{self.mode.title} - Your Task", role="h2",
               anchor="mm", color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        c.text(w // 2, py + 84 + len(lines) * 30,
               "Next: a quick warm-up so we can calibrate to your hand.",
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, "I'm Ready", variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.hit(b):
            self.reset_run()
            self.goto(CALIBRATION, now)

    def screen_calibration(self, c: Canvas, now: float, landmarks, d):
        w, h = c.w, c.h
        if landmarks is not None and d is not None:
            self.calibrator.update(now, d)
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h - 190, 118
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 28, "Warm-up: open and close your hand",
               role="body_l", anchor="mm")
        c.text(w // 2, py + 54, "Touch index finger to thumb, then open wide - a few times.",
               role="caption", color="text-muted", anchor="mm")
        c.progress_bar(px + theme.SPACE[4], py + 84, pw - 2 * theme.SPACE[4],
                       self.calibrator.progress, color="warning",
                       label=f"{int(self.calibrator.progress * 100)} %")
        if landmarks is None:
            self.toasts.show("Show your hand to the camera", "warning", now=now)
        elif self.calibrator.timed_out(now) and not self.calibrator.done:
            self.toasts.show("Having trouble? Move a little closer to the camera",
                             "info", hold=3.0, now=now)
        if self.calibrator.done:
            self.d_closed, self.d_open = self.calibrator.result()
            self.goto(COUNTDOWN, now)

    def screen_countdown(self, c: Canvas, now: float):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining <= 0:
            self._start_test(now)
            return
        frac_sec = elapsed - int(elapsed)          # 0→1 inside current second
        # ring sweeps 360→0 across the second (§6.2)
        c.ring(w // 2, h // 2, 64, "brand", thickness=4,
               sweep_deg=360 * (1 - frac_sec) if not theme.REDUCED_MOTION else 360)
        # number scale-pop 1.3→1.0 over 300 ms
        scale = lerp(1.3, 1.0, ease_out_cubic(frac_sec / 0.3)) \
            if not theme.REDUCED_MOTION else 1.0
        px_size = int(64 * scale)
        c._dirty = True
        c.draw.text((w // 2, h // 2), str(remaining),
                    font=get_font("bold", px_size),
                    fill=theme.rgba("text", 1.0), anchor="mm")
        c.text(w // 2, h // 2 - 100, "Get ready...", role="h2", anchor="mm",
               color="text-muted")
        if int(elapsed) != getattr(self, "_last_tick", -1):
            self._last_tick = int(elapsed)
            self.audio.play(self.tick_wav)

    def _start_test(self, now: float):
        ema = EMA_ALPHA_PACED if self.mode.paced else EMA_ALPHA_FAST
        self.detector = TapDetector(self.mode.min_intertap_s, ema,
                                    self.d_closed, self.d_open)
        if self.mode.paced:
            self.grid_t0 = now
            self.next_beat_k = 0
            if self.mode.warmup_s > 0:
                self.goto(WARMUP, now)
            else:
                self._start_recording(now)
        else:
            self.audio.play(self.beep_wav)      # start cue
            self._start_recording(now)

    def _start_recording(self, now: float):
        self.recording_start = now
        # fresh detector state for scored data; thresholds carry over
        ema = EMA_ALPHA_PACED if self.mode.paced else EMA_ALPHA_FAST
        self.detector = TapDetector(self.mode.min_intertap_s, ema,
                                    self.d_closed, self.d_open)
        self.beat_times = []
        self.hand_frames = 0
        self.visible_frames = 0
        self.goto(RECORDING, now)

    def _run_detector(self, c: Canvas, now: float, landmarks, d) -> None:
        tapped = self.detector.update(now, d)
        if tapped and landmarks is not None:
            fx = int((landmarks[4][0] + landmarks[8][0]) / 2 * c.w)
            fy = int((landmarks[4][1] + landmarks[8][1]) / 2 * c.h)
            self.ripples.append((now, fx, fy))
            self.glow_t = now

    def _render_feedback(self, c: Canvas, now: float):
        # tap ripple: success ring expanding from the fingertips (§6.3)
        if not theme.REDUCED_MOTION:
            self.ripples = [r for r in self.ripples if now - r[0] < 0.25]
            for t0, x, y in self.ripples:
                p = (now - t0) / 0.25
                c.ring(x, y, lerp(10, 42, ease_out_cubic(p)), "success",
                       thickness=2, alpha=1.0 - p)
        c.border_glow("brand", 0.4 * max(0.0, 1 - (now - self.glow_t) / 0.2))

    def _beat_ring(self, c: Canvas, now: float):
        """Pulsing rhythm ring, top-center: expands on the beat, relaxes back."""
        if not self.mode.paced:
            return
        cx, cy = c.w // 2, 92
        interval = self.mode.interval_s
        since = max(0.0, now - self.last_beat_t)
        p = ease_out_cubic(min(1.0, since / interval))
        r = lerp(30 * 1.25, 30, p) if not theme.REDUCED_MOTION else 30
        glow = 1.0 - 0.5 * p
        c.ring(cx, cy, r + 4, "surface-2", thickness=6, alpha=0.9)
        c.ring(cx, cy, r, "brand", thickness=4, alpha=glow)

    def screen_warmup(self, c: Canvas, now: float, landmarks, d):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = self.mode.warmup_s - elapsed
        if remaining <= 0:
            self._start_recording(now)
            return
        self._run_detector(c, now, landmarks, d)   # feedback only, not scored
        self._beat_ring(c, now)
        pw = min(480, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, h - 160
        c.panel(px, py, pw, 88)
        c.text(w // 2, py + 26, "Practice - not scored yet", role="body_l",
               anchor="mm", color="warning")
        c.text(w // 2, py + 52, f"Scored test begins in {remaining:.0f} s",
               role="body", color="text-muted", anchor="mm")
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       elapsed / self.mode.warmup_s, color="warning",
                       label="warm-up")
        if landmarks is None:
            self.toasts.show("Keep your hand in the frame", "warning", now=now)

    def screen_recording(self, c: Canvas, now: float, landmarks, d):
        w, h = c.w, c.h
        elapsed = now - self.recording_start
        remaining = self.mode.duration_s - elapsed
        self.hand_frames += 1
        if landmarks is not None:
            self.visible_frames += 1
        if remaining <= 0:
            self._finish(now)
            return
        self._run_detector(c, now, landmarks, d)
        self._beat_ring(c, now)

        # live metric chips (top-left, under status bar)
        taps = len(self.detector.tap_times)
        recent = [t for t in self.detector.tap_times if t > now - 5]
        rate = (len(recent) - 1) / (recent[-1] - recent[0]) \
            if len(recent) >= 2 and recent[-1] > recent[0] else 0.0
        c.panel(theme.SAFE_MARGIN, 60, 168, 76, alpha=0.75, radius=12,
                shadow=False)
        c.text(theme.SAFE_MARGIN + 14, 76, f"Taps  {taps}", role="body_sb",
               mono=True)
        c.text(theme.SAFE_MARGIN + 14, 104, f"Rate  {rate:.1f} Hz", role="body_sb",
               mono=True)

        # sparkline of the distance signal with tap dots (§5)
        sw = min(320, w - 2 * theme.SAFE_MARGIN)
        c.sparkline(w - sw - theme.SAFE_MARGIN, h - 130, sw, 70,
                    self.detector.series, self.detector.tap_times, now,
                    lo=self.d_closed, hi=self.d_open)

        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       elapsed / self.mode.duration_s, color="success",
                       label=f"{remaining:.0f} s left")
        if landmarks is None:
            self.toasts.show("Keep your hand in the frame", "warning", now=now)

    def _finish(self, now: float):
        visible_ratio = (self.visible_frames / self.hand_frames
                         if self.hand_frames else 0.0)
        self.results = compute_metrics(
            self.mode, self.detector.tap_times, self.detector.series,
            self.recording_start, now, beat_times=self.beat_times,
            hand_visible_ratio=visible_ratio)
        self.audio.play(self.done_wav)
        hand = max(self.hand_labels, key=self.hand_labels.get) \
            if self.hand_labels else None
        t0 = self.recording_start
        raw = {
            "tap_times_s": [round(t - t0, 3) for t in self.detector.tap_times],
            "distance_series": [[round(t - t0, 3), round(dd, 4)]
                                for t, dd in self.detector.series],
            "beat_times_s": [round(b - t0, 3) for b in self.beat_times],
            "calibration": {"d_closed": round(self.d_closed, 4),
                            "d_open": round(self.d_open, 4)},
            "hand_visible_ratio": round(visible_ratio, 3),
        }
        try:
            self.saved_path = save_session(
                test="finger_tapping", mode=self.mode.key, hand=hand,
                duration_s=self.mode.duration_s,
                device={"camera_fps": round(self.fps, 1),
                        "resolution": "640x480", "app_version": APP_VERSION},
                metrics=self.results, raw=raw)
        except OSError as e:
            self.saved_path = None
            print(f"[WARN] Could not save session: {e}")
        if self.results.get("cv_pct") is not None:
            self.countup = CountUp(self.results["cv_pct"], time.time(),
                                   theme.DUR_SLOW)
        self.goto(COMPLETE, now)

    def screen_complete(self, c: Canvas, now: float):
        w, h = c.w, c.h
        r = self.results
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        bh = 42

        # ── measure content first, then size the panel to fit (button never
        #    overlaps the metric rows / notes) ──
        if r["scoreable"]:
            rows = [("Tap rate", f"{r['frequency_hz']:.2f} Hz"),
                    ("Mean interval", f"{r['mean_iti_ms']:.0f} ms"),
                    ("IIV (SD)", f"{r['iiv_ms']:.1f} ms"),
                    ("Taps", f"{r['taps']}")]
            if r.get("amplitude_cv_pct") is not None:
                rows.append(("Amplitude CV", f"{r['amplitude_cv_pct']:.1f} %"))
            if r.get("decrement_pct_per_s") is not None:
                rows.append(("Speed change", f"{r['decrement_pct_per_s']:+.1f} %/s"))
            if r.get("sync_sd_ms") is not None:
                rows.append(("Beat sync SD", f"{r['sync_sd_ms']:.0f} ms"))
            if r.get("hits") is not None:
                rows.append(("Beats hit", f"{r['hits']}/{r['hits'] + r['misses']}"))
            rows = rows[:8]
            nlines = (len(rows) + 1) // 2
            note_off = 190 + nlines * 24 + 6
            saved_off = note_off + 20
            btn_off = (saved_off if self.saved_path else note_off) + 26
        else:
            reason = r["reason"] or "Something went wrong - please try again."
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
        c.text(w // 2, py + 30, f"{self.mode.title} - Results", role="h2",
               anchor="mm")

        if r["scoreable"]:
            cv_val = self.countup.value(now) if self.countup else r["cv_pct"]
            c._dirty = True
            c.draw.text((w // 2, py + 90), f"{cv_val:.1f}%",
                        font=get_font("mono", 56),
                        fill=theme.rgba(r["status"], 1.0), anchor="mm")
            c.text(w // 2, py + 126, "Rhythm variability (CV of tap intervals)",
                   role="caption", color="text-muted", anchor="mm")
            c.badge(w // 2, py + 140, r["label"], r["status"])
            col_w = (pw - 3 * theme.SPACE[4]) // 2
            for i, (label, val) in enumerate(rows):
                rx = px + theme.SPACE[4] + (i % 2) * (col_w + theme.SPACE[4])
                ry = py + 190 + (i // 2) * 24
                c.text(rx, ry, label, role="caption", color="text-muted")
                c.text(rx + col_w, ry, val, role="caption", anchor="ra", mono=True)
            c.text(w // 2, py + note_off,
                   f"Typical < {self.mode.cv_typical:.0f}% | monitor "
                   f"{self.mode.cv_typical:.0f}-{self.mode.cv_monitor:.0f}% | "
                   f"elevated > {self.mode.cv_monitor:.0f}%",
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
        win = "Finger Tapping Test  |  Q or window ✕ to quit"
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

            landmarks = self.detect_hand(frame, now)
            d = thumb_index_distance(landmarks) if landmarks is not None else None
            self.run_metronome(now)

            if landmarks is not None:
                draw_hand_skeleton(frame, landmarks, HAND_CONNECTIONS,
                                   highlight=(now - self.glow_t) < 0.15)

            c = Canvas(frame)
            # persistent status bar (§5): hand + FPS quality + mode
            chips = [("Hand detected", "success") if landmarks is not None
                     else ("Show your hand", "warning")]
            if self.fps < 24:
                chips.append((f"{self.fps:.0f} fps", "warning"))
            c.status_bar(chips, self.mode.title)

            if self.state == IDLE:
                self.screen_idle(c, now)
            elif self.state == INSTRUCTION:
                self.screen_instruction(c, now)
            elif self.state == CALIBRATION:
                self.screen_calibration(c, now, landmarks, d)
            elif self.state == COUNTDOWN:
                self.screen_countdown(c, now)
            elif self.state == WARMUP:
                self.screen_warmup(c, now, landmarks, d)
            elif self.state == RECORDING:
                self.screen_recording(c, now, landmarks, d)
            elif self.state == COMPLETE:
                self.screen_complete(c, now)

            if self.state in (WARMUP, RECORDING):
                self._render_feedback(c, now)
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
        print("\n[INFO] Finger tapping test closed.")


def main():
    print("=" * 52)
    print("  Finger Tapping Test")
    print("  Modes: Big & Fast (primary) / Paced Rhythm")
    print("=" * 52)
    source = select_camera_source()
    cap = open_capture(source)
    if cap is None:
        print("[ERROR] Could not open camera.")
        sys.exit(1)
    App(cap).run()


if __name__ == "__main__":
    main()
