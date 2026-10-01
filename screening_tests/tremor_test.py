"""
Hand Tremor Test
================
Three 20-second holds with both hands in view, measured for a rhythmic
3.5-12 Hz oscillation. See docs/tests/TREMOR_TEST_PLAN.md.

  1. Palms Up in Your Lap    hands resting in the lap, palms up (rest tremor)
  2. Palms Down in Your Lap  the same, palms down — both sides of the hand
  3. Arms Held Out           both arms out, palms down (postural tremor)

The rest holds are in the lap, fully supported, as a neurologist examines
rest tremor. That needs a camera aimed down at the lap (an external webcam or,
later, a phone); a laptop's own camera on the table cannot see it.

Both hands are tracked at once, because a parkinsonian rest tremor usually
starts on one side and the left/right difference is itself the finding.

Headline (core/tremor/metrics.py): the tremor-band movement at the peak, as
RMS % of the hand's own length, with the peak frequency. **Frequency is the
trusted number** — video tremor frequency matches accelerometers to ~0.2 Hz;
video amplitude is an estimate (plan §1).

When the sensor glove is plugged in, its IMU is recorded beside the camera
for every hold, and the glove's peak frequency is saved next to the camera's:
that difference is how this test gets validated (plan §5). No glove, no
change — the test runs camera-only.

Record now, measure after (docs/tests/TREMOR_RESTRUCTURE_PLAN.md §4). A
thread owns the camera (core/capture.FrameRecorder) and keeps every frame of
each hold; live, MediaPipe only gets the hands into position and drives the
prompts. When a hold ends, core/tremor/offline.py measures every recorded
frame -- MediaPipe, framing trust and OPTICAL FLOW seeded from that frame's
own landmarks -- in the background while the next hold is explained, pausing
whenever a hold is being captured. Whatever is left after the last hold is
handed to a worker process (`--finish`, core/pending.py) and the test exits,
so the camera and the hub are free while it measures; the worker saves the
session and the hub shows it when it lands. If the hand-off fails, an
Analysing screen finishes here instead (core/tremor/finish.py serves both).
The hand-off is the one moment frames touch the disk: a job file in the
system temp folder, deleted as soon as the worker has read it. So a 60 fps camera gives the full 3.5-12 Hz band whatever rate the
laptop manages live. The flow is scored; the RAW landmarks take over for a
hold the flow could not measure (the One-Euro smoothing used to draw the hand
would erase a tremor); the live landmark cells are the last resort if the
offline pass fails. Frames where a hand is at the edge of the picture are left
out (core/framing.py). Frames are otherwise in memory only and are dropped
after analysis; `--keep-frames` (developer use, never from the hub) writes them to
recordings/ so a recording can be re-analysed.

This file is the run loop + rendering only; the engine lives in core/tremor/.
Results auto-save to results/ as JSON + a CSV index row.

Run:  python screening_tests/tremor_test.py     Quit: press 'q'
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))  # keep first: hand_utils import path

# Stdlib-only, and above the heavy imports on purpose: cv2 + mediapipe take
# ~2 s warm and ~10 s cold, and nothing reaches the console until they land.
from core import i18n
from core.splash import Splash, IMPORT_STEPS
_splash = Splash("Hand Tremor Test",
                 "Click 'Start Test' in the camera window.  Q to quit.",
                 IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
import numpy as np
_splash.step()               # OpenCV in
from core import quiet       # keep above mediapipe: silences its startup log
import mediapipe as mp
_splash.step()               # MediaPipe in

from core.hand_utils import preprocess_for_mediapipe
from core.camera import (capture_info, select_camera_source, open_capture,
                         create_display_window, show, set_mouse_callback,
                         window_closed, pause_before_exit)
from core.screen_recorder import ScreenRecorder
from core.mirror_check import ensure_orientation
from core import pending, profiles
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.ui import theme
from core.ui.anim import ease_out_cubic, lerp
from core.ui.coach import Coach, PRI_HAND
from core.ui.components import Canvas, get_font, bare_view
from core.ui.keys import OVERLAY_HIDDEN_HINT, TOGGLE_OVERLAY
from core import framing
from core.ui.framing_ui import draw_framing
from core.capture import FrameRecorder
from core.tremor import metrics as tm
from core.tremor.finish import finish_run
from core.tremor.flow_view import LiveFlowView
from core.tremor.offline import OfflineAnalyser, assign_hands, detect_half
from core.tremor.phases import PHASES, PHASE_ORDER, HANDS

_splash.done()   # imports are in; the camera prompt follows immediately

APP_VERSION = "0.3.0"          # 0.2: optical flow; 0.3: offline pass, every frame
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

# ── Test Configuration ────────────────────────────────────────────────────
COUNTDOWN_FROM = 3
POSITION_HOLD_S = 1.5        # both hands trusted this long before a hold starts
GLOVE_BANNER_WAIT_S = 2.5    # how long to wait for the board to announce itself
KEY_ADVANCE = (13, 32)       # Enter / Space press the screen's main button
HANDED_SHOW_S = 6.0          # the "measuring in the background" card, then exit

# ── States ────────────────────────────────────────────────────────────────
(IDLE, INSTRUCTION, POSITION, COUNTDOWN, RECORDING, ANALYSING, COMPLETE) = (
    "idle", "instruction", "position", "countdown", "recording", "analysing",
    "complete")
#: After the last hold: the unfinished holds are being written out for the
#: background worker (SAVING), then the camera is released and a closing card
#: says where the results will appear (HANDED). ANALYSING/COMPLETE are the
#: in-process path, used when the hand-off cannot happen.
SAVING, HANDED = "saving", "handed"
#: The offline pass waits while these run, so it never competes with the
#: capture of the hold it is about to measure.
QUIET_STATES = (COUNTDOWN, RECORDING)

HAND_NAMES = {"left": "Left hand", "right": "Right hand"}


def _finding(r: dict) -> str:
    """The run's finding in words, in place of a coloured verdict."""
    if r.get("tremor_peak_hz") is None:
        return "No rhythmic shaking found"
    if r.get("status") == "warning":
        return "A weak rhythm - repeat to confirm"
    return "Rhythmic shaking found"
