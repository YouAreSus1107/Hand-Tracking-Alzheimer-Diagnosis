"""
Oculomotor Test (Pro/Anti-saccade)
==================================
Webcam-only saccadic eye-movement screening (docs/OCULOMOTOR_TEST_PLAN.md):

  Part 1 - Look Toward  -- prosaccade block, 16 trials (per-user latency
                           baseline; look AT the dot).
  Part 2 - Look Away    -- anti-saccade block, 24 trials (primary; look AWAY
                           from the dot - inhibitory control).
  Part 3 - Hold Still   -- fixation-stability hold (research §10.3): stare at
                           the central cross while jitter, 2-D BCEA, and
                           saccadic-intrusion rate are measured.

Headline biomarker: anti-saccade error rate % (Opwonya 2022 meta-analysis,
SMD 1.59 for AD vs controls). Latency is reported with Anti − Pro leading,
because the fixed camera+display offset cancels in the difference (§3.4).
Fixation stability is a secondary readout (core/gaze/fixation.py).

Flow: start -> instructions -> 3-point gaze calibration -> countdown ->
practice (3 unscored trials, explicit feedback) -> scored block; then the
anti block repeats instructions -> countdown -> practice -> scored; then a
brief fixation hold; results are auto-saved to results/ as JSON + CSV index.

This file is the run loop + rendering only; the gaze engine (tracker,
calibration, saccade detection, metrics, tasks) lives in core/gaze/.

Run:  python screening_tests/oculomotor_test.py     Quit: press 'q'
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))  # keep first: hand_utils import path

# Stdlib-only, and above the heavy imports on purpose: cv2 + mediapipe take
# ~2 s warm and ~10 s cold, and nothing reaches the console until they land.
from core.splash import Splash, GAZE_IMPORT_STEPS
_splash = Splash("Eye Movement Test (Pro/Anti-saccade)",
                 "Part 1: look toward - Part 2: look away - Part 3: hold still",
                 GAZE_IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
import numpy as np
_splash.step()               # OpenCV in

from core.hand_utils import preprocess_for_mediapipe
from core.camera import (select_camera_source, open_capture,
                         create_display_window, window_closed)
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.gaze.calibrate import GazeCalibrator, GazeMap
from core.gaze.detector import SaccadeTrial, TrialResult
from core.gaze.fixation import (FixationAnalyzer, FixationResult,
                                HOLD_S as FIX_HOLD_S, SETTLE_S as FIX_SETTLE_S)
from core.gaze.metrics import (compute_metrics, ERROR_TYPICAL_PCT,
                               ERROR_MONITOR_PCT)
from core.gaze.tasks import TASKS, BLOCK_ORDER, SaccadeTask, build_directions
from core.gaze.tracker import GazeTracker, GazeSample
from core.ui import theme
from core.ui.anim import CountUp, ease_out_cubic, fade_in_out, lerp
from core.ui.components import Canvas, get_font

_splash.done()   # imports are in; the camera prompt follows immediately

APP_VERSION = "0.1.0"
MODEL_PATH = str(_REPO_ROOT / "model" / "face_landmarker.task")

COUNTDOWN_FROM = 3
DIM_ALPHA = 0.80            # video dim during stimulus phases (dot salience)
# Full-screen text cards read as a murky gray veil over the video at the
# stimulus dim, so they get a near-solid backdrop and an opaque panel instead:
# nothing to look at but the words.
CARD_DIM = 0.96
CARD_PANEL_ALPHA = 0.98
FEEDBACK_S = 0.9            # practice per-trial feedback pause

# ── States ─────────────────────────────────────────────────────────────────
IDLE, INSTRUCTION, CALIBRATION, COUNTDOWN, PRACTICE, RECORDING, COMPLETE = (
    "idle", "instruction", "calibration", "countdown", "practice", "recording",
    "complete")
# Fixation-stability block (Part 3), after the anti block
FIX_INTRO, FIX_HOLD = "fix_intro", "fix_hold"

# Fixation intro copy (Part 3) — not a SaccadeTask, so kept beside the screen.
FIX_TITLE = "Part 3 - Hold Still"
FIX_INSTRUCTIONS = (
    "Keep your eyes on the + in the middle.",
    "Don't follow anything - just hold still",
    "and stare at the center until the ring fills.",
)

# Trial phases inside PRACTICE / RECORDING
FIXATION, GAP, TARGET, FEEDBACK = "fixation", "gap", "target", "feedback"

# How much the video is dimmed per state. Applied once in the run loop, before
# the status bar is drawn, so the bar stays legible instead of being painted
# over. IDLE is absent: the user needs a clear view to frame their face.
DIM_BY_STATE = {
    CALIBRATION: DIM_ALPHA, COUNTDOWN: DIM_ALPHA, PRACTICE: DIM_ALPHA,
    RECORDING: DIM_ALPHA, FIX_HOLD: DIM_ALPHA,
    INSTRUCTION: CARD_DIM, FIX_INTRO: CARD_DIM, COMPLETE: CARD_DIM,
}


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
        self.tracker = GazeTracker(MODEL_PATH)
        self.audio = AudioWorker()
        self.tick_wav = build_tone(660, 60)
        self.good_wav = build_tone(880, 90)
        self.done_wav = build_tone(523, 180)

        self.state = IDLE
        self.toasts = Toasts()
        self.rng = random.Random()

        self.mouse = (0, 0)
        self.click: tuple[int, int] | None = None
        self.fps = 30.0
        self._last_frame_t: float | None = None
        self._dim_solid = None          # cached solid for dim_frame

        self.reset_run()

    # ── run-scoped state ──────────────────────────────────────────────────
    def reset_run(self):
        self.calibrator: GazeCalibrator | None = None
        self.gaze_map: GazeMap | None = None
        self.block_i = 0
        self.t_state = time.time()
        self.phase = FIXATION
        self.phase_t0 = self.t_state
        self.fix_dur = 1.5
        self.trial: SaccadeTrial | None = None
        self.dirs: list[int] = []
        self.trial_idx = 0
        self.last_result: TrialResult | None = None
        self.block_results: dict[str, list[TrialResult]] = {"pro": [], "anti": []}
        self.raw_trials: dict[str, list[dict]] = {"pro": [], "anti": []}
        self.face_frames = 0
        self.visible_frames = 0
        self.recording_time = 0.0
        self._rec_t0: float | None = None
        self.fixation: FixationAnalyzer | None = None
        self.fix_result: FixationResult | None = None
        self.results = None
        self.saved_path = None
        self.countup: CountUp | None = None

    @property
    def task(self) -> SaccadeTask:
        return TASKS[BLOCK_ORDER[min(self.block_i, len(BLOCK_ORDER) - 1)]]

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

    # ── per-frame gaze pipeline ───────────────────────────────────────────
    def detect_gaze(self, frame, now: float) -> GazeSample | None:
        # Adaptive load shedding: skip CLAHE+sharpen when slow (as tapping does).
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        return self.tracker.detect(rgb, now, frame.shape[1], frame.shape[0])

    def gaze_pos(self, sample: GazeSample | None) -> float | None:
        """Signed screen position in [−1.5, 1.5], or None (no face / blink)."""
        if (sample is None or sample.ratio is None or self.gaze_map is None):
            return None
        return self.gaze_map.position(sample.ratio)

    # ── stimulus drawing ──────────────────────────────────────────────────
    def dim_frame(self, frame, alpha: float) -> None:
        """Blend the video toward the background color, in place.

        Dimming the frame itself rather than painting a translucent rectangle
        into the Canvas overlay matters: PIL's rectangle *replaces* overlay
        pixels, so a dim rect and the status bar's own rect would each cut a
        hole in the other. Here every overlay element composites over an
        already-dimmed image, and panels keep their intended opacity.
        """
        if self._dim_solid is None or self._dim_solid.shape != frame.shape:
            self._dim_solid = np.full(frame.shape, theme.bgr("bg"), np.uint8)
        cv2.addWeighted(frame, 1.0 - alpha, self._dim_solid, alpha, 0.0, frame)

    def draw_cross(self, c: Canvas, alpha: float = 1.0):
        cx, cy = c.w // 2, c.h // 2
        s = 16
        c.polyline([(cx - s, cy), (cx + s, cy)], "text", thickness=3, alpha=alpha)
        c.polyline([(cx, cy - s), (cx, cy + s)], "text", thickness=3, alpha=alpha)

    def target_x(self, c: Canvas, direction: int) -> int:
        return int(c.w // 2 + direction * self.task.eccentricity * c.w)

    def draw_target(self, c: Canvas, direction: int):
        c.dot(self.target_x(c, direction), c.h // 2, 16, "text",
              outline="brand", outline_w=3)

    def draw_eye_markers(self, c: Canvas, sample: GazeSample | None):
        if sample is None:
            return
        for (x, y) in sample.iris_px:
            c.dot(x, y, 3, "brand")
        for (x, y) in sample.corners_px:
            c.dot(x, y, 2, "surface-2")

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float, sample: GazeSample | None):
        self.draw_eye_markers(c, sample)
        w, h = c.w, c.h
        pw = min(540, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 140, 250
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, "Eye Movement Test", role="h1", anchor="mm")
        c.text(w // 2, py + 74, "Measures how quickly and accurately your eyes",
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 98, "respond - a marker studied in early cognitive decline.",
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 128, "Two short parts, about 4 minutes total.",
               role="body", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        b1 = c.button(px + theme.SPACE[4], py + 156, bw, 48,
                      "Start Eye Movement Test", variant="primary",
                      hovered=self.hover(px + theme.SPACE[4], py + 156, bw, 48),
                      icon="play")
        c.text(w // 2, py + 226, "Sit about arm's length from the screen, face the camera.",
               role="caption", color="text-muted", anchor="mm")
        c.disclaimer()
        if self.hit(b1):
            self.reset_run()
            self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        w, h = c.w, c.h
        task = self.task
        lines = task.instructions
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph, alpha=CARD_PANEL_ALPHA)
        c.text(w // 2, py + 34, task.title, role="h2", anchor="mm", color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        next_line = ("Next: a quick calibration - just look at three dots."
                     if self.gaze_map is None else
                     "First a few practice tries, then the scored part.")
        c.text(w // 2, py + 84 + len(lines) * 30, next_line,
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, "I'm Ready", variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.hit(b):
            if self.gaze_map is None:
                self.calibrator = GazeCalibrator(now)
                self.goto(CALIBRATION, now)
            else:
                self.goto(COUNTDOWN, now)

    def _calib_dot_xy(self, c: Canvas, stage: str) -> tuple[int, int]:
        cy = c.h // 2
        if stage == "center":
            return c.w // 2, cy
        return self.target_x(c, -1 if stage == "left" else 1), cy

    def screen_calibration(self, c: Canvas, now: float,
                           sample: GazeSample | None):
        w, h = c.w, c.h
        cal = self.calibrator
        ratio = sample.ratio if sample is not None else None
        advanced = cal.update(now, ratio)
        if advanced:
            self.audio.play(self.tick_wav)

        if cal.failed:
            self.toasts.show(cal.fail_reason, "warning", hold=3.0, now=now)
            self.calibrator = GazeCalibrator(now)   # auto-restart
            return
        if cal.done:
            self.gaze_map = cal.result()
            self.audio.play(self.good_wav)
            self.goto(COUNTDOWN, now)
            return

        # the calibration dot, with a gentle breathing ring
        dx, dy = self._calib_dot_xy(c, cal.stage)
        pulse = 1.0 + (0.15 * (0.5 + 0.5 * ease_out_cubic((now * 2) % 1))
                       if not theme.REDUCED_MOTION else 0.0)
        c.dot(dx, dy, 14, "text", outline="brand", outline_w=3)
        c.ring(dx, dy, 22 * pulse, "brand", thickness=2, alpha=0.7)

        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h - 190, 118
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 28, "Calibration: look at the glowing dot",
               role="body_l", anchor="mm")
        c.text(w // 2, py + 54, "Keep your head still - move only your eyes.",
               role="caption", color="text-muted", anchor="mm")
        c.progress_bar(px + theme.SPACE[4], py + 84, pw - 2 * theme.SPACE[4],
                       cal.progress, color="warning",
                       label=f"{int(cal.progress * 100)} %")
        if sample is None:
            self.toasts.show("Show your face to the camera", "warning", now=now)
        elif cal.stage_timed_out(now):
            self.toasts.show("Having trouble? Sit closer and add a little light",
                             "info", hold=3.0, now=now)

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
        c.text(w // 2, h // 2 - 100, "Get ready...", role="h2", anchor="mm",
               color="text-muted")
        if int(elapsed) != getattr(self, "_last_tick", -1):
            self._last_tick = int(elapsed)
            self.audio.play(self.tick_wav)

    # ── trial machine (shared by PRACTICE and RECORDING) ──────────────────
    def _start_practice(self, now: float):
        self.dirs = build_directions(self.task.n_practice, self.rng)
        self.trial_idx = 0
        self._begin_fixation(now)
        self.goto(PRACTICE, now)

    def _start_recording(self, now: float):
        self.dirs = build_directions(self.task.n_trials, self.rng)
        self.trial_idx = 0
        self._rec_t0 = now
        self._begin_fixation(now)
        self.goto(RECORDING, now)
        self.toasts.show("Scored part - keep going", "info", now=now)

    def _begin_fixation(self, now: float):
        self.phase = FIXATION
        self.phase_t0 = now
        self.fix_dur = self.rng.uniform(self.task.fixation_min_s,
                                        self.task.fixation_max_s)
        self.trial = None

    def _finish_trial(self, now: float, scored: bool):
        res = self.trial.finalize()
        self.last_result = res
        key = self.task.key
        if scored:
            self.block_results[key].append(res)
            self.raw_trials[key].append({
                "dir": res.target_dir,
                "outcome": res.outcome,
                "latency_ms": round(res.latency_ms, 1) if res.latency_ms else None,
                "series": [[round(t, 3), round(p, 3) if p is not None else None]
                           for t, p in self.trial.series],
            })
        self.trial = None
        if res.outcome == "correct" and not scored:
            self.audio.play(self.good_wav)

    def _advance_trial(self, now: float):
        self.trial_idx += 1
        n = self.task.n_practice if self.state == PRACTICE else self.task.n_trials
        if self.trial_idx < n:
            self._begin_fixation(now)
            return
        if self.state == PRACTICE:
            self._start_recording(now)
            return
        # scored block finished
        self.recording_time += now - self._rec_t0
        if BLOCK_ORDER[self.block_i] == "pro":
            self.block_i += 1
            self.audio.play(self.good_wav)
            self.goto(INSTRUCTION, now)
        else:
            # anti block done → fixation-stability hold (Part 3)
            self.audio.play(self.good_wav)
            self.goto(FIX_INTRO, now)

    def _feedback_copy(self, res: TrialResult) -> tuple[str, str]:
        if res.outcome == "correct":
            return "Correct", "success"
        if res.outcome in ("error_uncorrected", "error_corrected"):
            return ("Look AWAY from the dot" if self.task.is_anti
                    else "Look AT the dot"), "warning"
        if res.outcome == "anticipatory":
            return "A little early - wait for the dot", "info"
        return "Eyes not detected - face the camera", "warning"

    def screen_trials(self, c: Canvas, now: float, pos: float | None,
                      sample: GazeSample | None):
        w, h = c.w, c.h
        practice = self.state == PRACTICE
        elapsed = now - self.phase_t0

        if self.state == RECORDING:
            self.face_frames += 1
            if sample is not None:
                self.visible_frames += 1

        if self.phase == FIXATION:
            self.draw_cross(c)
            if elapsed >= self.fix_dur:
                self.phase, self.phase_t0 = GAP, now
        elif self.phase == GAP:
            if elapsed >= self.task.gap_s:
                self.phase, self.phase_t0 = TARGET, now
        elif self.phase == TARGET:
            direction = self.dirs[self.trial_idx]
            if self.trial is None:
                # t₀ = the frame the dot is first actually rendered (§3.2)
                self.trial = SaccadeTrial(now, direction,
                                          self.gaze_map.deadband,
                                          self.task.is_anti)
                self.audio.play(self.tick_wav)
            self.draw_target(c, direction)
            self.trial.update(now, pos)
            if now - self.trial.t0 >= self.task.target_hold_s:
                self._finish_trial(now, scored=not practice)
                if practice:
                    self.phase, self.phase_t0 = FEEDBACK, now
                else:
                    self._advance_trial(now)
        elif self.phase == FEEDBACK:
            msg, status = self._feedback_copy(self.last_result)
            c.badge(w // 2, h // 2 - 60, msg, status)
            if elapsed >= FEEDBACK_S:
                self._advance_trial(now)

        # a trial may have ended the block/run above — don't draw its now-stale
        # progress bar over the next screen for this frame.
        if self.state not in (PRACTICE, RECORDING):
            return

        # phase label + progress
        n = self.task.n_practice if practice else self.task.n_trials
        label = "Practice" if practice else self.task.title
        c.text(theme.SAFE_MARGIN, 68, f"{label}  -  trial {min(self.trial_idx + 1, n)} of {n}",
               role="body_sb", color="warning" if practice else "text")
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       self.trial_idx / n,
                       color="warning" if practice else "success",
                       label="practice" if practice else "scored")
        if sample is None:
            self.toasts.show("Face the camera", "warning", now=now)

    # ── fixation-stability block (Part 3) ─────────────────────────────────
    def screen_fix_intro(self, c: Canvas, now: float):
        w, h = c.w, c.h
        lines = FIX_INSTRUCTIONS
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph, alpha=CARD_PANEL_ALPHA)
        c.text(w // 2, py + 34, FIX_TITLE, role="h2", anchor="mm", color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        c.text(w // 2, py + 84 + len(lines) * 30,
               "Last part - about 12 seconds, then you're done.",
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, "I'm Ready", variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.hit(b):
            self.fixation = FixationAnalyzer(now, self.gaze_map.deadband)
            self.goto(FIX_HOLD, now)

    def screen_fixation(self, c: Canvas, now: float, pos: float | None,
                        sample: GazeSample | None):
        w, h = c.w, c.h
        rx = sample.ratio if sample is not None else None
        ry = sample.ratio_y if sample is not None else None
        self.fixation.update(now, pos, rx, ry)

        total = FIX_SETTLE_S + FIX_HOLD_S
        elapsed = now - self.fixation.t0
        frac = min(1.0, elapsed / total)

        # central cross with a filling ring — the progress cue doubles as the
        # fixation target (keep eyes here).
        self.draw_cross(c)
        c.ring(w // 2, h // 2, 46, "surface-2", thickness=4, alpha=0.5)
        c.ring(w // 2, h // 2, 46, "brand", thickness=4, sweep_deg=360 * frac)

        c.text(w // 2, h // 2 + 96, "Hold still - keep looking at the +",
               role="body_l", anchor="mm")
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       frac, color="brand", label="hold steady")
        if sample is None:
            self.toasts.show("Face the camera", "warning", now=now)

        if elapsed >= total:
            self.fix_result = self.fixation.finalize()
            self.recording_time += elapsed
            self._finish_run(now)

    def _finish_run(self, now: float):
        visible_ratio = (self.visible_frames / self.face_frames
                         if self.face_frames else 0.0)
        self.results = compute_metrics(self.block_results["pro"],
                                       self.block_results["anti"],
                                       face_visible_ratio=visible_ratio)
        self.audio.play(self.done_wav)
        gm = self.gaze_map
        raw = {
            "trials": self.raw_trials,
            "calibration": {"center": round(gm.center, 4),
                            "left": round(gm.left, 4),
                            "right": round(gm.right, 4),
                            "deadband": round(gm.deadband, 3)},
            "face_visible_ratio": round(visible_ratio, 3),
        }
        metrics = {k: v for k, v in self.results.items()
                   if k not in ("pro_block", "anti_block")}
        metrics["pro_block"] = self.results["pro_block"]
        metrics["anti_block"] = self.results["anti_block"]
        self._merge_fixation(metrics, raw)
        try:
            self.saved_path = save_session(
                test="oculomotor", mode="pro_anti", hand=None,
                duration_s=self.recording_time,
                device={"camera_fps": round(self.fps, 1),
                        "resolution": "640x480", "app_version": APP_VERSION},
                metrics=metrics, raw=raw)
        except OSError as e:
            self.saved_path = None
            print(f"[WARN] Could not save session: {e}")
        if self.results.get("error_rate_pct") is not None and self.results["scoreable"]:
            self.countup = CountUp(self.results["error_rate_pct"], time.time(),
                                   theme.DUR_SLOW)
        self.goto(COMPLETE, now)

    def _merge_fixation(self, metrics: dict, raw: dict) -> None:
        """Fold the fixation-stability readout into the saved metrics + raw
        trace. rms/bcea are rescaled so they survive the session's 2-decimal
        rounding and read naturally: rms as % of the eye-to-target distance,
        BCEA in ×10⁻³ relative units."""
        fr = self.fix_result
        if fr is None:
            return
        metrics["fixation_scoreable"] = fr.scoreable
        if fr.scoreable:
            metrics["fixation_rms_pct"] = fr.rms_jitter * 100
            metrics["fixation_bcea"] = fr.bcea * 1000 if fr.bcea is not None else None
            metrics["intrusion_count"] = fr.intrusion_count
            metrics["intrusion_rate_per_min"] = fr.intrusion_rate_per_min
            metrics["fixation_valid_s"] = fr.fixation_s
            metrics["fixation_status"] = fr.status
            metrics["fixation_label"] = fr.label
        else:
            metrics["fixation_reason"] = fr.reason
        raw["fixation"] = {
            "valid_ratio": round(fr.valid_ratio, 3),
            "n_samples": fr.n_samples,
            "intrusion_count": fr.intrusion_count,
            "series": [[round(t, 3), round(p, 3) if p is not None else None]
                       for t, p in self.fixation.series],
        }

    def screen_complete(self, c: Canvas, now: float):
        w, h = c.w, c.h
        r = self.results
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        bh = 42

        def fmt(v, unit="", nd=0):
            return "-" if v is None else f"{v:.{nd}f}{unit}"

        if r["scoreable"]:
            rows = [("Anti - Pro latency", fmt(r["anti_minus_pro_ms"], " ms")),
                    ("Corrected errors", fmt(r["corrected_rate_pct"], " %")),
                    ("Anti latency", fmt(r["antisaccade_latency_ms"], " ms")),
                    ("Pro latency", fmt(r["prosaccade_latency_ms"], " ms")),
                    ("Latency CV", fmt(r["latency_cv_pct"], " %", 1)),
                    ("Valid anti trials", f"{r['valid_anti_trials']}/{TASKS['anti'].n_trials}"),
                    ("Valid pro trials", f"{r['valid_pro_trials']}/{TASKS['pro'].n_trials}"),
                    ("Excluded (too early)", f"{r['anticipatory_count']}")]
            fr = self.fix_result
            if fr is not None and fr.scoreable:
                rows += [("Fixation jitter", fmt(fr.rms_jitter * 100, " %", 1)),
                         ("Gaze intrusions",
                          f"{fr.intrusion_count} ({fmt(fr.intrusion_rate_per_min, '/min')})")]
            nlines = (len(rows) + 1) // 2
            note_off = 190 + nlines * 24 + 6
            # Drop the secondary "short form" caveat when fixation rows are
            # present so the denser panel still fits a 480p canvas; the medical
            # disclaimer ribbon always remains.
            show_note2 = fr is None or not fr.scoreable
            y = note_off
            note2_off = (y := y + 20) if show_note2 else None
            saved_off = (y := y + 20) if self.saved_path else None
            btn_off = y + 26
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
        c.panel(px, py, pw, ph, alpha=CARD_PANEL_ALPHA)
        c.text(w // 2, py + 30, "Eye Movement Test - Results", role="h2",
               anchor="mm")

        if r["scoreable"]:
            val = self.countup.value(now) if self.countup else r["error_rate_pct"]
            c._dirty = True
            c.draw.text((w // 2, py + 90), f"{val:.0f}%",
                        font=get_font("mono", 56),
                        fill=theme.rgba(r["status"], 1.0), anchor="mm")
            c.text(w // 2, py + 126, "Anti-saccade errors (looked toward the dot)",
                   role="caption", color="text-muted", anchor="mm")
            c.badge(w // 2, py + 140, r["label"], r["status"])
            col_w = (pw - 3 * theme.SPACE[4]) // 2
            for i, (label, valstr) in enumerate(rows):
                rx = px + theme.SPACE[4] + (i % 2) * (col_w + theme.SPACE[4])
                ry = py + 190 + (i // 2) * 24
                c.text(rx, ry, label, role="caption", color="text-muted")
                c.text(rx + col_w, ry, valstr, role="caption", anchor="ra", mono=True)
            c.text(w // 2, py + note_off,
                   f"Typical < {ERROR_TYPICAL_PCT:.0f}% | monitor "
                   f"{ERROR_TYPICAL_PCT:.0f}-{ERROR_MONITOR_PCT:.0f}% | "
                   f"elevated > {ERROR_MONITOR_PCT:.0f}%",
                   role="caption", color="text-muted", anchor="mm")
            if note2_off is not None:
                c.text(w // 2, py + note2_off,
                       "Short screening form - fewer trials than a clinical test.",
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
        win = "Eye Movement Test  |  Q or window ✕ to quit"
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

            sample = self.detect_gaze(frame, now)
            pos = self.gaze_pos(sample)

            dim = DIM_BY_STATE.get(self.state)
            if dim:
                self.dim_frame(frame, dim)
            c = Canvas(frame)
            chips = [("Face detected", "success") if sample is not None
                     else ("Face the camera", "warning")]
            if self.fps < 24:
                chips.append((f"{self.fps:.0f} fps", "warning"))
            if self.state in (FIX_INTRO, FIX_HOLD):
                bar_title = FIX_TITLE
            elif self.state != IDLE:
                bar_title = self.task.title
            else:
                bar_title = ""
            c.status_bar(chips, bar_title)

            if self.state == IDLE:
                self.screen_idle(c, now, sample)
            elif self.state == INSTRUCTION:
                self.screen_instruction(c, now)
            elif self.state == CALIBRATION:
                self.screen_calibration(c, now, sample)
            elif self.state == COUNTDOWN:
                self.screen_countdown(c, now)
            elif self.state in (PRACTICE, RECORDING):
                self.screen_trials(c, now, pos, sample)
            elif self.state == FIX_INTRO:
                self.screen_fix_intro(c, now)
            elif self.state == FIX_HOLD:
                self.screen_fixation(c, now, pos, sample)
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
        self.tracker.close()
        self.audio.close()
        print("\n[INFO] Eye movement test closed.")


def main():
    # banner already printed by the splash, above the heavy imports
    if not Path(MODEL_PATH).exists():
        print("[ERROR] model/face_landmarker.task not found.")
        print("  Download: https://storage.googleapis.com/mediapipe-models/"
              "face_landmarker/face_landmarker/float16/latest/face_landmarker.task")
        sys.exit(1)
    source = select_camera_source()
    # 60 fps is requested at open time (finer saccade-latency resolution, §3.4)
    # and falls back silently to whatever the camera supports; setting it
    # afterwards would renegotiate the stream and flash the camera again.
    print("[INFO] Opening camera and loading the face model - a few seconds...")
    cap = open_capture(source, fps=60)
    if cap is None:
        print("[ERROR] Could not open camera.")
        sys.exit(1)
    App(cap).run()


if __name__ == "__main__":
    main()
