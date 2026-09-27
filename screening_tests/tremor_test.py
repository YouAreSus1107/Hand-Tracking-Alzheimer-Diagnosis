"""
Hand Tremor Test
================
Three 20-second holds with both hands in view, measured for a rhythmic
3.5-12 Hz oscillation. See docs/tests/TREMOR_TEST_PLAN.md.

  1. Hands at Rest         forearms on the table, hands relaxed (rest tremor)
  2. Rest While Counting   the same, counting backward aloud — mental load is
                           the standard way to bring out a hidden rest tremor
  3. Arms Held Out         both arms out, palms down (postural tremor)

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

Tremor is measured on the RAW landmarks; the One-Euro smoothing used to draw
the hand would erase it. Frames where a hand is at the edge of the picture are
left out (core/framing.py), because MediaPipe's guessed landmarks jitter.

This file is the run loop + rendering only; the engine lives in core/tremor/.
Results auto-save to results/ as JSON + a CSV index row.

Run:  python screening_tests/tremor_test.py     Quit: press 'q'
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
from core import i18n
from core.splash import Splash, IMPORT_STEPS
_splash = Splash("Hand Tremor Test",
                 "Click 'Start Test' in the camera window.  Q to quit.",
                 IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
_splash.step()               # OpenCV in
from core import quiet       # keep above mediapipe: silences its startup log
import mediapipe as mp
_splash.step()               # MediaPipe in

from core.hand_utils import (HAND_CONNECTIONS, make_landmark_filters,
                             smooth_landmarks, preprocess_for_mediapipe,
                             true_hand)
from core.camera import (select_camera_source, open_capture,
                         create_display_window, window_closed, pause_before_exit)
from core.mirror_check import ensure_orientation
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.ui import theme
from core.ui.anim import ease_out_cubic, fade_in_out, lerp
from core.ui.components import Canvas, draw_hand_skeleton, get_font
from core import framing
from core.ui.framing_ui import draw_framing
from core.tremor import metrics as tm
from core.tremor.phases import PHASES, PHASE_ORDER, HANDS

_splash.done()   # imports are in; the camera prompt follows immediately

APP_VERSION = "0.1.0"
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

# ── Test Configuration ────────────────────────────────────────────────────
COUNTDOWN_FROM = 3
POSITION_HOLD_S = 1.5        # both hands trusted this long before a hold starts
GLOVE_BANNER_WAIT_S = 2.5    # how long to wait for the board to announce itself
KEY_ADVANCE = (13, 32)       # Enter / Space press the screen's main button

# ── States ────────────────────────────────────────────────────────────────
(IDLE, INSTRUCTION, POSITION, COUNTDOWN, RECORDING, COMPLETE) = (
    "idle", "instruction", "position", "countdown", "recording", "complete")

HAND_NAMES = {"left": "Left hand", "right": "Right hand"}
PHASE_SHORT = {"rest": "Rest", "rest_count": "Counting", "postural": "Arms out"}


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


class App:
    def __init__(self, cap, glove=None):
        self.cap = cap
        self.glove = glove
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
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
        self.toasts = Toasts()
        self.filters = {h: make_landmark_filters() for h in HANDS}
        self.monitors = {h: framing.FramingMonitor() for h in HANDS}
        self.hands: dict[str, dict] = {}

        self.mouse = (0, 0)
        self.click: tuple[int, int] | None = None
        self.advance = False
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
        self.data = {p: {h: {"t": [], "pts": [], "len": []} for h in HANDS}
                     for p in PHASE_ORDER}
        self.cells: dict = {}
        self.glove_cells: dict = {}
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
        """{"left"|"right": {"raw": 21 (x, y) normalised, "smooth": ...}}.

        Two hands are told apart by where they are, not by MediaPipe's
        handedness label: resting apart on a table they never cross, and the
        label flips now and then. The frame is flipped to selfie view, so the
        hand on the left of the picture is the person's left hand. With only
        one hand in view the label is all there is, and is used -- through
        true_hand(), since on a selfie frame it names the other hand."""
        rgb = preprocess_for_mediapipe(frame, enable=self.fps >= 20)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_img, int(now * 1000))
        found = list(zip(result.hand_landmarks or [], result.handedness or []))
        out: dict[str, dict] = {}
        if len(found) >= 2:
            found = sorted(found[:2], key=lambda f: f[0][0].x)
            labelled = zip(("left", "right"), found)
        elif found:
            labelled = [(true_hand(found[0][1][0].category_name, selfie=True),
                         found[0])]
        else:
            labelled = []
        for label, (lms, _hd) in labelled:
            if label not in HANDS:
                continue
            fx, fy = self.filters[label]
            out[label] = {
                "raw": [(lm.x, lm.y) for lm in lms],
                "smooth": smooth_landmarks(lms, fx, fy, now),
            }
        return out

    def both_trusted(self) -> bool:
        return all(h in self.hands and not self.monitors[h].untrusted
                   for h in HANDS)

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(540, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 128, 236
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, i18n.t("Hand Tremor Test"), role="h1",
               anchor="mm")
        c.text(w // 2, py + 74,
               i18n.t("Three 20-second holds with both hands in view."),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 98,
               i18n.t("Measures shaking at rest and with arms held out."),
               role="body", color="text-muted", anchor="mm")
        if self.glove is not None:
            c.text(w // 2, py + 124,
                   i18n.t("Sensor glove connected - its motion sensor is "
                          "recorded too."),
                   role="caption", color="success", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        bx, by = px + theme.SPACE[4], py + 156
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
            self.toasts.show(i18n.t("Keep both hands in the picture"),
                             "warning", now=now)

        if elapsed >= ph_.duration_s:
            self._end_phase(now)

    def _end_phase(self, now: float):
        ph_ = self.phase
        self.audio.play(self.done_wav)
        t0, t1 = self.record_start + ph_.settle_s, self.record_start + ph_.duration_s
        self.windows[ph_.key] = (t0, t1)
        self.cells[ph_.key] = {
            hnd: tm.analyse_hand(d["t"], d["pts"], d["len"],
                                 move_max=ph_.move_max)
            for hnd, d in self.data[ph_.key].items()}
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
        else:
            self._finish(now)

    def _finish(self, now: float):
        clipped = 100.0 * self.clip_frames / self.all_frames if self.all_frames else 0.0
        self.results = tm.compute_metrics(
            self.cells, phase_order=PHASE_ORDER, hands=HANDS,
            glove=self.glove_cells if self.glove is not None else None,
            clipped_pct=clipped)
        self.results["edge_clipped_pct"] = round(clipped, 1)
        self._save_session()
        self.goto(COMPLETE, now)

    def _save_session(self):
        r = self.results
        # The spectra are for the report panel, which reads `raw`; the
        # metrics block (sent with every session list) keeps one line a cell.
        light = {p: {hnd: ({k: c[k] for k in ("peak_hz", "amp_pct",
                                              "prominence", "verdict")}
                           if c and c.get("scored") else
                           {"why": (c or {}).get("why")})
                     for hnd, c in per.items()}
                 for p, per in self.cells.items()}
        metrics = {k: v for k, v in r.items() if k not in ("cells", "glove")}
        metrics["cells"] = light
        raw = {"phases": {}, "glove": self.glove_cells or None}
        for p, per in self.data.items():
            t0 = self.windows.get(p, (0.0, 0.0))[0]
            traces = {}
            for hnd, d in per.items():
                if not d["t"]:
                    continue
                # index fingertip, relative to its own median, in % of the
                # hand length: the movement the spectrum was computed from
                scale = sorted(d["len"])[len(d["len"]) // 2]
                xs = [pt[2][0] for pt in d["pts"]]
                ys = [pt[2][1] for pt in d["pts"]]
                mx, my = sorted(xs)[len(xs) // 2], sorted(ys)[len(ys) // 2]
                traces[hnd] = [[round(t - t0, 3),
                                round((x - mx) / scale * 100, 2),
                                round((y - my) / scale * 100, 2)]
                               for t, x, y in zip(d["t"], xs, ys)]
            raw["phases"][p] = {
                "traces": traces,
                "spectra": {hnd: c.get("spectrum")
                            for hnd, c in (self.cells.get(p) or {}).items()
                            if c and c.get("scored")},
            }
        glove_dev = None
        if self.glove is not None:
            glove_dev = {"port": self.glove.port, "imu": self.glove.imu_name()}
        duration = sum(PHASES[p].duration_s for p in PHASE_ORDER)
        fw, fh = self.frame_size
        try:
            self.saved_path = save_session(
                test="tremor", mode="rest_postural", hand="both",
                duration_s=duration,
                device={"camera_fps": round(self.fps, 1),
                        "resolution": f"{fw}x{fh}", "app_version": APP_VERSION,
                        "glove": glove_dev},
                metrics=metrics, raw=raw)
        except OSError as e:
            self.saved_path = None
            print(f"[WARN] Could not save session: {e}")

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
            c.badge(w // 2, py + 48, i18n.t(r["label"]), r["status"])
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
                        tone = tm.band(cell["verdict"])[0]
                        tone = "text" if tone == "success" else tone
                    else:
                        val, tone = "-", "text-muted"
                    c.text(x0 + col * (j + 1) + col - 8, ry, val,
                           role="caption", anchor="ra", mono=True, color=tone)
            c.text(w // 2, py + note_off,
                   i18n.t("Peak frequency and movement (% of hand length). "
                          "Size is an estimate - screening, not diagnosis."),
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
        if self.fps < tm.FS_MIN + 2:
            chips.append((f"{self.fps:.0f} fps", "warning"))
        return chips

    def run(self):
        win = "Hand Tremor Test  |  Q or window ✕ to quit"
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
            self.frame_size = (fw, fh)

            self.hands = self.detect_hands(frame, now)
            for hnd in HANDS:
                hd = self.hands.get(hnd)
                self.monitors[hnd].update(hd["raw"] if hd else None, now)
                if hd:
                    draw_hand_skeleton(frame, hd["smooth"], HAND_CONNECTIONS)

            c = Canvas(frame)
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
            elif self.state == COMPLETE:
                self.screen_complete(c, now)

            if self.state in (POSITION, COUNTDOWN, RECORDING):
                for hnd, hd in self.hands.items():
                    draw_framing(c, self.monitors[hnd], hd["raw"], self.toasts,
                                 now)
            self.toasts.render(c, now)

            cv2.imshow(win, c.compose())
            self.click = None
            key = cv2.waitKey(5) & 0xFF
            self.advance = key in KEY_ADVANCE
            if key == ord("q"):
                break
            if window_closed(win):
                break

        self.cap.release()
        cv2.destroyAllWindows()
        self.landmarker.close()
        self.audio.close()
        if self.glove is not None:
            self.glove.disconnect()
        print("\n[INFO] Hand tremor test closed.")


def main():
    # banner already printed by the splash, above the heavy imports
    source = select_camera_source()
    glove = open_glove()
    print("[INFO] Opening camera and loading the hand model - a few seconds...")
    cap = open_capture(source, fps=60)
    if cap is None:
        print("[ERROR] Could not open camera.")
        if glove is not None:
            glove.disconnect()
        pause_before_exit()
        sys.exit(1)
    ensure_orientation(cap)   # once per camera: undo its own mirroring
    App(cap, glove).run()


if __name__ == "__main__":
    main()