PHASE_SHORT = {"rest_palm_up": "Palms up", "rest_palm_down": "Palms down",
               "postural": "Arms out"}


# ── Glove (optional) ──────────────────────────────────────────────────────

def open_glove():
    """The sensor glove's reader when a board with a live IMU is plugged in,
    else None. Never raises and never blocks the test: every failure leaves
    it camera-only with one console line saying why."""
    try:
        from core.glove.serial_io import GloveReader, default_port, has_pyserial
    except Exception as e:  # noqa: BLE001 - an optional lane must not crash the test
        print(f"[INFO] Glove support unavailable ({e}) - camera only.")
        return None
    if not has_pyserial():
        print("[INFO] pyserial not installed - camera only.")
        return None
    port = default_port()
    if not port:
        print("[INFO] No sensor glove plugged in - camera only.")
        return None
    reader = GloveReader(str(_REPO_ROOT / "results"))
    ok, msg = reader.connect(port)
    if not ok:
        print(f"[INFO] Glove not used: {msg}")
        return None
    t_end = time.time() + GLOVE_BANNER_WAIT_S
    while time.time() < t_end and reader.imu_name() is None:
        time.sleep(0.1)
    if reader.imu_name() is None:
        print("[INFO] The glove reports no IMU - camera only.")
        reader.disconnect()
        return None
    print(f"[INFO] Sensor glove on {port} ({reader.imu_name()}) - "
          "recording its IMU beside the camera.")
    return reader


def make_landmarker(num_hands: int = 2):
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.55,
    )
    with quiet.muted_native_stderr():
        return mp.tasks.vision.HandLandmarker.create_from_options(options)


def detect_factory(make_lm=None):
    """make_detect() for the offline pass: each call gives (detect, close[,
    side_detect]) for one hold.

    With the real model (make_lm None) it also brings one single-hand
    landmarker per side, for a hand the whole frame misses
    (offline.detect_half): with both hands in view MediaPipe can lock onto
    one and never find the other (TREMOR_TEST_PLAN.md §3c). A scripted
    landmarker (the run-loop harness) answers the same whatever it is shown,
    so it gets no halves."""
    real = make_lm is None
    make_lm = make_lm or make_landmarker

    def wrap(inst):
        def detect(rgb, ts_ms):
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            return inst.detect_for_video(img, ts_ms)
        return detect

    def make_detect():
        lm = make_lm()
        if not real:
            return wrap(lm), lm.close
        sides = {h: make_landmarker(num_hands=1) for h in HANDS}

        def close():
            for inst in (lm, *sides.values()):
                inst.close()
        return wrap(lm), close, {h: wrap(inst) for h, inst in sides.items()}
    return make_detect


# ── Background finish (core/pending.py) ───────────────────────────────────

def spawn_worker(job_dir: Path) -> None:
    """Start `tremor_test.py --finish <job_dir>`: no window, below-normal
    priority (the next test's live loop comes first), its own process group
    so closing this test's console does not take it down, and its console
    written to the job's log."""
    log = open(Path(job_dir) / pending.LOG, "ab")
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = (subprocess.CREATE_NO_WINDOW
                               | subprocess.CREATE_NEW_PROCESS_GROUP
                               | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    else:
        kw["start_new_session"] = True
    env = dict(os.environ, PYTHONUNBUFFERED="1", NO_COLOR="1")
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--finish",
             str(job_dir)],
            cwd=str(_REPO_ROOT), env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, close_fds=True, **kw)
    finally:
        log.close()


def run_job(job_dir, make_detect=None, save=None) -> dict | None:
    """The worker: measure the holds the test handed over, then score and
    save exactly as the test would have (core/tremor/finish.py). Progress
    and the outcome go to the job's status for the hub; the frames are
    deleted whatever happens. Returns finish_run()'s result, or None."""
    job_dir = Path(job_dir)
    make_detect = make_detect or detect_factory()
    save = save or save_session
    beat = None
    try:
        with open(job_dir / pending.JOB, "rb") as f:
            payload = pickle.load(f)
        (job_dir / pending.JOB).unlink()        # the frames now live in memory only
        job = payload["job"]
        # --keep-frames reaches the holds measured here too
        analyser = OfflineAnalyser(make_detect, hands=job["hands"],
                                   keep_dir=payload.get("keep_dir"))
        analyser.results.update(payload["results"])
        analyser.errors.update(payload["errors"])
        for key, take, window, move_max in payload.pop("todo"):
            analyser.submit(key, take, window, move_max)
        beat = pending.Heartbeat(job_dir, analyser.progress)
        beat.start()
        analyser.start()
        while not analyser.idle():
            time.sleep(0.1)
        analyser.stop()
        print("[INFO] Offline pass done: "
              f"{sorted(analyser.results)} measured, errors {analyser.errors or 'none'}")
        out = finish_run(job, analyser.results, analyser.errors, save=save)
        beat.stop()
        beat = None
        if out["saved_path"] is None:
            pending.fail(job_dir, "The results could not be saved.")
        else:
            pending.done(job_dir, session=Path(out["saved_path"]).name)
            print(f"[INFO] Saved {out['saved_path']}")
        return out
    except Exception as e:  # noqa: BLE001 - the hub must hear about any failure
        traceback.print_exc()
        if beat is not None:
            beat.stop()
        try:
            pending.fail(job_dir, f"{type(e).__name__}: {e}")
        except OSError:
            pass
        return None


