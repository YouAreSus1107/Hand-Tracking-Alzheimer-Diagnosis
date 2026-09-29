"""
Finger Tapping Test
===================
Camera-based finger-tapping screening with two paradigms (core/tapping/modes.py):

  Big & Fast  -- self-paced maximum-speed tapping, 20 s (primary; the
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

# Stdlib-only, and above the heavy imports on purpose: cv2 + mediapipe take
# ~2 s warm and ~10 s cold, and nothing reaches the console until they land.
from core.splash import Splash, IMPORT_STEPS
_splash = Splash("Finger Tapping Test",
                 "Modes: Big & Fast (primary) / Paced Rhythm",
                 IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
_splash.step()               # OpenCV in
from core import quiet       # keep above mediapipe: silences its startup log
import mediapipe as mp
_splash.step()               # MediaPipe in

from core import i18n
from core.hand_utils import (HAND_CONNECTIONS, make_landmark_filters,
                             smooth_landmarks, preprocess_for_mediapipe,
                             true_hand)
from core.camera import (capture_info, preset_camera_name, select_camera_source, open_capture,
                         create_display_window, window_closed, pause_before_exit)
from core.screen_recorder import ScreenRecorder
from core.mirror_check import ensure_orientation
from core import profiles
from core.session import load_index, save_session
from core.tapping import baseline
from core.tapping.audio import AudioWorker, build_tone
from core.tapping.detector import Calibrator, TapDetector, thumb_index_distance
from core.tapping.gaps import label_gaps, restore_missed_tap
from core.tapping.metrics import compute_metrics, scored_taps
from core.tapping.modes import MODES, DEFAULT_MODE, TapMode
from core.ui import theme
from core.ui.anim import CountUp, ease_out_cubic, lerp
from core.ui.components import Canvas, draw_hand_skeleton, get_font
from core import framing
from core.ui.framing_ui import framing_chips, draw_framing
from core.ui.coach import Coach, PROMPT_Y, PRI_HAND, PRI_SETUP

_splash.done()   # imports are in; the camera prompt follows immediately

APP_VERSION = "0.2.0"
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

COUNTDOWN_FROM = 3
AUDIO_LEAD = 0.200          # fire beeps early to offset OS audio latency
EMA_ALPHA_PACED = 0.4
EMA_ALPHA_FAST = 0.6        # less smoothing lag for max-speed tapping
# After a pause for the hand leaving the frame, taps this soon after resuming
# are not trusted either: the detector's state is from before the pause.
RESUME_GUARD_S = 0.25

# ── States ─────────────────────────────────────────────────────────────────
IDLE, INSTRUCTION, CALIBRATION, COUNTDOWN, WARMUP, RECORDING, COMPLETE = (
    "idle", "instruction", "calibration", "countdown", "warmup", "recording",
    "complete")


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
        with quiet.muted_native_stderr():
            self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.audio = AudioWorker()
        self.beep_wav = build_tone(880, 100)
        self.tick_wav = build_tone(660, 60)
        self.done_wav = build_tone(523, 180)

        self.mode: TapMode = MODES[DEFAULT_MODE]
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
        # Pause-and-resume while the hand is out of frame. The scored clock is
        # wall time minus time spent paused, so the pause vanishes from every
        # timeline; the one interval that spans it is dropped via a blackout.
        self.paused_total = 0.0
        self.paused_since: float | None = None
        self.pauses: list[tuple[float, float]] = []      # (scored t, wall s)
        self.blackouts: list[tuple[float, float]] = []   # scored clock
        self.results = None
        self.saved_path = None
        self.countup: CountUp | None = None

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
            scored_beat = beat_t - self.paused_total
            if (self.state == RECORDING and self.paused_since is None
                    and scored_beat >= self.recording_start):
                self.beat_times.append(scored_beat)
            self.next_beat_k = k_due + 1

    # ── per-frame pipeline ────────────────────────────────────────────────
    def detect_hand(self, frame, now: float):
        # Adaptive load shedding (audit A13): skip CLAHE+sharpen when slow.
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        if not result.hand_landmarks:
            return None, None
        # Frame is flipped to selfie view, so MediaPipe's label names the
        # OTHER hand -- true_hand() undoes that (core/hand_utils.py).
        if result.handedness:
            label = true_hand(result.handedness[0][0].category_name,
                              selfie=True)
            self.hand_labels[label] = self.hand_labels.get(label, 0) + 1
        raw_pts = [(lm.x, lm.y) for lm in result.hand_landmarks[0]]
        return smooth_landmarks(result.hand_landmarks[0],
                                self.lm_filters_x, self.lm_filters_y,
                                now), raw_pts

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 130, 236
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, i18n.t("Finger Tapping Test"), role="h1",
               anchor="mm")
        c.text(w // 2, py + 74, i18n.t("Measures motor rhythm and speed -"),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 98,
               i18n.t("markers studied in early cognitive decline."),
               role="body", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        b1 = c.button(px + theme.SPACE[4], py + 128, bw, 48,
                      i18n.t("Start {mode} ({secs} s)",
                             mode=i18n.t(MODES["big_and_fast"].title),
                             secs=f"{MODES['big_and_fast'].duration_s:.0f}"),
                      variant="primary",
                      hovered=self.hover(px + theme.SPACE[4], py + 128, bw, 48),
                      icon="play")
        b2 = c.button(px + theme.SPACE[4], py + 184, bw, 40,
                      i18n.t("{mode} ({secs} s, with metronome)",
                             mode=i18n.t(MODES["paced"].title),
                             secs=f"{MODES['paced'].duration_s:.0f}"),
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
        # Chinese needs its own line breaks, so the block is keyed rather
        # than translated line by line -- the line counts differ.
        lines = i18n.tk(f"tap.{self.mode.key}.instructions",
                        self.mode.instructions)
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 34,
               i18n.t("{mode} - Your Task", mode=i18n.t(self.mode.title)),
               role="h2", anchor="mm", color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        c.text(w // 2, py + 84 + len(lines) * 30,
               i18n.t("Next: a quick warm-up so we can calibrate to your hand."),
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, i18n.t("I'm Ready"), variant="success",
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
        ph = 118
        px, py = (w - pw) // 2, h - PROMPT_Y - 8 - ph   # clear of the prompt
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 28, i18n.t("Warm-up: open and close your hand"),
               role="body_l", anchor="mm")
        c.text(w // 2, py + 54,
               i18n.t("Touch index finger to thumb, then open wide - a few times."),
               role="caption", color="text-muted", anchor="mm")
        c.progress_bar(px + theme.SPACE[4], py + 84, pw - 2 * theme.SPACE[4],
                       self.calibrator.progress, color="warning",
                       label=f"{int(self.calibrator.progress * 100)} %")
        if landmarks is None:
            self.coach.say(i18n.t("Show your hand to the camera"), PRI_HAND)
        elif self.calibrator.timed_out(now) and not self.calibrator.done:
            self.coach.say(i18n.t("Move your hand a little closer to the camera"),
                           PRI_SETUP)
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
        c.text(w // 2, h // 2 - 100, i18n.t("Get ready..."), role="h2",
               anchor="mm",
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
        self.paused_total = 0.0
        self.paused_since = None
        self.pauses = []
        self.blackouts = []
        self.framing = framing.FramingMonitor()
        self.goto(RECORDING, now)

    def _run_detector(self, c: Canvas, now: float, landmarks, d,
                      t: float | None = None) -> None:
        tapped = self.detector.update(now if t is None else t, d)
        if tapped and landmarks is not None:
            fx = int((landmarks[4][0] + landmarks[8][0]) / 2 * c.w)
            fy = int((landmarks[4][1] + landmarks[8][1]) / 2 * c.h)
            self.ripples.append((now, fx, fy))
            self.glow_t = now

    def _scored(self, now: float) -> float:
        """Wall time minus time spent paused; frozen while paused."""
        if self.paused_since is not None:
            now = self.paused_since
        return now - self.paused_total

    def _update_pause(self, now: float):
        """Pause the scored run while the hand is (partly) out of frame and
        resume once the framing monitor trusts it again."""
        if self.framing.untrusted and self.paused_since is None:
            self.paused_since = now
        elif not self.framing.untrusted and self.paused_since is not None:
            at = self.paused_since - self.paused_total   # scored time paused
            wall = now - self.paused_since
            self.paused_total += wall
            self.paused_since = None
            self.blackouts.append((at - framing.PRE_ROLL_S,
                                   at + RESUME_GUARD_S))
            self.pauses.append((round(at - self.recording_start, 3),
                                round(wall, 2)))

    def _paused_panel(self, c: Canvas):
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, h // 2 - 50
        # what to do about it is the prompt channel's job, below
        c.panel(px, py, pw, 76)
        c.text(w // 2, py + 28, i18n.t("Paused - your hand is out of view"),
               role="body_l", anchor="mm", color="warning")
        c.text(w // 2, py + 54,
               i18n.t("The test continues when your whole hand is back."),
               role="caption", color="text-muted", anchor="mm")

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
        px, py = (w - pw) // 2, h - PROMPT_Y - 8 - 88   # clear of the prompt
        c.panel(px, py, pw, 88)
        c.text(w // 2, py + 26, i18n.t("Practice - not scored yet"),
               role="body_l", anchor="mm", color="warning")
        c.text(w // 2, py + 52,
               i18n.t("Scored test begins in {secs} s", secs=f"{remaining:.0f}"),
               role="body", color="text-muted", anchor="mm")
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       elapsed / self.mode.warmup_s, color="warning",
                       label=i18n.t("warm-up"))
        if landmarks is None:
            self.coach.say(i18n.t("Show your hand to the camera"), PRI_HAND)

    def screen_recording(self, c: Canvas, now: float, landmarks, d):
        w, h = c.w, c.h
        self._update_pause(now)
        st = self._scored(now)
        elapsed = st - self.recording_start
        remaining = self.mode.duration_s - elapsed
        paused = self.paused_since is not None
        if not paused:
            self.hand_frames += 1
            if landmarks is not None:
                self.visible_frames += 1
        if remaining <= 0:
            self._finish(now)
            return
        if not paused:
            self._run_detector(c, now, landmarks, d, t=st)
        self._beat_ring(c, now)

        # live metric chips (top-left, under status bar)
        taps = len(self.detector.tap_times)
        recent = [t for t in self.detector.tap_times if t > now - 5]
        rate = (len(recent) - 1) / (recent[-1] - recent[0]) \
            if len(recent) >= 2 and recent[-1] > recent[0] else 0.0
        c.panel(theme.SAFE_MARGIN, 60, 168, 76, alpha=0.75, radius=12,
                shadow=False)
        # label and value are drawn apart: the label is translated, the value
        # keeps the mono face so the digits stay tabular as it counts up.
        val_x = theme.SAFE_MARGIN + 154
        c.text(theme.SAFE_MARGIN + 14, 76, i18n.t("Taps"), role="body_sb")
        c.text(val_x, 76, f"{taps}", role="body_sb", anchor="ra", mono=True)
        c.text(theme.SAFE_MARGIN + 14, 104, i18n.t("Rate"), role="body_sb")
        c.text(val_x, 104, f"{rate:.1f} Hz", role="body_sb", anchor="ra",
               mono=True)

        # sparkline of the distance signal with tap dots (§5)
        sw = min(320, w - 2 * theme.SAFE_MARGIN)
        c.sparkline(w - sw - theme.SAFE_MARGIN, h - PROMPT_Y - 8 - 70, sw, 70,
                    self.detector.series, self.detector.tap_times, st,
                    lo=self.d_closed, hi=self.d_open)

        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       elapsed / self.mode.duration_s, color="success",
                       label=i18n.t("{secs} s left", secs=f"{remaining:.0f}"))
        if paused:
            self._paused_panel(c)
        if landmarks is None:
            self.coach.say(i18n.t("Show your hand to the camera"), PRI_HAND)

    def _finish(self, now: float):
        visible_ratio = (self.visible_frames / self.hand_frames
                         if self.hand_frames else 0.0)
        self.results = compute_metrics(
            self.mode, self.detector.tap_times, self.detector.series,
            self.recording_start, self._scored(now),
            beat_times=self.beat_times,
            hand_visible_ratio=visible_ratio, camera_fps=self.fps,
            near_miss=self.detector.near_miss, blackouts=self.blackouts)
        # provenance, not part of the score
        self.results["pause_count"] = len(self.pauses)
        self.results["paused_s"] = round(self.paused_total, 1)
        self.results["edge_clipped_pct"] = round(self.framing.clipped_pct, 1)
        self.audio.play(self.done_wav)
        hand = max(self.hand_labels, key=self.hand_labels.get) \
            if self.hand_labels else None
        camera_name = preset_camera_name()
        self._compare_with_usual(hand, camera_name)
        t0 = self.recording_start
        raw = {
            "tap_times_s": [round(t - t0, 3) for t in self.detector.tap_times],
            "distance_series": [[round(t - t0, 3), round(dd, 4)]
                                for t, dd in self.detector.series],
            "beat_times_s": [round(b - t0, 3) for b in self.beat_times],
            "calibration": {"d_closed": round(self.d_closed, 4),
                            "d_open": round(self.d_open, 4)},
            "threshold_series": [[round(t - t0, 3), round(c, 4), round(o, 4)]
                                 for t, c, o in self.detector.threshold_series],
            "hand_visible_ratio": round(visible_ratio, 3),
            "near_miss_taps": self.detector.near_miss,
            "closed_dwell_frac": round(self.detector.closed_dwell_frac, 3),
            # times are on the scored clock (pauses removed); each pause is
            # (scored time it began, wall seconds it lasted)
            "pauses": [list(pz) for pz in self.pauses],
            "blackouts_s": [[round(a - t0, 3), round(b - t0, 3)]
                            for a, b in self.blackouts],
        }
        # Every long gap with its cause (core/tapping/gaps.py), and the tap
        # that was forgiven if there was one, so the report can mark both.
        scored = scored_taps(self.mode, self.detector.tap_times)
        raw["gap_labels"] = [[round(a - t0, 3), round(b - t0, 3), kind]
                             for a, b, kind in label_gaps(scored, self.detector.series,
                                                          self.blackouts)]
        if self.results.get("missed_tap_forgiven"):
            tr = restore_missed_tap(scored, self.detector.series, self.blackouts)
            if tr is not None:
                raw["restored_tap_s"] = round(tr - t0, 3)
        try:
            self.saved_path = save_session(
                test="finger_tapping", mode=self.mode.key, hand=hand,
                duration_s=self.mode.duration_s,
                device={"camera_fps": round(self.fps, 1),
                        "resolution": "640x480", "app_version": APP_VERSION,
                        **capture_info(self.cap), "camera_name": camera_name},
                metrics=self.results, raw=raw)
        except OSError as e:
            self.saved_path = None
            print(f"[WARN] Could not save session: {e}")
        if self.results.get("cv_pct") is not None:
            self.countup = CountUp(self.results["cv_pct"], time.time(),
                                   theme.DUR_SLOW)
        self.goto(COMPLETE, now)

    def _compare_with_usual(self, hand: str | None, camera_name: str) -> None:
        """This run against the same person's own earlier runs
        (core/tapping/baseline.py). A Typical run that is also far slower than
        usual becomes Monitor; nothing is ever lowered."""
        r = self.results
        try:
            pid = profiles.from_env().get("id")
            prior = baseline.eligible(load_index("finger_tapping", self.mode.key),
                                      pid, hand, self.mode.key)
        except Exception as e:           # a history problem must not lose the run
            print(f"[WARN] Could not read earlier runs: {e}")
            return
        r.update(baseline.compare(prior, r.get("frequency_hz"), r.get("confidence_pct"),
                                  r.get("amplitude_mean"), camera_name))
        if r.get("scoreable") and r.get("slower_than_usual") and r.get("status") == "success":
            r["status"], r["label"] = "warning", baseline.SLOWER_LABEL

    @staticmethod
    def _gaps_line(r: dict) -> str:
        """'1 missed tap forgiven · 2 interruptions', or '' when neither."""
        parts = []
        if r.get("missed_tap_forgiven"):
            parts.append(i18n.t("1 missed tap forgiven"))
        if r.get("rate_vs_usual") is not None:
            parts.append(i18n.t("Speed {pct}% of your usual",
                                pct=f"{r['rate_vs_usual'] * 100:.0f}"))
        n = r.get("interruptions") or 0
        if n == 1:
            parts.append(i18n.t("1 interruption"))
        elif n > 1:
            parts.append(i18n.t("{n} interruptions", n=str(n)))
        return " · ".join(parts)

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
                    ("Taps", f"{r['taps']}"),
                    ("Intervals", f"{r['n_intervals']}")]
            if r.get("amplitude_cv_pct") is not None:
                rows.append(("Amplitude CV", f"{r['amplitude_cv_pct']:.1f} %"))
            if r.get("decrement_pct_per_s") is not None:
                rows.append(("Speed change", f"{r['decrement_pct_per_s']:+.1f} %/s"))
            if r.get("sync_sd_ms") is not None:
                rows.append(("Beat sync SD", f"{r['sync_sd_ms']:.0f} ms"))
            if r.get("hits") is not None:
                rows.append(("Beats hit", f"{r['hits']}/{r['hits'] + r['misses']}"))
            rows = rows[:8]
            # Three compact columns keep the complete results screen inside a
            # 480p camera window while retaining legible caption-sized labels.
            nlines = (len(rows) + 2) // 3
            metrics_off = 248
            # the band scale sits in its own gap below the rows so it never
            # crowds the last row's values
            note_off = metrics_off + nlines * 22 + 12
            edge_off = note_off + (18 if r.get("band_edge") else 0)
            gaps_line = self._gaps_line(r)
            gaps_off = edge_off + (18 if gaps_line else 0)
            btn_off = gaps_off + 16
        else:
            reason = r["reason"] or "Something went wrong - please try again."
            # i18n.wrap, not split(): Chinese has no spaces, so splitting on
            # whitespace returns one unbreakable token that runs off the panel.
            lines = i18n.wrap(i18n.t(reason), 48)[:3]
            btn_off = 108 + len(lines) * 26 + 12
        ph = btn_off + bh + 14

        px, py = (w - pw) // 2, max(56, (h - ph) // 2)
        c.panel(px, py, pw, ph, alpha=0.9)
        c.text(w // 2, py + 30,
               i18n.t("{mode} - Results", mode=i18n.t(self.mode.title)),
               role="h2", anchor="mm")

        if r["scoreable"]:
            cv_val = self.countup.value(now) if self.countup else r["cv_pct"]
            c._dirty = True
            # Deliberately not r["status"]: a red/amber/green number here reads
            # as an on-the-spot diagnosis, which is not what this screen is for
            # (§ result page review — informal testing, explained in person).
            # The plain-language label still carries the finding in words.
            c.draw.text((w // 2, py + 90), f"{cv_val:.1f}%",
                        font=get_font("mono", 56),
                        fill=theme.rgba("text", 1.0), anchor="mm")
            c.text(w // 2, py + 126,
                   i18n.t("Rhythm variability (CV of tap intervals)"),
                   role="caption", color="text-muted", anchor="mm")
            ci_lo, ci_hi = r.get("cv_ci_low_pct"), r.get("cv_ci_high_pct")
            if ci_lo is not None and ci_hi is not None:
                c.text(w // 2, py + 142,
                       i18n.t("95% CI {low}-{high}%", low=f"{ci_lo:.1f}",
                              high=f"{ci_hi:.1f}"), role="caption",
                       color="text-muted", anchor="mm", mono=True)
            c.badge(w // 2, py + 158, i18n.t(r["label"]), "info")
            conf = r.get("confidence_pct") or 0
            # Confidence is recording quality, not a second clinical verdict.
            # Moderate therefore uses neutral info blue; only low quality warns.
            conf_status = ("success" if conf >= 75 else
                           "info" if conf >= 45 else "warning")
            conf_level = ("High" if conf >= 75 else
                          "Moderate" if conf >= 45 else "Low")
            conf_w = min(330, pw - 2 * theme.SPACE[4])
            c.confidence_card(
                # Verdict badge occupies y=158..192; keep a true 8 px gap.
                px + (pw - conf_w) // 2, py + 200, conf_w,
                label=i18n.t("Measurement confidence"),
                value=i18n.t("{level} - {pct}%", level=i18n.t(conf_level),
                             pct=f"{conf:.0f}"),
                detail="",
                progress=conf / 100.0, status=conf_status)
            # Columns are sized to what they hold, not split evenly: an even
            # split left "Speed change" and its value running into each other
            # while the other columns had room to spare.
            need = [0, 0, 0]
            for i, (label, val) in enumerate(rows):
                need[i % 3] = max(need[i % 3],
                                  c.text_width(i18n.t(label), "caption")
                                  + theme.SPACE[2]
                                  + c.text_width(val, "caption", mono=True))
            spare = max(0, pw - 4 * theme.SPACE[4] - sum(need))
            col_ws = [n + spare // 3 for n in need]
            col_xs = [px + theme.SPACE[4]]
            for cw in col_ws[:2]:
                col_xs.append(col_xs[-1] + cw + theme.SPACE[4])
            for i, (label, val) in enumerate(rows):
                rx, cw = col_xs[i % 3], col_ws[i % 3]
                ry = py + metrics_off + (i // 3) * 22
                c.text(rx, ry, i18n.t(label), role="caption",
                       color="text-muted")
                c.text(rx + cw, ry, val, role="caption", anchor="ra", mono=True)
            c.text(w // 2, py + note_off,
                   i18n.t("Typical < {typical}% | monitor {typical}-{monitor}% "
                          "| elevated > {monitor}%",
                          typical=f"{self.mode.cv_typical:.0f}",
                          monitor=f"{self.mode.cv_monitor:.0f}"),
                   role="small", color="text-muted", anchor="mm")
            if r.get("band_edge"):
                c.text(w // 2, py + note_off + 18,
                       i18n.t("Close to a band edge - repeat for a firmer reading."),
                       role="small", color="text-muted", anchor="mm")
            if gaps_line:
                c.text(w // 2, py + edge_off + 18, gaps_line,
                       role="small", color="text-muted", anchor="mm")
        else:
            c.badge(w // 2, py + 52, i18n.t("Couldn't score this run"),
                    "warning")
            for i, line in enumerate(lines):
                c.text(w // 2, py + 108 + i * 26, line, role="body",
                       color="text-muted", anchor="mm")

        bw = 160
        bx = (px + pw - theme.SPACE[4] - bw
              if r["scoreable"] else w // 2 - bw // 2)
        by = py + btn_off
        if r["scoreable"] and self.saved_path:
            c.icon("check", px + theme.SPACE[4], by + 12, 18, "success")
            c.text(px + theme.SPACE[4] + 26, by + bh // 2,
                   i18n.t("Result saved"), role="caption",
                   color="text-muted", anchor="lm")
        b = c.button(bx, by, bw, bh, i18n.t("Try Again"), variant="primary",
                     hovered=self.hover(bx, by, bw, bh))
        c.disclaimer()
        if self.hit(b):
            self.reset_run()
            self.goto(IDLE, now)

    # ── main loop ─────────────────────────────────────────────────────────
    def run(self):
        screen_rec = ScreenRecorder("finger_tapping")
        win = "Finger Tapping Test  |  Q or close the window to quit"
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

            landmarks, self._raw_pts = self.detect_hand(frame, now)
            self.framing.update(self._raw_pts, now)
            # A hand partly out of frame jitters (core/framing.py): its
            # distance is not trusted -- calibration, warm-up and the scored
            # run all see nothing rather than a guess.
            d = (thumb_index_distance(landmarks)
                 if landmarks is not None and not self.framing.untrusted
                 else None)
            self.run_metronome(now)

            if landmarks is not None:
                draw_hand_skeleton(frame, landmarks, HAND_CONNECTIONS,
                                   highlight=(now - self.glow_t) < 0.15)

            c = Canvas(frame)
            # persistent status bar (§5): hand + FPS quality + mode
            c.status_bar(framing_chips(self.framing, landmarks, self.fps),
                         i18n.t(self.mode.title))

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
            if self.state in (CALIBRATION, WARMUP, RECORDING):
                draw_framing(c, self.framing, self._raw_pts, self.coach)
            self.coach.render(c, now)

            cv2.imshow(win, screen_rec.frame(c.compose()))
            self.click = None
            key = cv2.waitKey(5) & 0xFF
            screen_rec.key(key)
            if key == ord("q"):
                break
            if window_closed(win):
                break

        self.cap.release()
        screen_rec.close()
        cv2.destroyAllWindows()
        self.landmarker.close()
        self.audio.close()
        print("\n[INFO] " + i18n.ct("Finger tapping test closed."))


def main():
    # banner already printed by the splash, above the heavy imports
    source = select_camera_source()
    print("[INFO] " + i18n.ct("Opening camera and loading the hand model - a few seconds..."))
    cap = open_capture(source, fps=60)
    if cap is None:
        print("[ERROR] " + i18n.ct("Could not open camera."))
        pause_before_exit()
        sys.exit(1)
    ensure_orientation(cap)   # once per camera: undo its own mirroring
    App(cap).run()


if __name__ == "__main__":
    main()
