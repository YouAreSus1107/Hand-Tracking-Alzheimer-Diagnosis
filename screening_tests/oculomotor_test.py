"""
Oculomotor Test (Pro/Anti-saccade)
==================================
Webcam-only saccadic eye-movement screening (docs/tests/OCULOMOTOR_TEST_PLAN.md):

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
from core import i18n
from core.splash import Splash, GAZE_IMPORT_STEPS
_splash = Splash("Eye Movement Test (Pro/Anti-saccade)",
                 "Part 1: look toward - Part 2: look away - Part 3: hold still",
                 GAZE_IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
import numpy as np
_splash.step()               # OpenCV in

from core.hand_utils import preprocess_for_mediapipe
from core.camera import (select_camera_source, open_capture,
                         create_display_window, window_closed, pause_before_exit)
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.gaze.calibrate import GazeCalibrator, GazeMap
from core.gaze.detector import (SaccadeEnvelope, SaccadeTrial, SettleGate,
                                TrialResult)
from core.gaze.fixation import (FixationAnalyzer, FixationResult,
                                HOLD_S as FIX_HOLD_S, SETTLE_S as FIX_SETTLE_S)
from core.gaze.confidence import block_quality
from core.gaze.metrics import (compute_metrics, block_stats,
                               ERROR_TYPICAL_PCT, ERROR_MONITOR_PCT)
from core.gaze.openness import BLINK_FRAC, VERTICAL_FRAC
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
# A blink is ~0.15 s and every run is full of them, so the "eyes not readable"
# state is only surfaced once it has persisted well past one — otherwise the
# chip strobes and the coaching means nothing.
EYES_WARN_S = 0.7

# ── States ─────────────────────────────────────────────────────────────────
IDLE, INSTRUCTION, CALIBRATION, COUNTDOWN, PRACTICE, RECORDING, COMPLETE = (
    "idle", "instruction", "calibration", "countdown", "practice", "recording",
    "complete")
# Fixation-stability block (Part 3), after the anti block
FIX_INTRO, FIX_HOLD = "fix_intro", "fix_hold"
# Between-parts summary: what was recorded, and the offer to record it again.
PART_SUMMARY = "part_summary"
PART_KEYS = ("pro", "anti", "fix")

# Fixation intro copy (Part 3) — not a SaccadeTask, so kept beside the screen.
FIX_TITLE = "Part 3 - Hold Still"
FIX_INSTRUCTIONS = (
    "Keep your eyes on the + in the middle.",
    "Don't follow anything - just hold still",
    "and stare at the center until the ring fills.",
)

# Trial phases inside PRACTICE / RECORDING
FIXATION, GAP, TARGET, FEEDBACK = "fixation", "gap", "target", "feedback"

# Settle-gate pacing (the gate itself is core.gaze.detector.SettleGate). The
# dot is held back until the eye reads steady, capped so a person the tracker
# simply cannot hold still on is never stuck staring at a cross.
SETTLE_MAX_S = 2.5        # give up waiting and run the trial anyway
SETTLE_COACH_S = 1.5      # still waiting after this -> one coaching toast

# How much the video is dimmed per state. Applied once in the run loop, before
# the status bar is drawn, so the bar stays legible instead of being painted
# over. IDLE is absent: the user needs a clear view to frame their face.
DIM_BY_STATE = {
    CALIBRATION: DIM_ALPHA, COUNTDOWN: DIM_ALPHA, PRACTICE: DIM_ALPHA,
    RECORDING: DIM_ALPHA, FIX_HOLD: DIM_ALPHA,
    INSTRUCTION: CARD_DIM, FIX_INTRO: CARD_DIM, COMPLETE: CARD_DIM,
    PART_SUMMARY: CARD_DIM,
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
        self._eyes_bad_since: float | None = None
        self.eyes_stalled = False       # eyes unreadable for longer than a blink
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
        self.settle = SettleGate()
        # One envelope per block: the excursion a person produces looking away
        # is not the one they produce looking at, so the two must not pool.
        self.envelope: dict[str, SaccadeEnvelope] = {}
        self.dirs: list[int] = []
        self.trial_idx = 0
        self.last_result: TrialResult | None = None
        self.block_results: dict[str, list[TrialResult]] = {"pro": [], "anti": []}
        self.raw_trials: dict[str, list[dict]] = {"pro": [], "anti": []}
        # Run totals, banked from the per-attempt counters below when a part
        # is kept. A discarded attempt's frames must not dilute the kept run's
        # tracking ratio, which is why the two are separate.
        self.face_frames = 0
        self.visible_frames = 0
        self.gaze_frames = 0            # frames with a usable iris reading
        self.blk_face = 0
        self.blk_visible = 0
        self.blk_gaze = 0
        self._cal_noface = 0            # calibration stall causes, for coaching
        self._cal_shut = 0
        # Per-part attempts. `attempts` counts every attempt made (kept plus
        # discarded) so a redone part is never compared naively with a clean
        # one; `redo_used` spends the single redo each part is allowed.
        self.attempts = {k: 0 for k in PART_KEYS}
        self.redo_used = {k: False for k in PART_KEYS}
        self.discarded: dict[str, list[dict]] = {k: [] for k in PART_KEYS}
        self.summary_key = "pro"        # which part PART_SUMMARY is showing
        self.part_quality: dict = {}
        self._countdown_next = PRACTICE
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
    def _track_eye_state(self, sample: GazeSample | None, now: float) -> None:
        """Latch how long the iris has been unreadable while a face is tracked,
        so blinks (~0.15 s) don't flicker the chip or fire the coaching."""
        unreadable = sample is not None and sample.ratio is None
        if not unreadable:
            self._eyes_bad_since = None
        elif self._eyes_bad_since is None:
            self._eyes_bad_since = now
        self.eyes_stalled = (self._eyes_bad_since is not None
                             and now - self._eyes_bad_since >= EYES_WARN_S)

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
        """Iris + corner dots, drawn on the person's own eyes. The iris colour
        is the gate's verdict, so the fastest feedback loop in the test — move
        your lids, watch the dots change — needs no reading."""
        if sample is None:
            return
        color = "brand" if sample.ratio is not None else "warning"
        for (x, y) in sample.iris_px:
            c.dot(x, y, 3, color)
        for (x, y) in sample.corners_px:
            c.dot(x, y, 2, "surface-2")

    def eye_meter(self, c: Canvas, x: int, y: int, sample: GazeSample | None,
                  w: int = 236) -> None:
        """Lid-openness readout: how far this person's eyes are open relative
        to their *own* open baseline, with the blink gate marked on the track.

        Relative, not absolute, on purpose — a narrow palpebral fissure reads
        as fully open here, so the meter never nags somebody about the eyes
        they have. It only moves when their lids actually close on the shot.
        """
        h = 76
        c.panel(x, y, w, h)
        pad = theme.SPACE[2]
        c.text(x + pad, y + 16, i18n.t("Eye opening"), role="caption",
               color="text-muted")
        frac = sample.open_frac if sample is not None else None
        bar_w = w - 2 * pad
        bar_y = y + 36
        if frac is None:
            c.progress_bar(x + pad, bar_y, bar_w, 0.0, color="surface-2")
            msg, color = ((i18n.t("Face the camera"), "text-muted")
                          if sample is None else
                          (i18n.t("Looking for your eyes..."), "text-muted"))
        else:
            if sample.ratio is not None:
                status = "success" if frac >= VERTICAL_FRAC else "warning"
                msg = (i18n.t("Eyes tracked") if frac >= VERTICAL_FRAC
                       else i18n.t("Narrowing - open wider"))
            else:
                status = "danger"
                msg = i18n.t("Eyes read as closed")
            c.progress_bar(x + pad, bar_y, bar_w, min(1.0, frac), color=status)
            color = status
        # the gate itself, drawn on the track: everything left of the tick is
        # a frame the test has to throw away.
        tick = x + pad + int(bar_w * BLINK_FRAC)
        c.polyline([(tick, bar_y - 3), (tick, bar_y + 11)], "text-muted",
                   thickness=1, alpha=0.8)
        c.text(x + pad, y + 56, msg, role="caption", color=color)

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float, sample: GazeSample | None):
        self.draw_eye_markers(c, sample)
        w, h = c.w, c.h
        self.eye_meter(c, theme.SAFE_MARGIN, h - 26 - 12 - 76, sample)
        pw = min(540, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 140, 250
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, i18n.t("Eye Movement Test"), role="h1",
               anchor="mm")
        c.text(w // 2, py + 74,
               i18n.t("Measures how quickly and accurately your eyes"),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 98,
               i18n.t("respond - a marker studied in early cognitive decline."),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 128,
               i18n.t("Three short parts, about 3 minutes total."),
               role="body", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        b1 = c.button(px + theme.SPACE[4], py + 156, bw, 48,
                      i18n.t("Start Eye Movement Test"), variant="primary",
                      hovered=self.hover(px + theme.SPACE[4], py + 156, bw, 48),
                      icon="play")
        c.text(w // 2, py + 226,
               i18n.t("Sit about arm's length from the screen, "
                      "face the camera."),
               role="caption", color="text-muted", anchor="mm")
        c.disclaimer()
        if self.hit(b1):
            self.reset_run()
            self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        w, h = c.w, c.h
        task = self.task
        # keyed, not line by line: Chinese sets its own line breaks
        lines = i18n.tk(f"gaze.{task.key}.instructions", task.instructions)
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph, alpha=CARD_PANEL_ALPHA)
        c.text(w // 2, py + 34, i18n.t(task.title), role="h2", anchor="mm",
               color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        next_line = i18n.t(
            "Next: a quick calibration - just look at three dots."
            if self.gaze_map is None else
            "First a few practice tries, then the scored part.")
        c.text(w // 2, py + 84 + len(lines) * 30, next_line,
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, i18n.t("I'm Ready"), variant="success",
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
        if ratio is None:                    # why this frame was dropped
            if sample is None:
                self._cal_noface += 1
            else:
                self._cal_shut += 1
        advanced = cal.update(now, ratio)
        if advanced:
            self.audio.play(self.tick_wav)

        if cal.failed:
            self.toasts.show(i18n.t(cal.fail_reason), "warning", hold=3.0,
                             now=now)
            self.calibrator = GazeCalibrator(now)   # auto-restart
            self._cal_noface = self._cal_shut = 0
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
        c.text(w // 2, py + 28, i18n.t("Calibration: look at the glowing dot"),
               role="body_l", anchor="mm")
        c.text(w // 2, py + 54,
               i18n.t("Keep your head still - move only your eyes."),
               role="caption", color="text-muted", anchor="mm")
        c.progress_bar(px + theme.SPACE[4], py + 84, pw - 2 * theme.SPACE[4],
                       cal.progress, color="warning",
                       label=f"{int(cal.progress * 100)} %")
        self.draw_eye_markers(c, sample)
        self.eye_meter(c, theme.SAFE_MARGIN, 56, sample)
        if sample is None:
            self.toasts.show(i18n.t("Show your face to the camera"), "warning",
                             now=now)
        elif self.eyes_stalled:
            self.toasts.show(i18n.t("Your eyes are reading as closed - open "
                                    "them wide and hold"), "warning", now=now)
        elif cal.stage_timed_out(now):
            # A stalled stage has a cause, and the two have opposite fixes:
            # name whichever one has been eating the frames.
            if self._cal_shut > self._cal_noface:
                self.toasts.show(
                    i18n.t("Having trouble? Add light, and raise the camera "
                           "to eye level so your lids don't cover the iris"),
                    "info", hold=4.0, now=now)
            else:
                self.toasts.show(
                    i18n.t("Having trouble? Sit closer and add a little light"),
                    "info", hold=3.0, now=now)

    def screen_countdown(self, c: Canvas, now: float):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining <= 0:
            if self._countdown_next == RECORDING:
                self._countdown_next = PRACTICE
                self._start_recording(now)
            else:
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
        self.blk_face = self.blk_visible = self.blk_gaze = 0
        self.block_results[self.task.key] = []
        self.raw_trials[self.task.key] = []
        self._begin_fixation(now)
        self.goto(RECORDING, now)
        self.toasts.show(i18n.t("Scored part - keep going"), "info", now=now)

    def _count_frame(self, sample: GazeSample | None) -> None:
        """Tally one recorded frame against the current attempt."""
        self.blk_face += 1
        if sample is not None:
            self.blk_visible += 1
            if sample.ratio is not None:
                self.blk_gaze += 1

    def _valid_count(self, key: str) -> int:
        return sum(1 for r in self.block_results[key] if r.valid)

    def _needs_more_trials(self) -> bool:
        """Whether the scored block should run another trial.

        Past the planned count it keeps going only while short of usable
        trials — so an anticipated or blinked-through trial buys a replacement
        instead of costing the run. The stopping rule reads the *validity*
        count and never the error rate, so unlike stopping on the result it
        cannot bias the estimate.
        """
        task = self.task
        if self.trial_idx < task.n_trials:
            return True
        if not task.extends or self.trial_idx >= task.max_trials:
            return False
        return self._valid_count(task.key) < task.target_valid

    def _begin_fixation(self, now: float):
        self.phase = FIXATION
        self.phase_t0 = now
        self.fix_dur = self.rng.uniform(self.task.fixation_min_s,
                                        self.task.fixation_max_s)
        self.trial = None
        self.settle.reset()

    def _block_envelope(self) -> SaccadeEnvelope:
        """The confirm-threshold envelope for the block being run, seeded from
        calibration the first time it is asked for."""
        key = self.task.key
        if key not in self.envelope:
            self.envelope[key] = SaccadeEnvelope(self.gaze_map.deadband)
        return self.envelope[key]

    def _finish_trial(self, now: float, scored: bool):
        res = self.trial.finalize()
        self.last_result = res
        key = self.task.key
        # Practice trials feed the envelope too: by the time the block is
        # scored it already knows roughly how far this person's eyes travel.
        self._block_envelope().observe(res)
        if scored:
            self.block_results[key].append(res)
            self.raw_trials[key].append({
                "dir": res.target_dir,
                "outcome": res.outcome,
                # `is not None`, not a truth test: a 0.0 ms latency is the
                # signature of the failure this rework fixes, and storing it
                # as null hid it from the report drawer.
                "latency_ms": (round(res.latency_ms, 1)
                               if res.latency_ms is not None else None),
                # What the detector actually used, so the report draws the
                # lines that were in force (as tapping's threshold_series does).
                "baseline": round(res.baseline, 3),
                "onset_thr": round(res.onset_thr, 3),
                "confirm_thr": round(res.confirm_thr, 3),
                "series": [[round(t, 3), round(p, 3) if p is not None else None]
                           for t, p in self.trial.series],
            })
        self.trial = None
        if res.outcome == "correct" and not scored:
            self.audio.play(self.good_wav)

    def _advance_trial(self, now: float):
        self.trial_idx += 1
        if self.state == PRACTICE:
            if self.trial_idx < self.task.n_practice:
                self._begin_fixation(now)
            else:
                self._start_recording(now)
            return
        if self._needs_more_trials():
            # Replacement trials get their own count-balanced segment
            # rather than one long schedule truncated early: each segment is
            # balanced in itself, so stopping part-way through the second
            # leaves the run within ±4 of even sides on 20 trials.
            if self.trial_idx >= len(self.dirs):
                self.dirs += build_directions(
                    self.task.max_trials - self.task.n_trials, self.rng)
            self._begin_fixation(now)
            return
        # scored block finished
        self.recording_time += now - self._rec_t0
        self.audio.play(self.good_wav)
        self._show_part_summary(self.task.key, now)

    def _feedback_copy(self, res: TrialResult) -> tuple[str, str]:
        if res.outcome == "correct":
            return i18n.t("Correct"), "success"
        if res.outcome in ("error_uncorrected", "error_corrected"):
            return i18n.t("Look AWAY from the dot" if self.task.is_anti
                          else "Look AT the dot"), "warning"
        if res.outcome == "anticipatory":
            return i18n.t("A little early - wait for the dot"), "info"
        return i18n.t("Eyes not detected - face the camera"), "warning"

    def screen_trials(self, c: Canvas, now: float, pos: float | None,
                      sample: GazeSample | None):
        w, h = c.w, c.h
        practice = self.state == PRACTICE
        elapsed = now - self.phase_t0

        if self.state == RECORDING:
            self._count_frame(sample)

        if self.phase == FIXATION:
            self.draw_cross(c)
            # The jittered dwell is the *minimum* (the gap paradigm needs its
            # unpredictable foreperiod); past it the settle gate decides, so a
            # trial never starts with the eye still travelling back.
            self.settle.update(now, pos)
            if elapsed >= self.fix_dur and (self.settle.settled
                                            or elapsed >= SETTLE_MAX_S):
                self.phase, self.phase_t0 = GAP, now
            elif elapsed >= SETTLE_COACH_S and not self.settle.settled:
                self.toasts.show(i18n.t("Look back at the +"), "info", now=now)
        elif self.phase == GAP:
            if elapsed >= self.task.gap_s:
                self.phase, self.phase_t0 = TARGET, now
        elif self.phase == TARGET:
            direction = self.dirs[self.trial_idx]
            if self.trial is None:
                # t₀ = the frame the dot is first actually rendered (§3.2)
                self.trial = SaccadeTrial(now, direction,
                                          self._block_envelope().confirm_threshold(),
                                          self.task.is_anti,
                                          baseline=self.settle.baseline())
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

        # phase label + progress. Past the planned count the block is running
        # replacements, so the total and the bar's label change rather than
        # leaving a full bar sitting there looking stuck.
        task = self.task
        n = task.n_practice if practice else task.n_trials
        extending = not practice and self.trial_idx >= task.n_trials
        total = task.max_trials if extending else n
        label = i18n.t("Practice") if practice else i18n.t(task.title)
        c.text(theme.SAFE_MARGIN, 68,
               i18n.t("{label}  -  trial {n} of {total}", label=label,
                      n=min(self.trial_idx + 1, total), total=total),
               role="body_sb", color="warning" if practice else "text")
        if extending:
            bar_label, bar_color = i18n.t("replacing skipped trials"), "brand"
        elif practice:
            bar_label, bar_color = i18n.t("practice"), "warning"
        else:
            bar_label, bar_color = i18n.t("scored"), "success"
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       self.trial_idx / total, color=bar_color, label=bar_label)
        if sample is None:
            self.toasts.show(i18n.t("Face the camera"), "warning", now=now)
        elif self.eyes_stalled:
            self.toasts.show(i18n.t("Open your eyes wide - keep watching "
                                    "the dot"), "warning", now=now)

    # ── between-parts summary + redo ──────────────────────────────────────
    def _blk_gaze_ratio(self) -> float:
        return self.blk_gaze / self.blk_face if self.blk_face else 0.0

    def _part_rows(self, key: str) -> list[tuple[str, str]]:
        """The part's own numbers — no band, no verdict.

        The clinical call belongs on the final screen: showing it here would
        turn "redo this part" into a retry-until-green loop, and telling
        somebody mid-test that their result looks elevated is its own harm.
        """
        pct = f"{self._blk_gaze_ratio() * 100:.0f} %"
        if key == "fix":
            fr = self.fix_result
            if fr is None or not fr.scoreable:
                return [(i18n.t("Hold recorded"), i18n.t("not enough data")),
                        (i18n.t("Eyes readable"), pct)]
            return [(i18n.t("Fixation jitter"), f"{fr.rms_jitter * 100:.1f} %"),
                    (i18n.t("Tracked"), f"{fr.valid_ratio * 100:.0f} %"),
                    (i18n.t("Eyes readable"), pct),
                    (i18n.t("Gaze intrusions"), f"{fr.intrusion_count}")]
        st = block_stats(self.block_results[key])
        rows = []
        if key == "anti":
            rows.append((i18n.t("Looked toward the dot"),
                         f"{st['errors']}/{st['valid']}"))
        elif st["mean_latency_ms"] is not None:
            rows.append((i18n.t("Mean latency"),
                         f"{st['mean_latency_ms']:.0f} ms"))
        rows += [(i18n.t("Valid trials"), f"{st['valid']}/{st['trials']}"),
                 (i18n.t("Eyes readable"), pct),
                 (i18n.t("Started too early"), f"{st['anticipatory']}")]
        return rows

    def _show_part_summary(self, key: str, now: float):
        self.attempts[key] += 1
        if key == "fix":
            fr = self.fix_result
            support = fr.valid_ratio if fr is not None else 0.0
            excluded_frac = 0.0
        else:
            st = block_stats(self.block_results[key])
            support = (st["valid"] / TASKS[key].n_trials
                       if TASKS[key].n_trials else 0.0)
            excluded_frac = ((st["trials"] - st["valid"]) / st["trials"]
                             if st["trials"] else 0.0)
        self.part_quality = block_quality(
            support=support, excluded_frac=excluded_frac,
            gaze_valid_ratio=self._blk_gaze_ratio())
        self.summary_key = key
        self.goto(PART_SUMMARY, now)

    def _part_title(self, key: str) -> str:
        return i18n.t(FIX_TITLE if key == "fix" else TASKS[key].title)

    def _bank_attempt(self):
        """Fold the kept attempt's frames into the run totals."""
        self.face_frames += self.blk_face
        self.visible_frames += self.blk_visible
        self.gaze_frames += self.blk_gaze
        self.blk_face = self.blk_visible = self.blk_gaze = 0

    def _discard_attempt(self, key: str):
        """Set the attempt aside — kept in the session, out of the score.

        Nothing is deleted: a block full of anticipations is real data about
        this patient, and the saved recording says how many attempts it took.
        """
        record = {"attempt": self.attempts[key],
                  "quality_pct": round(self.part_quality.get("quality_pct", 0.0), 1),
                  "gaze_valid_ratio": round(self._blk_gaze_ratio(), 3)}
        if key == "fix":
            record["series"] = [[round(t, 3),
                                 round(pos, 3) if pos is not None else None]
                                for t, pos in self.fixation.series]
            self.fix_result = None
        else:
            record["trials"] = self.raw_trials[key]
            self.block_results[key] = []
            self.raw_trials[key] = []
        self.discarded[key].append(record)
        self.blk_face = self.blk_visible = self.blk_gaze = 0
        self.redo_used[key] = True

    def screen_part_summary(self, c: Canvas, now: float):
        w, h = c.w, c.h
        key = self.summary_key
        rows = self._part_rows(key)
        q = self.part_quality
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 96 + len(rows) * 26 + 10 + 62 + 62
        px, py = (w - pw) // 2, max(56, (h - ph) // 2)
        c.panel(px, py, pw, ph, alpha=CARD_PANEL_ALPHA)
        c.text(w // 2, py + 32,
               i18n.t("{part} recorded", part=self._part_title(key)),
               role="h2", anchor="mm", color="brand")
        c.text(w // 2, py + 62,
               i18n.t("How this part was recorded - your result comes at "
                      "the end."),
               role="caption", color="text-muted", anchor="mm")
        inner = pw - 2 * theme.SPACE[4]
        for i, (label, val) in enumerate(rows):
            ry = py + 90 + i * 26
            c.text(px + theme.SPACE[4], ry, label, role="caption",
                   color="text-muted")
            c.text(px + theme.SPACE[4] + inner, ry, val, role="caption",
                   anchor="ra", mono=True)
        qp = q.get("quality_pct", 0.0)
        q_status = "success" if qp >= 75 else "info" if qp >= 45 else "warning"
        q_level = "Good" if qp >= 75 else "Fair" if qp >= 45 else "Poor"
        card_y = py + 90 + len(rows) * 26 + 8
        c.confidence_card(px + theme.SPACE[4], card_y, inner,
                          label=i18n.t("Recording quality"),
                          value=i18n.t("{pct}% - {level}", pct=f"{qp:.0f}",
                                       level=i18n.t(q_level)),
                          detail=i18n.t(q["reasons"][0]) if q.get("reasons") else "",
                          progress=qp / 100.0, status=q_status)
        by = card_y + 62
        bw = (inner - theme.SPACE[3]) // 2
        spent = self.redo_used[key]
        # A spent redo greys out where it was rather than vanishing: a button
        # that disappears reads as a bug, and nobody hunts for what is not there.
        redo = c.button(px + theme.SPACE[4], by, bw, 48,
                        i18n.t("Redo used") if spent
                        else i18n.t("Redo this part"),
                        variant="ghost",
                        hovered=not spent and self.hover(px + theme.SPACE[4],
                                                         by, bw, 48))
        nx = px + theme.SPACE[4] + bw + theme.SPACE[3]
        nxt = c.button(nx, by, bw, 48,
                       i18n.t("Finish") if key == "fix" else i18n.t("Next part"),
                       variant="success", hovered=self.hover(nx, by, bw, 48),
                       icon="check")
        c.disclaimer()
        if not spent and self.hit(redo):
            self._redo_part(key, now)
        elif self.hit(nxt):
            self._keep_part(key, now)

    def _redo_part(self, key: str, now: float):
        self._discard_attempt(key)
        if key == "fix":
            self.fixation = FixationAnalyzer(now, self.gaze_map.deadband)
            self.goto(FIX_HOLD, now)
            return
        # Straight back to the scored trials: practice and calibration are
        # already done, and re-running them is most of what made this test long.
        self._countdown_next = RECORDING
        self.goto(COUNTDOWN, now)

    def _keep_part(self, key: str, now: float):
        self._bank_attempt()
        if key == "pro":
            self.block_i += 1
            self.goto(INSTRUCTION, now)
        elif key == "anti":
            self.goto(FIX_INTRO, now)
        else:
            self._finish_run(now)

    # ── fixation-stability block (Part 3) ─────────────────────────────────
    def screen_fix_intro(self, c: Canvas, now: float):
        w, h = c.w, c.h
        lines = i18n.tk("gaze.fix.instructions", FIX_INSTRUCTIONS)
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph, alpha=CARD_PANEL_ALPHA)
        c.text(w // 2, py + 34, i18n.t(FIX_TITLE), role="h2", anchor="mm",
               color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 78 + i * 30, line, role="body_l", anchor="mm")
        c.text(w // 2, py + 84 + len(lines) * 30,
               i18n.t("Last part - about 12 seconds, then you're done."),
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, i18n.t("I'm Ready"), variant="success",
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
        self._count_frame(sample)

        total = FIX_SETTLE_S + FIX_HOLD_S
        elapsed = now - self.fixation.t0
        frac = min(1.0, elapsed / total)

        # central cross with a filling ring — the progress cue doubles as the
        # fixation target (keep eyes here).
        self.draw_cross(c)
        c.ring(w // 2, h // 2, 46, "surface-2", thickness=4, alpha=0.5)
        c.ring(w // 2, h // 2, 46, "brand", thickness=4, sweep_deg=360 * frac)

        c.text(w // 2, h // 2 + 96,
               i18n.t("Hold still - keep looking at the +"),
               role="body_l", anchor="mm")
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       frac, color="brand", label=i18n.t("hold steady"))
        if sample is None:
            self.toasts.show(i18n.t("Face the camera"), "warning", now=now)
        elif self.eyes_stalled:
            self.toasts.show(i18n.t("Open your eyes wide - keep looking at "
                                    "the +"), "warning", now=now)

        if elapsed >= total:
            self.fix_result = self.fixation.finalize()
            self.recording_time += elapsed
            self.audio.play(self.good_wav)
            self._show_part_summary("fix", now)

    def _finish_run(self, now: float):
        visible_ratio = (self.visible_frames / self.face_frames
                         if self.face_frames else 0.0)
        # Distinct from face visibility: the face can be in frame the whole
        # run while the lids hide the iris, and only this ratio shows it.
        gaze_ratio = (self.gaze_frames / self.face_frames
                      if self.face_frames else 0.0)
        self.results = compute_metrics(self.block_results["pro"],
                                       self.block_results["anti"],
                                       face_visible_ratio=visible_ratio,
                                       gaze_valid_ratio=gaze_ratio,
                                       camera_fps=self.fps,
                                       attempts=dict(self.attempts))
        self.audio.play(self.done_wav)
        gm = self.gaze_map
        raw = {
            "trials": self.raw_trials,
            "calibration": {"center": round(gm.center, 4),
                            "left": round(gm.left, 4),
                            "right": round(gm.right, 4),
                            "deadband": round(gm.deadband, 3)},
            "face_visible_ratio": round(visible_ratio, 3),
            "gaze_valid_ratio": round(gaze_ratio, 3),
        }
        # Abandoned attempts ride along under their own key, so a reader that
        # only knows about `trials` sees exactly what it always did.
        discarded = {k: v for k, v in self.discarded.items() if v}
        if discarded:
            raw["discarded_attempts"] = discarded
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
                    ("Started too early", f"{r['anticipatory_count']}")]
            if r.get("gaze_valid_ratio", 1.0) < 0.9:
                rows.append(("Eyes readable",
                             fmt(r["gaze_valid_ratio"] * 100, " %")))
            fr = self.fix_result
            if fr is not None and fr.scoreable:
                rows += [("Fixation jitter", fmt(fr.rms_jitter * 100, " %", 1)),
                         ("Gaze intrusions",
                          f"{fr.intrusion_count} ({fmt(fr.intrusion_rate_per_min, '/min')})")]
            redone = [k for k, n in (r.get("attempts") or {}).items() if n > 1]
            if redone:
                rows.append(("Parts re-recorded", f"{len(redone)}"))
            # Three columns and a hard cap, as the tapping screen does: the
            # confidence card needs vertical room, and two columns of ten rows
            # leave none of it on a 480p canvas. Rows are ordered by what a
            # reader needs first, so the cap drops the least important.
            rows = rows[:9]
            nlines = (len(rows) + 2) // 3
            metrics_off = 224
            note_off = metrics_off + nlines * 22 + 4
            y = note_off
            edge_off = (y := y + 18) if r.get("band_edge") else None
            saved_off = (y := y + 18) if self.saved_path else None
            btn_off = y + 26
        else:
            reason = r["reason"] or "Something went wrong - please try again."
            # i18n.wrap, not split(): Chinese has no spaces to break on.
            lines = i18n.wrap(i18n.t(reason), 48)[:3]
            btn_off = 108 + len(lines) * 26 + 12
        ph = btn_off + bh + 14

        px, py = (w - pw) // 2, max(56, (h - ph) // 2)
        c.panel(px, py, pw, ph, alpha=CARD_PANEL_ALPHA)
        c.text(w // 2, py + 30, i18n.t("Eye Movement Test - Results"),
               role="h2", anchor="mm")

        if r["scoreable"]:
            val = self.countup.value(now) if self.countup else r["error_rate_pct"]
            c._dirty = True
            c.draw.text((w // 2, py + 84), f"{val:.0f}%",
                        font=get_font("mono", 56),
                        fill=theme.rgba(r["status"], 1.0), anchor="mm")
            c.text(w // 2, py + 116,
                   i18n.t("Anti-saccade errors (looked toward the dot)"),
                   role="caption", color="text-muted", anchor="mm")
            c.badge(w // 2, py + 130, i18n.t(r["label"]), r["status"])
            # The interval rides in the card's detail slot rather than taking a
            # line of its own — it is a statement about the same measurement.
            ci_lo, ci_hi = r.get("error_ci_low_pct"), r.get("error_ci_high_pct")
            ci_text = ("" if ci_lo is None or ci_hi is None else
                       i18n.t("95% CI {low}-{high}%", low=f"{ci_lo:.0f}",
                              high=f"{ci_hi:.0f}"))
            conf = r.get("confidence_pct") or 0
            # Confidence is recording quality, not a second clinical verdict.
            # Moderate therefore uses neutral info blue; only low quality warns.
            conf_status = ("success" if conf >= 75 else
                           "info" if conf >= 45 else "warning")
            conf_level = ("High" if conf >= 75 else
                          "Moderate" if conf >= 45 else "Low")
            conf_w = min(330, pw - 2 * theme.SPACE[4])
            c.confidence_card(
                # Verdict badge occupies y=130..164; keep a true 8 px gap.
                px + (pw - conf_w) // 2, py + 172, conf_w,
                label=i18n.t("Measurement confidence"),
                value=i18n.t("{level} - {pct}%", level=i18n.t(conf_level),
                             pct=f"{conf:.0f}"),
                detail=ci_text,
                progress=conf / 100.0, status=conf_status)
            col_w = (pw - 4 * theme.SPACE[4]) // 3
            for i, (label, valstr) in enumerate(rows):
                rx = px + theme.SPACE[4] + (i % 3) * (col_w + theme.SPACE[4])
                ry = py + metrics_off + (i // 3) * 22
                c.text(rx, ry, i18n.t(label), role="caption",
                       color="text-muted")
                c.text(rx + col_w, ry, valstr, role="caption", anchor="ra", mono=True)
            c.text(w // 2, py + note_off,
                   i18n.t("Typical < {typical}% | monitor {typical}-{monitor}% "
                          "| elevated > {monitor}%",
                          typical=f"{ERROR_TYPICAL_PCT:.0f}",
                          monitor=f"{ERROR_MONITOR_PCT:.0f}"),
                   role="caption", color="text-muted", anchor="mm")
            if edge_off is not None:
                c.text(w // 2, py + edge_off,
                       i18n.t("Close to a band edge - repeat for a firmer "
                              "reading."),
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
            self._track_eye_state(sample, now)

            dim = DIM_BY_STATE.get(self.state)
            if dim:
                self.dim_frame(frame, dim)
            c = Canvas(frame)
            # Three states, not two: a tracked face whose eyes are shut yields
            # no gaze at all, and the old chip called that "Face detected" —
            # green, while the run quietly collected nothing.
            if sample is None:
                chips = [(i18n.t("Face the camera"), "warning")]
            elif self.eyes_stalled:
                chips = [(i18n.t("Eyes not readable"), "warning")]
            else:
                chips = [(i18n.t("Eyes tracked"), "success")]
            if self.fps < 24:
                chips.append((f"{self.fps:.0f} fps", "warning"))
            if self.state == PART_SUMMARY:
                bar_title = self._part_title(self.summary_key)
            elif self.state in (FIX_INTRO, FIX_HOLD):
                bar_title = i18n.t(FIX_TITLE)
            elif self.state != IDLE:
                bar_title = i18n.t(self.task.title)
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
            elif self.state == PART_SUMMARY:
                self.screen_part_summary(c, now)
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
        pause_before_exit()
        sys.exit(1)
    source = select_camera_source()
    # 60 fps is requested at open time (finer saccade-latency resolution, §3.4)
    # and falls back silently to whatever the camera supports; setting it
    # afterwards would renegotiate the stream and flash the camera again.
    print("[INFO] Opening camera and loading the face model - a few seconds...")
    cap = open_capture(source, fps=60)
    if cap is None:
        print("[ERROR] Could not open camera.")
        pause_before_exit()
        sys.exit(1)
    App(cap).run()


if __name__ == "__main__":
    main()