class App:
    def __init__(self, cap, glove=None, landmarker_factory=None,
                 keep_dir: Path | None = None, background: bool | None = None,
                 spawn=None):
        self.cap = cap
        self.glove = glove
        # The live instance and a fresh one per hold for the offline pass
        # come from one factory (the run-loop harness passes its own).
        self.make_landmarker = landmarker_factory or make_landmarker
        self.landmarker = self.make_landmarker()
        # One single-hand landmarker per side for a hand the whole frame
        # misses, live as offline (offline.detect_half); real model only.
        self.side_landmarkers = ({h: make_landmarker(num_hands=1) for h in HANDS}
                                 if self.make_landmarker is make_landmarker else {})
        self.recorder = FrameRecorder(cap)       # owns cap.read() from run()
        self._make_detect = detect_factory(landmarker_factory)
        self.keep_dir = keep_dir
        self.analyser = OfflineAnalyser(self._make_detect, hands=HANDS,
                                        keep_dir=keep_dir)
        # Finish in a worker process after the last hold, so the camera and
        # the hub's slot are free while it measures. Off by default for a
        # scripted landmarker: a worker process could not use it. A harness
        # that wants the hand-off passes background=True and its own spawn.
        self.background = (landmarker_factory is None if background is None
                           else background)
        self.spawn = spawn or spawn_worker
        self._handoff: tuple | None = None       # set by the hand-off thread
        self._handoff_thread: threading.Thread | None = None
        self._handed_at = 0.0
        self.camera_closed = False
        self.audio = AudioWorker()
        self.start_wav = build_tone(880, 100)
        self.tick_wav = build_tone(660, 60)
        self.done_wav = build_tone(523, 180)

        self.state = IDLE
        self.coach = Coach()           # the one place prompts appear
        # what the test measures, drawn live instead of MediaPipe's skeleton
        self.flow_view = LiveFlowView(HANDS)
        self.monitors = {h: framing.FramingMonitor() for h in HANDS}
        self.hands: dict[str, dict] = {}

        self.mouse = (0, 0)
        self.click: tuple[int, int] | None = None
        self.overlay_hidden = False
        self.advance = False
        self.glove_hand: str | None = None   # which hand wears the glove
        self.fps = 30.0
        self._last_frame_t: float | None = None
        self.frame_size = (640, 480)
        self.reset_run()

    # ── run-scoped state ──────────────────────────────────────────────────
    def reset_run(self):
        self.phase_i = 0
        self.t_state = time.time()
        self.record_start = 0.0
        self._pos_since: float | None = None
        # {phase: {hand: {"t": [], "pts": [], "len": []}}}
        # Live landmarks: the fallback. finish_run() replaces each hold's
        # with the offline pass's own when it succeeds, since those are
        # what get scored (core/tremor/finish.py).
        self.data = {p: {h: {"t": [], "pts": [], "len": []} for h in HANDS}
                     for p in PHASE_ORDER}
        self.cells: dict = {}            # the cells scored
        self.cells_live: dict = {}       # the live landmark cells, for comparison
        self.glove_cells: dict = {}
        if self.analyser.idle():
            self.analyser.reset()
        self.windows: dict = {}             # {phase: (t0, t1)} scored window
        self.clip_frames = self.all_frames = 0
        self.results = None
        self.saved_path = None

    @property
    def phase(self):
        return PHASES[PHASE_ORDER[self.phase_i]]

    def goto(self, state: str, now: float):
        self.state = state
        self.t_state = now
        self.coach.clear()       # a prompt never outlives its screen

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

    def pressed(self, rect) -> bool:
        """The screen's main button: clicked, or Enter/Space — the hands are
        meant to stay put, and reaching for the mouse between holds moves them."""
        return self.hit(rect) or self.advance

    def hover(self, x, y, w, h) -> bool:
        mx, my = self.mouse
        return x <= mx <= x + w and y <= my <= y + h

    # ── per-frame pipeline ────────────────────────────────────────────────
    def detect_hands(self, frame, now: float) -> dict[str, dict]:
        """{"left"|"right": {"raw": 21 (x, y) normalised}}.
        Which hand is which: core/tremor/offline.assign_hands, the rule the
        offline pass uses too."""
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        out: dict[str, dict] = {}
        found = assign_hands(result, HANDS)
        for h, inst in self.side_landmarkers.items():
            if h not in found:
                other = next((v for k, v in found.items() if k != h), None)

                def one(crop, ms, inst=inst):
                    return inst.detect_for_video(
                        mp.Image(image_format=mp.ImageFormat.SRGB, data=crop), ms)
                lms = detect_half(rgb, h, one, int(now * 1000), other)
                if lms is not None:
                    found[h] = lms
        for label, lms in found.items():
            out[label] = {"raw": [(lm.x, lm.y) for lm in lms]}
        return out

    def both_trusted(self) -> bool:
        return all(h in self.hands and not self.monitors[h].untrusted
                   for h in HANDS)

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(540, w - 2 * theme.SAFE_MARGIN)
        # with a glove: one more line and the which-hand choice
        extra = 64 if self.glove is not None else 0
        px, py, ph = (w - pw) // 2, h // 2 - 128 - extra // 2, 236 + extra
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, i18n.t("Hand Tremor Test"), role="h1",
               anchor="mm")
        c.text(w // 2, py + 74,
               i18n.t("Three 20-second holds with both hands in view."),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 98,
               i18n.t("Measures shaking at rest and with arms held out."),
               role="body", color="text-muted", anchor="mm")
        # The rest holds are in the lap, which a laptop's own camera on the
        # table cannot see: say so before the first hold, not during it.
        c.text(w // 2, py + 124,
               i18n.t("Aim the camera at your lap before you start."),
               role="caption", color="brand", anchor="mm")
        if self.glove is not None:
            c.text(w // 2, py + 144,
                   i18n.t("Sensor glove connected - which hand is wearing it?"),
                   role="caption", color="success", anchor="mm")
            # The glove is compared with the camera's reading of THIS hand
            # (TREMOR_RESTRUCTURE_PLAN.md §6). Unanswered, the comparison
            # falls back to the camera's strongest rest reading.
            gw, gap = 150, theme.SPACE[3]
            gx = w // 2 - gw - gap // 2
            for hnd in HANDS:
                chosen = self.glove_hand == hnd
                r = c.button(gx, py + 158, gw, 36, i18n.t(HAND_NAMES[hnd]),
                             variant="primary" if chosen else "ghost",
                             hovered=self.hover(gx, py + 158, gw, 36),
                             icon="check" if chosen else None)
                if self.hit(r):
                    self.glove_hand = hnd
                gx += gw + gap
        bw = pw - 2 * theme.SPACE[4]
        bx, by = px + theme.SPACE[4], py + 156 + extra
        b = c.button(bx, by, bw, 48, i18n.t("Start Test"), variant="primary",
                     hovered=self.hover(bx, by, bw, 48), icon="play")
        c.disclaimer()
        if self.pressed(b):
            self.reset_run()
            self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        w, h = c.w, c.h
        ph_ = self.phase
        # keyed, not line by line: Chinese sets its own line breaks
        lines = i18n.tk(f"tremor.{ph_.key}.instructions", ph_.instructions)
        pw = min(580, w - 2 * theme.SAFE_MARGIN)
        ph = 132 + len(lines) * 30 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 30,
               i18n.t("Part {n} of {total}", n=self.phase_i + 1,
                      total=len(PHASE_ORDER)),
               role="caption", color="text-muted", anchor="mm")
        c.text(w // 2, py + 62, i18n.t(ph_.title), role="h2", anchor="mm",
               color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 106 + i * 30, line, role="body_l", anchor="mm")
        c.text(w // 2, py + 112 + len(lines) * 30,
               i18n.t("Hold for {s} seconds. Press Space when ready.",
                      s=f"{ph_.duration_s:.0f}"),
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, i18n.t("I'm Ready"), variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.pressed(b):
            self._pos_since = None
            self.goto(POSITION, now)

    def _hand_chips(self, c: Canvas, y: int):
        """One chip per hand, centred: is each one fully in the picture."""
        chips = []
        for hnd in HANDS:
            mon = self.monitors[hnd]
            if hnd not in self.hands:
                chips.append((i18n.t("Show your {hand}",
                                     hand=i18n.t(HAND_NAMES[hnd]).lower()),
                              "warning"))
            elif mon.untrusted or mon.level == framing.CLIPPED:
                chips.append((i18n.t("{hand} at the edge",
                                     hand=i18n.t(HAND_NAMES[hnd])), "danger"))
            else:
                chips.append((i18n.t(HAND_NAMES[hnd]), "success"))
        gap = theme.SPACE[3]
        widths = [c.text_width(label, "caption") + 42 for label, _ in chips]
        x = (c.w - (sum(widths) + gap * (len(chips) - 1))) // 2
        for (label, status), cw in zip(chips, widths):
            c.chip(x, y, label, status=status)
            x += cw + gap

    def screen_position(self, c: Canvas, now: float):
        """Wait until both hands have been fully in view for a moment. The
        hold starts itself — nobody should have to reach for the mouse with
        their hands already in place."""
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, 70
        c.panel(px, py, pw, 112, alpha=0.85)
        c.text(w // 2, py + 28, i18n.t("Place both hands in view"),
               role="body_l", anchor="mm", color="brand")
        c.text(w // 2, py + 54, i18n.t(self.phase.cue), role="body",
               color="text-muted", anchor="mm")
        self._hand_chips(c, py + 72)

        if not self.both_trusted():
            self._pos_since = None
            return
        if self._pos_since is None:
            self._pos_since = now
        held = now - self._pos_since
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       min(1.0, held / POSITION_HOLD_S), color="success",
                       label=i18n.t("hold still"))
        if held >= POSITION_HOLD_S:
            self.goto(COUNTDOWN, now)

    def screen_countdown(self, c: Canvas, now: float):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining <= 0:
            self._start_recording(now)
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
        c.text(w // 2, h // 2 - 100, i18n.t(self.phase.cue), role="h2",
               anchor="mm", color="text-muted")
        if int(elapsed) != getattr(self, "_last_tick", -1):
            self._last_tick = int(elapsed)
            self.audio.play(self.tick_wav)

    def _start_recording(self, now: float):
        self.record_start = now
        self.recorder.arm(self.phase.key)      # every frame from here is kept
        self.audio.play(self.start_wav)
        self.goto(RECORDING, now)

    def screen_recording(self, c: Canvas, now: float):
        w, h = c.w, c.h
        ph_ = self.phase
        elapsed = now - self.record_start
        scoring = elapsed >= ph_.settle_s

        # Record every trusted hand. The first settle_s is the hands coming to
        # rest after the beep — voluntary motion, not tremor — so it is shown
        # but not kept.
        if scoring:
            fw, fh = self.frame_size
            for hnd, hd in self.hands.items():
                self.all_frames += 1
                if self.monitors[hnd].level == framing.CLIPPED:
                    self.clip_frames += 1
                if self.monitors[hnd].untrusted:
                    continue
                px_pts = [(x * fw, y * fh) for x, y in hd["raw"]]
                length = tm.hand_length(px_pts)
                if length is None:
                    continue
                d = self.data[ph_.key][hnd]
                d["t"].append(now)
                d["pts"].append(tm.select(px_pts))
                d["len"].append(length)

        # live HUD
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, 70
        c.panel(px, py, pw, 112, alpha=0.8)
        c.text(w // 2, py + 28, i18n.t(ph_.title), role="body_l",
               anchor="mm", color="brand")
        c.text(w // 2, py + 54, i18n.t(ph_.cue), role="body", anchor="mm",
               color="text-muted")
        self._hand_chips(c, py + 72)
        remaining = max(0.0, ph_.duration_s - elapsed)
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       min(1.0, elapsed / ph_.duration_s), color="success",
                       label=i18n.t("{s} s left", s=f"{remaining:.0f}"))
        missing = [hnd for hnd in HANDS if hnd not in self.hands]
        if missing:
            self.coach.say(i18n.t("Keep both hands in the picture"), PRI_HAND)

        if elapsed >= ph_.duration_s:
            self._end_phase(now)

    def _end_phase(self, now: float):
        ph_ = self.phase
        self.audio.play(self.done_wav)
        t0, t1 = self.record_start + ph_.settle_s, self.record_start + ph_.duration_s
        self.windows[ph_.key] = (t0, t1)
        take = self.recorder.disarm()
        # The live landmark cells: the fallback if the offline pass fails,
        # and kept for comparison either way.
        self.cells_live[ph_.key] = {
            hnd: dict(tm.analyse_hand(d["t"], d["pts"], d["len"],
                                      move_max=ph_.move_max,
                                      despike_spikes=True,
                                      instrument="landmarks"),
                      method="live_landmarks")
            for hnd, d in self.data[ph_.key].items()}
        if take is not None and len(take):
            self.analyser.submit(ph_.key, take, (t0, t1), ph_.move_max)
        if self.glove is not None:
            try:
                self.glove_cells[ph_.key] = tm.analyse_glove(
                    self.glove.imu_series(t0, t1))
            except Exception as e:  # noqa: BLE001 - the glove never ends a run
                print(f"[WARN] Glove window lost: {e}")
                self.glove_cells[ph_.key] = None
        if self.phase_i + 1 < len(PHASE_ORDER):
            self.phase_i += 1
            self.goto(INSTRUCTION, now)
        elif self.background:
            self._handoff = None
            self.goto(SAVING, now)
            # built here: capture_info() asks the camera, and only this
            # thread may do that beside the recorder
            self._handoff_thread = threading.Thread(
                target=self._hand_off, args=(self._job(),), daemon=True,
                name="tremor-handoff")
            self._handoff_thread.start()
        else:
            self.goto(ANALYSING, now)

    # ── the hand-off to a background worker (core/pending.py) ─────────────
    def _job(self) -> dict:
        """Everything finish_run() needs, as plain data (core/tremor/finish.py)."""
        glove_dev = None
        if self.glove is not None:
            glove_dev = {"port": self.glove.port, "imu": self.glove.imu_name(),
                         "hand": self.glove_hand}
        return {
            "phase_order": list(PHASE_ORDER), "hands": list(HANDS),
            "windows": dict(self.windows), "data": self.data,
            "cells_live": self.cells_live,
            "clip_frames": self.clip_frames, "all_frames": self.all_frames,
            "glove_cells": self.glove_cells, "glove_on": self.glove is not None,
            "glove_hand": self.glove_hand, "glove_dev": glove_dev,
            "capture_fps": self.recorder.fps, "camera_fps": self.fps,
            "frame_size": self.frame_size, "capture_info": capture_info(self.cap),
            "app_version": APP_VERSION,
            "duration_s": sum(PHASES[p].duration_s for p in PHASE_ORDER),
            # a snapshot now, so the worker files it under whoever was tested
            "profile": profiles.from_env(), "timestamp": datetime.now(),
        }

    def _hand_off(self, job: dict):
        """Thread: take the unfinished holds back from the offline pass, write
        them and the run's state (`job`) into a job folder, start the worker. Sets
        self._handoff to ("ok", dir), or ("failed", why, holds) where holds
        are the unfinished ones to measure here instead (None: the analyser
        never let go and is still working through them)."""
        left, job_dir = None, None
        try:
            left = self.analyser.hand_over()
            if left is None:
                raise RuntimeError("the offline pass did not stop")
            job_dir = pending.new_job("tremor")
            payload = {"job": job, "results": dict(self.analyser.results),
                       "errors": dict(self.analyser.errors), "todo": left,
                       "keep_dir": self.keep_dir}
            with open(job_dir / pending.JOB, "wb") as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
            self.spawn(job_dir)
            self._handoff = ("ok", job_dir)
        except Exception as e:  # noqa: BLE001 - fall back to finishing here
            print(f"[WARN] Could not hand the analysis over ({e}) - "
                  "finishing it here.")
            if job_dir is not None:
                pending.remove(job_dir)
            self._handoff = ("failed", str(e), left)

    def screen_saving(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, h // 2 - 50
        c.panel(px, py, pw, 100)
        c.text(w // 2, py + 34, i18n.t("Saving the recording"), role="h2",
               anchor="mm")
        c.text(w // 2, py + 66, i18n.t("You can rest your hands."),
               role="body", color="text-muted", anchor="mm")
        c.disclaimer()
        done = self._handoff
        if done is None:
            return
        if done[0] == "ok":
            self._close_camera()
            self.goto(HANDED, now)
            self._handed_at = time.monotonic()
            return
        left = done[2]
        if left is not None:
            # the old analyser has stopped: a new one finishes the rest here,
            # keeping what the old one had already measured
            old = self.analyser
            self.analyser = OfflineAnalyser(self._make_detect, hands=HANDS,
                                            keep_dir=self.keep_dir)
            self.analyser.results.update(old.results)
            self.analyser.errors.update(old.errors)
            self.analyser.start()
            for job in left:
                self.analyser.submit(*job)
        self.goto(ANALYSING, now)

    def _close_camera(self):
        """Let the camera go: the worker needs nothing more from it."""
        self.recorder.stop()
        try:
            self.cap.release()
        except Exception:  # noqa: BLE001 - it is going away either way
            pass
        self.camera_closed = True

    def screen_handed(self, c: Canvas, now: float) -> bool:
        """The closing card. True once it is time to exit."""
        w, h = c.w, c.h
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        bh = 42
        ph = 216
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 34, i18n.t("Recording saved"), role="h2",
               anchor="mm")
        c.text(w // 2, py + 70,
               i18n.t("The results are being measured in the background."),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 96,
               i18n.t("They will appear in the hub in about a minute."),
               role="body", color="text-muted", anchor="mm")
        left = max(0.0, HANDED_SHOW_S - (time.monotonic() - self._handed_at))
        c.text(w // 2, py + 126,
               i18n.t("This window closes in {n} s", n=f"{left:.0f}"),
               role="caption", color="text-muted", anchor="mm")
        bw = 160
        bx, by = w // 2 - bw // 2, py + ph - bh - 18
        b = c.button(bx, by, bw, bh, i18n.t("Close"), variant="primary",
                     hovered=self.hover(bx, by, bw, bh))
        c.disclaimer()
        return left <= 0 or self.pressed(b)

    def screen_analysing(self, c: Canvas, now: float):
        """The offline pass finishing what it could not do between holds."""
        w, h = c.w, c.h
        pw = min(520, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, h // 2 - 70
        c.panel(px, py, pw, 140)
        c.text(w // 2, py + 34, i18n.t("Measuring every frame"), role="h2",
               anchor="mm")
        c.text(w // 2, py + 66, i18n.t("You can rest your hands."),
               role="body", color="text-muted", anchor="mm")
        frac = self.analyser.progress()
        c.progress_bar(px + theme.SPACE[4], py + 96, pw - 2 * theme.SPACE[4],
                       frac, color="brand", label=f"{frac * 100:.0f}%")
        c.disclaimer()
        if self.analyser.idle():
            self._finish(now)

    def _finish(self, now: float):
        """Finish here, in-process: the path when there is no hand-off."""
        out = finish_run(self._job(), self.analyser.results,
                         self.analyser.errors, save=save_session)
        self.results, self.cells = out["results"], out["cells"]
        self.saved_path = out["saved_path"]
        self.goto(COMPLETE, now)

    def screen_complete(self, c: Canvas, now: float):
        w, h = c.w, c.h
        r = self.results
        pw = min(600, w - 2 * theme.SAFE_MARGIN)
        bh = 42

        # Sized to fit a 640x480 frame above the disclaimer ribbon, with the
        # glove line and the saved path sharing one row: the full table has to
        # stay readable, and the button must never fall under the ribbon.
        conf_h = 48 if (r.get("confidence_reasons") or []) else 40
        if r["scoreable"]:
            conf_off = 142
            table_off = conf_off + conf_h + 14
            note_off = table_off + 22 + len(PHASE_ORDER) * 22 + 12
            foot_off = note_off + 18
            btn_off = foot_off + 22
        else:
            reason = r.get("reason") or "Something went wrong - please try again."
            lines = i18n.wrap(i18n.t(reason), 48)[:3]
            btn_off = 108 + len(lines) * 26 + 12
        ph = btn_off + bh + 12
        px, py = (w - pw) // 2, max(48, min((h - ph) // 2, h - 30 - ph))
        c.panel(px, py, pw, ph, alpha=0.92)
        c.text(w // 2, py + 28, i18n.t("Hand Tremor - Results"), role="h2",
               anchor="mm")

        if r["scoreable"]:
            # A supporting check, not a screening result: the finding is said
            # neutrally, never as a traffic light. The saved verdict
            # (r["status"]) is unchanged (TREMOR_RESTRUCTURE_PLAN.md §2).
            c.badge(w // 2, py + 48, i18n.t(_finding(r)), "info")
            where = (r.get("tremor_where") or ":").split(":")
            where_txt = dict(phase=i18n.t(PHASE_SHORT.get(where[0], where[0])),
                             hand=i18n.t(HAND_NAMES.get(where[1], where[1])).lower())
            # A frequency is only the headline when there is a peak; a clean
            # run leads with how little the hands moved instead.
            if r.get("tremor_peak_hz") is not None:
                big = f"{r['tremor_peak_hz']:.1f} Hz"
                sub = i18n.t("Strongest rhythm: {phase}, {hand}", **where_txt)
            else:
                big = f"{r['tremor_amp_pct']:.1f}%"
                sub = i18n.t("Largest movement in the tremor band (% of hand length)")
            c._dirty = True
            c.draw.text((w // 2, py + 102), big, font=get_font("mono", 36),
                        fill=theme.rgba("text", 1.0), anchor="mm")
            c.text(w // 2, py + 128, sub, role="caption", color="text-muted",
                   anchor="mm")
            conf = r.get("confidence_pct") or 0
            conf_status = ("success" if conf >= 75 else
                           "info" if conf >= 45 else "warning")
            conf_level = ("High" if conf >= 75 else
                          "Moderate" if conf >= 45 else "Low")
            reasons = r.get("confidence_reasons") or []
            conf_w = min(360, pw - 2 * theme.SPACE[4])
            c.confidence_card(
                px + (pw - conf_w) // 2, py + conf_off, conf_w,
                label=i18n.t("Measurement confidence"),
                value=i18n.t("{level} - {pct}%", level=i18n.t(conf_level),
                             pct=f"{conf:.0f}"),
                detail=i18n.t(reasons[0]) if reasons else "",
                progress=conf / 100.0, status=conf_status)

            # phase × hand table: peak Hz and amplitude per cell
            x0 = px + theme.SPACE[4]
            col = (pw - 2 * theme.SPACE[4]) // 3
            ty = py + table_off
            for j, hnd in enumerate(HANDS):
                c.text(x0 + col * (j + 1) + col - 8, ty,
                       i18n.t(HAND_NAMES[hnd]), role="caption",
                       color="text-muted", anchor="ra")
            for i, p in enumerate(PHASE_ORDER):
                ry = ty + 22 + i * 22
                c.text(x0, ry, i18n.t(PHASE_SHORT[p]), role="caption",
                       color="text-muted")
                for j, hnd in enumerate(HANDS):
                    cell = (self.cells.get(p) or {}).get(hnd) or {}
                    if cell.get("scored"):
                        # no peak, no frequency: the tallest noise bin's Hz
                        # is random and would read as a finding
                        hz = (f"{cell['peak_hz']:.1f} Hz" if cell["verdict"] != tm.NONE
                              else "-")
                        val = f"{hz}  {cell['amp_pct']:.1f}%"
                        tone = "text" if cell["verdict"] == tm.NONE else "brand"
                    else:
                        val, tone = "-", "text-muted"
                    c.text(x0 + col * (j + 1) + col - 8, ry, val,
                           role="caption", anchor="ra", mono=True, color=tone)
            c.text(w // 2, py + note_off,
                   i18n.t("A supporting check for the tapping and spiral tests. "
                          "Size is an estimate."),
                   role="caption", color="text-muted", anchor="mm")
            foot = []
            if r.get("glove_rest_peak_hz") is not None:
                foot.append(i18n.t("Glove sensor at rest: {hz} Hz",
                                   hz=f"{r['glove_rest_peak_hz']:.1f}"))
            if self.saved_path:
                foot.append(i18n.t("Saved: results/{name}",
                                   name=self.saved_path.name))
            if foot:
                c.text(w // 2, py + foot_off, "  ·  ".join(foot),
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
        if self.pressed(b):
            self.reset_run()
            self.goto(IDLE, now)

    # ── main loop ─────────────────────────────────────────────────────────
    def _status_chips(self):
        chips = []
        n = len(self.hands)
        chips.append((i18n.t("{n} of 2 hands", n=n),
                      "success" if n == 2 else "warning"))
        if self.glove is not None:
            chips.append((i18n.t("Glove IMU"),
                          "success" if self.glove.is_connected() else "danger"))
        # The tremor is measured from the recorded frames, so the capture
        # rate is the one that matters; MediaPipe's live rate only paces the
        # picture.
        rate = self.recorder.fps or self.fps
        if rate < tm.FS_MIN + 2:
            chips.append((f"{rate:.0f} fps", "warning"))
        return chips

    def _run_handed(self, win, screen_rec) -> bool:
        """One frame of the closing card, drawn on a plain background since
        the camera has been released. True when the loop should end."""
        fw, fh = self.frame_size
        bg = np.zeros((fh, fw, 3), np.uint8)
        bg[:] = theme.bgr("bg")
        c = Canvas(bg)
        c.status_bar([], i18n.t("Hand Tremor"))
        close = self.screen_handed(c, time.time())
        show(win, screen_rec.frame(c.compose()))
        self.click = None
        key = cv2.waitKey(30) & 0xFF
        screen_rec.key(key)
        self.advance = key in KEY_ADVANCE
        return close or key == ord("q") or window_closed(win)

    def run(self):
        screen_rec = ScreenRecorder("tremor")
        win = "Hand Tremor Test  |  Q or close the window to quit"
        window_ready = False
        self.recorder.start()
        self.analyser.start()
        seq = 0
        while True:
            if self.camera_closed:
                # handed off: the camera is gone, only the closing card is left
                if self._run_handed(win, screen_rec):
                    break
                continue
            if not self.cap.isOpened():
                break
            got = self.recorder.next_frame(seq)  # already flipped to selfie view
            if got is None:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue
            seq, now, frame = got
            if not window_ready:
                create_display_window(win, frame.shape[1], frame.shape[0])
                set_mouse_callback(win, self.on_mouse)
                window_ready = True
            if self._last_frame_t is not None:
                dt = max(1e-3, now - self._last_frame_t)
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)
            self._last_frame_t = now
            fh, fw = frame.shape[:2]
            self.frame_size = (fw, fh)

            # the offline pass never competes with a hold being captured
            if self.state in QUIET_STATES:
                self.analyser.pause()
            else:
                self.analyser.resume()
            self.hands = self.detect_hands(frame, now)
            for hnd in HANDS:
                hd = self.hands.get(hnd)
                self.monitors[hnd].update(hd["raw"] if hd else None, now)
            # The overlay shows the optical flow, which is what gets scored,
            # not MediaPipe's per-frame skeleton, which twitches on a flat hand
            # (core/tremor/flow_view.py).
            self.flow_view.update(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), now,
                {h: ([(x * fw, y * fh) for x, y in hd["raw"]] if hd else None)
                 for h in HANDS for hd in (self.hands.get(h),)})

            # V hides every overlay (core/ui/keys.py): keep an undrawn copy
            bare = frame.copy() if self.overlay_hidden else None
            if bare is not None:
                self.click = None      # its buttons cannot be seen
            c = Canvas(frame)
            self.flow_view.draw(c, now, show_trace=self.state in (POSITION, COUNTDOWN,
                                                                  RECORDING))
            c.status_bar(self._status_chips(), i18n.t("Hand Tremor"))

            if self.state == IDLE:
                self.screen_idle(c, now)
            elif self.state == INSTRUCTION:
                self.screen_instruction(c, now)
            elif self.state == POSITION:
                self.screen_position(c, now)
            elif self.state == COUNTDOWN:
                self.screen_countdown(c, now)
            elif self.state == RECORDING:
                self.screen_recording(c, now)
            elif self.state == SAVING:
                self.screen_saving(c, now)
            elif self.state == ANALYSING:
                self.screen_analysing(c, now)
            elif self.state == COMPLETE:
                self.screen_complete(c, now)

            if self.state in (POSITION, COUNTDOWN, RECORDING):
                for hnd, hd in self.hands.items():
                    draw_framing(c, self.monitors[hnd], hd["raw"], self.coach)
            self.coach.render(c, now)

            out = (c.compose() if bare is None
                   else bare_view(bare, i18n.t(OVERLAY_HIDDEN_HINT)))
            show(win, screen_rec.frame(out))
            self.click = None
            key = cv2.waitKey(5) & 0xFF
            screen_rec.key(key)
            if key in TOGGLE_OVERLAY:
                self.overlay_hidden = not self.overlay_hidden
            self.advance = key in KEY_ADVANCE
            if key == ord("q"):
                break
            if window_closed(win):
                break

        # Quit mid-hand-off: let it finish, or the run is lost with the
        # half-written job (the worker is its own process once started).
        if self._handoff_thread is not None:
            self._handoff_thread.join(timeout=30.0)
        self.recorder.stop()
        self.analyser.stop()
        if not self.camera_closed:
            self.cap.release()
        screen_rec.close()
        cv2.destroyAllWindows()
        self.landmarker.close()
        for inst in self.side_landmarkers.values():
            inst.close()
        self.audio.close()
        if self.glove is not None:
            self.glove.disconnect()
        print("\n[INFO] " + i18n.ct("Hand tremor test closed."))


def main():
    args = sys.argv[1:]
    if "--finish" in args:
        # the background worker (spawn_worker): no camera, no window
        i = args.index("--finish")
        if i + 1 >= len(args):
            sys.exit("--finish needs a job folder")
        if hasattr(os, "nice"):
            try:
                os.nice(10)            # POSIX; Windows gets it from spawn_worker
            except OSError:
                pass
        sys.exit(0 if run_job(args[i + 1]) is not None else 1)
    # banner already printed by the splash, above the heavy imports
    source = select_camera_source()
    glove = open_glove()
    print("[INFO] " + i18n.ct("Opening camera and loading the hand model - a few seconds..."))
    cap = open_capture(source, fps=60)
    if cap is None:
        print("[ERROR] " + i18n.ct("Could not open camera."))
        if glove is not None:
            glove.disconnect()
        pause_before_exit()
        sys.exit(1)
    ensure_orientation(cap)   # once per camera: undo its own mirroring
    keep_dir = None
    if "--keep-frames" in sys.argv[1:]:
        # developer use only: every hold's frames, for re-analysis
        keep_dir = (_REPO_ROOT / "recordings"
                    / time.strftime("tremor_%Y%m%d_%H%M%S"))
        print(f"[INFO] Keeping every frame in {keep_dir}")
    App(cap, glove, keep_dir=keep_dir).run()


if __name__ == "__main__":
    main()
