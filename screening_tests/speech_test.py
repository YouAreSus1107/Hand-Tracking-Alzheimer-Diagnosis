"""
Speech Test
===========
Microphone-only speech screening in two parts (docs/tests/SPEECH_TEST_PLAN.md):

  Pa-Ta-Ka       -- diadochokinesis, 8 s: repeat pa-ta-ka as fast and evenly as
                    you can. Headline: rhythm CV% of inter-syllable intervals —
                    the speech analogue of IIV finger tapping. Saved as
                    test="ddk".
  Sustained Ahh  -- phonation, 6 s: hold a steady "ahhh". Headline: jitter %
                    (cycle-to-cycle pitch variation), plus shimmer, HNR and
                    vocal tremor, measured by Praat. Saved as test="phonation".

When the optional phoneme model is installed (python install.py --speech-ml)
pa-ta-ka also gets a sequencing-error rate and a second, independent syllable
count; its headline never depends on the model.

Flow: part select -> instructions -> mic check (room noise, then one practice
utterance for level) -> countdown -> recording -> analysing -> results
(auto-saved to results/ as JSON + CSV index).

This file is the run loop + rendering only; capture, detection, metrics and
the task registry live in core/speech/. No camera is used — the window is a
plain canvas drawn with the same core/ui toolkit as the camera tests.

Run:  python screening_tests/speech_test.py     Quit: press 'q'
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# Stdlib-only, and above the heavy imports on purpose (see core/splash.py).
from core.splash import Splash, SPEECH_IMPORT_STEPS
_splash = Splash("Speech Test", "Parts: Pa-Ta-Ka / Sustained Ahh",
                 SPEECH_IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
import numpy as np
_splash.step()               # OpenCV in

from core import i18n
from core.camera import (create_display_window, show, set_mouse_callback,
                         window_closed, pause_before_exit)
from core.screen_recorder import ScreenRecorder
from core.session import save_session
from core.speech import onsets as on
from core.speech import phonation, phonemes
from core.speech.metrics import compute_metrics
from core.speech.recorder import Recorder, RecorderError
from core.speech.tasks import (TASKS, DEFAULT_TASK, PHONATION, PhonationTask,
                               SpeechTask)
from core.tapping.audio import AudioWorker, build_tone
from core.ui import theme
from core.ui.anim import CountUp, ease_out_cubic, fade_in_out, lerp
from core.ui.components import Canvas, get_font

_splash.done()

APP_VERSION = "0.2.0"
W, H = 960, 600

COUNTDOWN_FROM = 3
GO_DELAY_S = 0.5            # the go tone plays, then the window opens — keeps
                            # the tone (and audio-output latency) out of it
QUIET_S = 2.0               # mic check: room-noise measurement
SPEAK_TIMEOUT_S = 8.0       # mic check: how long to wait for the practice word
VOICE_OVER_FLOOR_DB = 15.0  # a block this far over the floor counts as voice
CHECK_MIN_SNR_DB = 18.0     # practice word must clear the room by this much
CLIP_PEAK_DB = -1.0         # sample peak at/above this = too close to the mic
METER_LO_DB = -70.0

# ── States ─────────────────────────────────────────────────────────────────
(IDLE, INSTRUCTION, MIC_QUIET, MIC_SPEAK, COUNTDOWN, RECORDING, ANALYSING,
 COMPLETE, NO_MIC) = ("idle", "instruction", "mic_quiet", "mic_speak",
                      "countdown", "recording", "analysing", "complete",
                      "no_mic")


class Toasts:
    """One coach message at a time; base-duration fade in/out (§6.2)."""

    def __init__(self):
        self.msg, self.status, self.t0, self.hold = "", "info", -1e9, 2.0

    def show(self, msg: str, status: str = "info", hold: float = 2.5,
             now: float | None = None):
        now = time.time() if now is None else now
        if msg == self.msg and now - self.t0 < self.hold + 0.4:
            return
        self.msg, self.status, self.t0, self.hold = msg, status, now, hold

    def render(self, canvas: Canvas, now: float):
        canvas.toast(self.msg, self.status,
                     fade_in_out(self.t0, now, theme.DUR_BASE, self.hold))


def instructions_key(task) -> str:
    """i18n key of the task's pre-split instruction block."""
    return (f"phon.{task.key}.instructions" if task.kind == "phonation"
            else f"ddk.{task.key}.instructions")


class App:
    def __init__(self):
        self.task: SpeechTask | PhonationTask = TASKS[DEFAULT_TASK]
        self.rec = Recorder(rate=self.task.sample_rate)
        self.mic_error = ""
        try:
            self.rec.open()
        except RecorderError as e:
            self.mic_error = str(e)

        self.audio = AudioWorker()
        self.tick_wav = build_tone(660, 60)
        self.go_wav = build_tone(880, 150)
        self.done_wav = build_tone(523, 180)

        # The phoneme model takes a few seconds to load, so it loads in the
        # background while the person reads the instructions. Unavailable is
        # a normal state, not an error — pa-ta-ka runs on the envelope alone.
        self.ml_ok, self.ml_why = phonemes.available()
        self.recogniser = None
        self.ml_loading = self.ml_ok
        if self.ml_ok:
            threading.Thread(target=self._load_model, daemon=True).start()

        self.state = NO_MIC if self.mic_error else IDLE
        self.toasts = Toasts()
        self.mouse = (0, 0)
        self.click: tuple[int, int] | None = None
        self.floor_db: float | None = None
        self.reset_run()

    def _load_model(self):
        try:
            self.recogniser = phonemes.Recogniser()
        except Exception as e:          # noqa: BLE001 - never fatal to the test
            self.ml_ok, self.ml_why = False, f"model failed to load: {e}"
            print(f"[WARN] Phoneme model unavailable: {e}")
        self.ml_loading = False

    def _use_task(self, task) -> None:
        """Select a part. The two parts record at different rates (16 kHz for
        the syllable timing and the phoneme model, 44.1 kHz for the
        perturbation measures), so the stream is reopened when the rate
        changes."""
        self.task = task
        if self.rec.rate == task.sample_rate:
            return
        self.rec.close()
        self.rec = Recorder(rate=task.sample_rate)
        try:
            self.rec.open()
        except RecorderError as e:
            self.mic_error = str(e)

    # ── run-scoped state ──────────────────────────────────────────────────
    def reset_run(self):
        self.t_state = time.time()
        self.win_start = self.win_end = None     # sample marks
        self.check_mark = None
        self.voice_seen_t = None
        self.check_peak_db = -100.0
        self.check_voice_db = -100.0
        self.check_failed = False
        self.live_count = 0
        self.live_t = 0.0
        self.results = None
        self.saved_path = None
        self.countup: CountUp | None = None
        self._worker: threading.Thread | None = None
        self._last_tick = -1

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

    # ── shared drawing ────────────────────────────────────────────────────
    def level_meter(self, c: Canvas, x: int, y: int, w: int):
        """Live input level, -70..0 dBFS, with the room's floor marked."""
        lvl = self.rec.level_db
        frac = (lvl - METER_LO_DB) / -METER_LO_DB
        if self.rec.peak_db >= CLIP_PEAK_DB:
            color = "danger"
        elif self.floor_db is not None and lvl > self.floor_db + VOICE_OVER_FLOOR_DB:
            color = "success"
        else:
            color = "brand"
        c.progress_bar(x, y, w, frac, color=color,
                       label=i18n.t("Microphone level"))
        if self.floor_db is not None:
            fx = x + int(w * max(0.0, (self.floor_db - METER_LO_DB) / -METER_LO_DB))
            c.draw.line([(fx, y - 4), (fx, y + 12)],
                        fill=theme.rgba("text-muted", 1.0), width=2)

    def waveform(self, c: Canvas, x: int, y: int, w: int, h: int,
                 seconds: float = 3.0):
        """Scrolling loudness envelope of the last few seconds. Essential
        signal, not decoration, so it is exempt from REDUCED_MOTION (plan §5),
        like the oculomotor test's jumping dot."""
        c.panel(x, y, w, h, alpha=0.75, radius=12, shadow=False)
        buf = self.rec.recent(seconds)
        hop = int(self.rec.rate * 0.02)
        n = buf.size // hop
        if n < 2:
            return
        blocks = buf[:n * hop].reshape(n, hop).astype(np.float64)
        db = on.to_dbfs(np.sqrt(np.mean(blocks ** 2, axis=1)))
        frac = np.clip((db - METER_LO_DB) / -METER_LO_DB, 0.0, 1.0)
        pad = 10
        span = int(seconds / 0.02)
        x0 = x + pad + (span - n) * (w - 2 * pad) / span
        pts = [(int(x0 + i * (w - 2 * pad) / span),
                int(y + h - pad - f * (h - 2 * pad))) for i, f in enumerate(frac)]
        c.polyline(pts, "brand", thickness=2, layer="ui")   # inside its panel

    # ── screens ───────────────────────────────────────────────────────────
    def screen_no_mic(self, c: Canvas, now: float):
        pw = min(560, W - 2 * theme.SAFE_MARGIN)
        lines = i18n.wrap(i18n.t(self.mic_error), 46)[:3]
        ph = 150 + len(lines) * 26
        px, py = (W - pw) // 2, (H - ph) // 2
        c.panel(px, py, pw, ph)
        c.badge(W // 2, py + 26, i18n.t("No microphone"), "danger")
        for i, line in enumerate(lines):
            c.text(W // 2, py + 88 + i * 26, line, role="body",
                   color="text-muted", anchor="mm")
        bw = 200
        b = c.button(W // 2 - bw // 2, py + ph - 60, bw, 44, i18n.t("Try Again"),
                     variant="primary",
                     hovered=self.hover(W // 2 - bw // 2, py + ph - 60, bw, 44))
        c.disclaimer()
        if self.hit(b):
            self.rec = Recorder(rate=self.task.sample_rate)
            try:
                self.rec.open()
                self.mic_error = ""
                self.goto(IDLE, now)
            except RecorderError as e:
                self.mic_error = str(e)

    def screen_idle(self, c: Canvas, now: float):
        pw = min(540, W - 2 * theme.SAFE_MARGIN)
        px, py, ph = (W - pw) // 2, H // 2 - 140, 256
        c.panel(px, py, pw, ph)
        c.text(W // 2, py + 36, i18n.t("Speech Test"), role="h1", anchor="mm")
        c.text(W // 2, py + 74, i18n.t("Two short parts: speech rhythm and"),
               role="body", color="text-muted", anchor="mm")
        c.text(W // 2, py + 98, i18n.t("voice steadiness - microphone only."),
               role="body", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        bx = px + theme.SPACE[4]
        ptk = TASKS[DEFAULT_TASK]
        b1 = c.button(bx, py + 134, bw, 48,
                      i18n.t("Start {mode} ({secs} s)", mode=i18n.t(ptk.title),
                             secs=f"{ptk.duration_s:.0f}"),
                      variant="primary", icon="play",
                      hovered=self.hover(bx, py + 134, bw, 48))
        b2 = c.button(bx, py + 192, bw, 40,
                      i18n.t("Start {mode} ({secs} s)",
                             mode=i18n.t(PHONATION.title),
                             secs=f"{PHONATION.duration_s:.0f}"),
                      variant="ghost", hovered=self.hover(bx, py + 192, bw, 40))
        c.disclaimer()
        if self.hit(b1):
            self._use_task(ptk)
            self.goto(INSTRUCTION, now)
        elif self.hit(b2):
            self._use_task(PHONATION)
            self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        lines = i18n.tk(instructions_key(self.task), self.task.instructions)
        pw = min(600, W - 2 * theme.SAFE_MARGIN)
        ph = 120 + len(lines) * 32 + 84
        px, py = (W - pw) // 2, (H - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(W // 2, py + 34,
               i18n.t("{mode} - Your Task", mode=i18n.t(self.task.title)),
               role="h2", anchor="mm", color="brand")
        for i, line in enumerate(lines):
            c.text(W // 2, py + 80 + i * 32, line, role="body_l", anchor="mm")
        c.text(W // 2, py + 86 + len(lines) * 32,
               i18n.t("Next: a quick microphone check."),
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = W // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, i18n.t("I'm Ready"), variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.hit(b):
            self.reset_run()
            self.rec.reset()
            self.check_mark = self.rec.mark()
            self.goto(MIC_QUIET, now)

    def _check_panel(self, c: Canvas, title: str, sub: str) -> tuple[int, int, int]:
        pw = min(560, W - 2 * theme.SAFE_MARGIN)
        px, py, ph = (W - pw) // 2, H // 2 - 110, 190
        c.panel(px, py, pw, ph)
        c.text(W // 2, py + 34, i18n.t("Microphone check"), role="h2",
               anchor="mm", color="brand")
        c.text(W // 2, py + 76, title, role="body_l", anchor="mm")
        c.text(W // 2, py + 104, sub, role="caption", color="text-muted",
               anchor="mm")
        self.level_meter(c, px + theme.SPACE[4], py + 146, pw - 2 * theme.SPACE[4])
        return px, py + ph, pw

    def screen_mic_quiet(self, c: Canvas, now: float):
        elapsed = now - self.t_state
        self._check_panel(c, i18n.t("Stay quiet for a moment"),
                          i18n.t("Measuring the background noise in the room..."))
        c.progress_bar(theme.SAFE_MARGIN, H - 60, W - 2 * theme.SAFE_MARGIN,
                       elapsed / QUIET_S, color="brand")
        c.disclaimer()
        if elapsed >= QUIET_S:
            quiet = self.rec.slice(self.check_mark)
            _, env = on.envelope(quiet, self.rec.rate)
            self.floor_db = float(np.median(env)) if env.size else on.SILENCE_DB
            self.check_mark = self.rec.mark()
            self.voice_seen_t = None
            self.check_peak_db = self.check_voice_db = -100.0
            self.goto(MIC_SPEAK, now)

    def screen_mic_speak(self, c: Canvas, now: float):
        elapsed = now - self.t_state
        px, bottom, pw = self._check_panel(
            c, i18n.t("Now say \"{word}\" once, at your normal loudness",
                      word=self.task.utterance),
            i18n.t("This sets the level - it is not scored."))
        if self.check_failed:
            bw = 220
            b = c.button(W // 2 - bw // 2, bottom + 16, bw, 42,
                         i18n.t("Continue anyway"), variant="ghost",
                         hovered=self.hover(W // 2 - bw // 2, bottom + 16, bw, 42))
            if self.hit(b):
                self.goto(COUNTDOWN, now)
                c.disclaimer()
                return
        c.disclaimer()

        lvl = self.rec.level_db
        self.check_peak_db = max(self.check_peak_db, self.rec.peak_db)
        voiced = lvl > self.floor_db + VOICE_OVER_FLOOR_DB
        if voiced:
            self.check_voice_db = max(self.check_voice_db, lvl)
            self.voice_seen_t = now
        # Evaluate once the word is over: voice heard, then 0.6 s of quiet.
        if self.voice_seen_t is not None and not voiced \
                and now - self.voice_seen_t > 0.6:
            snr = self.check_voice_db - self.floor_db
            if self.check_peak_db >= CLIP_PEAK_DB:
                self._check_retry(now, i18n.t("Too loud - move back from the "
                                              "microphone a little"), "warning")
            elif snr < CHECK_MIN_SNR_DB:
                self._check_retry(now, i18n.t("Too quiet for this room - speak "
                                              "up or move closer to the "
                                              "microphone"), "warning")
            else:
                self.toasts.show(i18n.t("Sounds good"), "success", hold=1.2,
                                 now=now)
                self.goto(COUNTDOWN, now)
        elif elapsed > SPEAK_TIMEOUT_S:
            self._check_retry(now, i18n.t("We couldn't hear you - check that "
                                          "the right microphone is selected"),
                              "warning")

    def _check_retry(self, now: float, msg: str, status: str):
        self.toasts.show(msg, status, hold=3.5, now=now)
        self.check_failed = True
        self.voice_seen_t = None
        self.check_peak_db = self.check_voice_db = -100.0
        self.goto(MIC_SPEAK, now)

    def screen_countdown(self, c: Canvas, now: float):
        elapsed = now - self.t_state
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining <= 0:
            self.audio.play(self.go_wav)
            # The window opens GO_DELAY_S after the tone, on the sample clock.
            self.win_start = self.rec.mark() + int(GO_DELAY_S * self.rec.rate)
            self.win_end = self.win_start + int(self.task.duration_s * self.rec.rate)
            self.goto(RECORDING, now)
            return
        frac_sec = elapsed - int(elapsed)
        c.ring(W // 2, H // 2, 64, "brand", thickness=4,
               sweep_deg=360 * (1 - frac_sec) if not theme.REDUCED_MOTION else 360)
        scale = lerp(1.3, 1.0, ease_out_cubic(frac_sec / 0.3)) \
            if not theme.REDUCED_MOTION else 1.0
        c._dirty = True
        c.draw.text((W // 2, H // 2), str(remaining),
                    font=get_font("bold", int(64 * scale)),
                    fill=theme.rgba("text", 1.0), anchor="mm")
        c.text(W // 2, H // 2 - 110, i18n.t("Get ready..."), role="h2",
               anchor="mm", color="text-muted")
        c.text(W // 2, H // 2 + 110, self.task.utterance.upper(), role="h1",
               anchor="mm", color="brand")
        if int(elapsed) != self._last_tick:
            self._last_tick = int(elapsed)
            self.audio.play(self.tick_wav)

    def screen_recording(self, c: Canvas, now: float):
        mark = self.rec.mark()
        started = mark >= self.win_start
        elapsed = max(0.0, (mark - self.win_start) / self.rec.rate)
        remaining = self.task.duration_s - elapsed
        is_ddk = self.task.kind == "ddk"

        c.text(W // 2, 110, self.task.utterance.upper(), role="h1",
               anchor="mm", color="brand" if started else "text-muted")
        if not started:
            cue = i18n.t("Go!")
        elif is_ddk:
            cue = i18n.t("Go! Keep going...")
        else:
            cue = i18n.t("Hold it steady...")
        c.text(W // 2, 150, cue, role="body_l", anchor="mm")
        self.waveform(c, theme.SAFE_MARGIN, 190, W - 2 * theme.SAFE_MARGIN, 220)

        # Live syllable count, re-detected four times a second on the window
        # so far — feedback that the microphone is hearing them, not a score.
        if is_ddk:
            if started and now - self.live_t > 0.25:
                self.live_t = now
                syl, _, _, _ = on.detect_syllables(
                    self.rec.slice(self.win_start, mark), self.rec.rate,
                    min_gap_s=self.task.min_gap_s, floor_db=self.floor_db)
                self.live_count = len(syl)
            c.panel(theme.SAFE_MARGIN, 60, 190, 44, alpha=0.75, radius=12,
                    shadow=False)
            c.text(theme.SAFE_MARGIN + 14, 82, i18n.t("Syllables"),
                   role="body_sb", anchor="lm")
            c.text(theme.SAFE_MARGIN + 176, 82, f"{self.live_count}",
                   role="body_sb", anchor="rm", mono=True)
        elif started and self.floor_db is not None \
                and self.rec.level_db < self.floor_db + VOICE_OVER_FLOOR_DB:
            self.toasts.show(i18n.t("Keep the sound going until the bar fills"),
                             "info", now=now)

        c.progress_bar(theme.SAFE_MARGIN, H - 60, W - 2 * theme.SAFE_MARGIN,
                       elapsed / self.task.duration_s, color="success",
                       label=i18n.t("{secs} s left",
                                    secs=f"{max(0.0, remaining):.0f}"))
        if started and self.rec.peak_db >= CLIP_PEAK_DB:
            self.toasts.show(i18n.t("Too loud - move back from the microphone "
                                    "a little"), "warning", now=now)
        if mark >= self.win_end:
            self.audio.play(self.done_wav)
            target = self._analyse_ddk if is_ddk else self._analyse_phonation
            self._worker = threading.Thread(target=target, daemon=True)
            self._worker.start()
            self.goto(ANALYSING, now)

    def _save(self, test: str, extra_device: dict, raw: dict):
        try:
            self.saved_path = save_session(
                test=test, mode=self.task.key, hand=None,
                duration_s=self.task.duration_s,
                device={"microphone": self.rec.device_name,
                        "sample_rate": self.rec.rate, "app_version": APP_VERSION,
                        **extra_device},
                metrics=self.results, raw=raw)
        except OSError as e:
            self.saved_path = None
            print(f"[WARN] Could not save session: {e}")

    def _analyse_ddk(self):
        """Runs off the UI thread: the phoneme model takes a second or two."""
        x = self.rec.slice(self.win_start, self.win_end)
        rate = self.rec.rate
        syl, times, env, floor = on.detect_syllables(
            x, rate, min_gap_s=self.task.min_gap_s, floor_db=self.floor_db)
        # Wait out a model that is still loading rather than silently scoring
        # without it on a fast first run.
        deadline = time.time() + 20
        while self.ml_loading and time.time() < deadline:
            time.sleep(0.1)
        ml, phones = None, []
        if self.recogniser is not None:
            try:
                phones = self.recogniser.recognise(x, rate)
                ml = {"syllables": phonemes.syllables_from_phones(phones)}
            except Exception as e:      # noqa: BLE001 - the cross-check is optional
                print(f"[WARN] Phoneme recognition failed: {e}")
        self.results = compute_metrics(
            self.task, syl, 0.0, self.task.duration_s,
            snr_db=on.snr_db(syl, floor), clip_frac=on.clipping_fraction(x),
            ml=ml)
        raw = {
            "envelope": [[round(float(t), 3), round(float(d), 1)]
                         for t, d in zip(times[::2], env[::2])],
            "onsets_s": [round(s.onset_s, 3) for s in syl],
            "peaks_s": [round(s.peak_s, 3) for s in syl],
            "floor_db": round(floor, 1),
            "mic_check_floor_db": (round(self.floor_db, 1)
                                   if self.floor_db is not None else None),
            "phones": [[p.label, round(p.start_s, 2), round(p.end_s, 2),
                        round(p.prob, 2)] for p in phones],
            "trim_s": self.task.trim_s,
        }
        self._save("ddk", {"recogniser": phonemes.MODEL_ID if ml else None}, raw)

    def _analyse_phonation(self):
        """Praat on the steady middle of the vowel (core/speech/phonation.py)."""
        x = self.rec.slice(self.win_start, self.win_end)
        rate = self.rec.rate
        times, env = on.envelope(x, rate)
        floor = self.floor_db if self.floor_db is not None \
            else on.noise_floor_db(env)
        a, b = self.task.skip_start_s, self.task.duration_s - self.task.skip_end_s
        inside = env[(times >= a) & (times <= b)]
        snr = float(np.median(inside)) - floor if inside.size else None
        if not phonation.available():
            meas = {}
            self.results = {
                "scoreable": False,
                "reason": ("The voice analysis package (praat-parselmouth) is "
                           "not installed - run python install.py."),
                "jitter_pct": None}
        else:
            meas = phonation.measure(x, rate, self.task)
            self.results = phonation.compute_metrics(
                self.task, meas, snr_db=snr,
                clip_frac=on.clipping_fraction(x))
        f0t, f0 = meas.get("f0_times", []), meas.get("f0_hz", [])
        raw = {
            "envelope": [[round(float(t), 3), round(float(d), 1)]
                         for t, d in zip(times[::2], env[::2])],
            # 20 ms resolution is plenty to draw; 0 marks an unvoiced frame.
            "f0": [[round(t, 2), round(f, 1)] for t, f in zip(f0t[::2], f0[::2])],
            "segment_s": [a, b],
            "floor_db": round(floor, 1),
        }
        self._save("phonation", {}, raw)

    def screen_analysing(self, c: Canvas, now: float):
        # A ring that fills and restarts — "working", with no false progress.
        sweep = 360 * ((now - self.t_state) % 1.2) / 1.2
        c.ring(W // 2, H // 2 - 20, 40, "surface-2", thickness=4)
        c.ring(W // 2, H // 2 - 20, 40, "brand", thickness=4,
               sweep_deg=sweep if not theme.REDUCED_MOTION else 360)
        c.text(W // 2, H // 2 + 60, i18n.t("Analysing your recording..."),
               role="body_l", anchor="mm")
        if self.task.kind == "ddk" and (self.recogniser is not None
                                        or self.ml_loading):
            c.text(W // 2, H // 2 + 90,
                   i18n.t("Checking the syllable order with the phoneme model"),
                   role="caption", color="text-muted", anchor="mm")
        if self._worker is not None and not self._worker.is_alive():
            key = self._headline_key()
            if self.results and self.results.get(key) is not None:
                self.countup = CountUp(self.results[key], now, theme.DUR_SLOW)
            self.goto(COMPLETE, now)

    def _headline_key(self) -> str:
        return "rhythm_cv_pct" if self.task.kind == "ddk" else "jitter_pct"

    def _result_rows(self, r: dict) -> list[tuple[str, str]]:
        if self.task.kind == "ddk":
            rows = [("Syllable rate", f"{r['syllable_rate_hz']:.2f} /s"),
                    ("Mean interval", f"{r['mean_isi_ms']:.0f} ms"),
                    ("Syllables", f"{r['syllables']}")]
            if r.get("npvi") is not None:
                rows.append(("nPVI", f"{r['npvi']:.1f}"))
            if r.get("decrement_pct_per_s") is not None:
                rows.append(("Speed change", f"{r['decrement_pct_per_s']:+.1f} %/s"))
            if r.get("snr_db") is not None:
                rows.append(("Signal / noise", f"{r['snr_db']:.0f} dB"))
            # The phoneme model's order errors are recorded but not shown:
            # on test speech it reported 15-57% "errors" on clean pa-ta-ka
            # (SPEECH_TEST_PLAN.md §3.1b). Shown here, that would read as a
            # finding about the person.
            return rows
        rows = []
        if r.get("shimmer_pct") is not None:
            rows.append(("Shimmer", f"{r['shimmer_pct']:.2f} %"))
        if r.get("hnr_db") is not None:
            rows.append(("HNR", f"{r['hnr_db']:.1f} dB"))
        if r.get("f0_mean_hz") is not None:
            rows.append(("Mean pitch", f"{r['f0_mean_hz']:.0f} Hz"))
        if r.get("f0_sd_hz") is not None:
            rows.append(("Pitch SD", f"{r['f0_sd_hz']:.1f} Hz"))
        if r.get("vocal_tremor_hz") is not None:
            rows.append(("Vocal tremor", f"{r['vocal_tremor_hz']:.1f} Hz"))
        if r.get("voiced_pct") is not None:
            rows.append(("Voiced", f"{r['voiced_pct']:.0f} %"))
        if r.get("snr_db") is not None:
            rows.append(("Signal / noise", f"{r['snr_db']:.0f} dB"))
        return rows

    def screen_complete(self, c: Canvas, now: float):
        r = self.results
        is_ddk = self.task.kind == "ddk"
        pw = min(600, W - 2 * theme.SAFE_MARGIN)
        bh = 42
        if r["scoreable"]:
            rows = self._result_rows(r)[:9]
            nlines = (len(rows) + 2) // 3
            metrics_off = 248
            note_off = metrics_off + nlines * 22 + 14
            btn_off = note_off + (20 if r.get("band_edge") else 0) + 16
        else:
            reason = r["reason"] or "Something went wrong - please try again."
            lines = i18n.wrap(i18n.t(reason), 50)[:3]
            btn_off = 108 + len(lines) * 26 + 12
        ph = btn_off + bh + 14
        px, py = (W - pw) // 2, max(56, (H - ph) // 2)
        c.panel(px, py, pw, ph, alpha=0.9)
        c.text(W // 2, py + 30,
               i18n.t("{mode} - Results", mode=i18n.t(self.task.title)),
               role="h2", anchor="mm")

        if r["scoreable"]:
            key = self._headline_key()
            val = self.countup.value(now) if self.countup else r[key]
            c._dirty = True
            # Neutral colour on purpose, as in the tapping results: a red or
            # green number reads as an on-the-spot diagnosis.
            c.draw.text((W // 2, py + 90),
                        f"{val:.1f}%" if is_ddk else f"{val:.2f}%",
                        font=get_font("mono", 56),
                        fill=theme.rgba("text", 1.0), anchor="mm")
            c.text(W // 2, py + 126,
                   i18n.t("Rhythm variability (CV of syllable intervals)")
                   if is_ddk else
                   i18n.t("Jitter (cycle-to-cycle pitch variation)"),
                   role="caption", color="text-muted", anchor="mm")
            lo, hi = r.get("cv_ci_low_pct"), r.get("cv_ci_high_pct")
            if lo is not None and hi is not None:
                c.text(W // 2, py + 142,
                       i18n.t("95% CI {low}-{high}%", low=f"{lo:.1f}",
                              high=f"{hi:.1f}"), role="caption",
                       color="text-muted", anchor="mm", mono=True)
            c.badge(W // 2, py + 158, i18n.t(r["label"]), "info")
            conf = r.get("confidence_pct") or 0
            conf_status = ("success" if conf >= 75 else
                           "info" if conf >= 45 else "warning")
            conf_level = ("High" if conf >= 75 else
                          "Moderate" if conf >= 45 else "Low")
            conf_w = min(330, pw - 2 * theme.SPACE[4])
            c.confidence_card(
                px + (pw - conf_w) // 2, py + 200, conf_w,
                label=i18n.t("Measurement confidence"),
                value=i18n.t("{level} - {pct}%", level=i18n.t(conf_level),
                             pct=f"{conf:.0f}"),
                detail="", progress=conf / 100.0, status=conf_status)
            col_w = (pw - 4 * theme.SPACE[4]) // 3
            for i, (label, v) in enumerate(rows):
                rx = px + theme.SPACE[4] + (i % 3) * (col_w + theme.SPACE[4])
                ry = py + metrics_off + (i // 3) * 22
                c.text(rx, ry, i18n.t(label), role="caption", color="text-muted")
                c.text(rx + col_w, ry, v, role="caption", anchor="ra", mono=True)
            if is_ddk:
                typical = f"{self.task.cv_typical:.0f}"
                monitor = f"{self.task.cv_monitor:.0f}"
            else:
                typical = f"{self.task.jitter_typical:.2f}"
                monitor = f"{self.task.jitter_monitor:.2f}"
            c.text(W // 2, py + note_off,
                   i18n.t("Typical < {typical}% | monitor {typical}-{monitor}% "
                          "| elevated > {monitor}%",
                          typical=typical, monitor=monitor),
                   role="caption", color="text-muted", anchor="mm")
            if r.get("band_edge"):
                c.text(W // 2, py + note_off + 20,
                       i18n.t("Close to a band edge - repeat for a firmer reading."),
                       role="caption", color="text-muted", anchor="mm")
        else:
            c.badge(W // 2, py + 52, i18n.t("Couldn't score this run"), "warning")
            for i, line in enumerate(lines):
                c.text(W // 2, py + 108 + i * 26, line, role="body",
                       color="text-muted", anchor="mm")

        bw = 160
        bx = px + pw - theme.SPACE[4] - bw if r["scoreable"] else W // 2 - bw // 2
        by = py + btn_off
        if r["scoreable"] and self.saved_path:
            c.icon("check", px + theme.SPACE[4], by + 12, 18, "success")
            c.text(px + theme.SPACE[4] + 26, by + bh // 2, i18n.t("Result saved"),
                   role="caption", color="text-muted", anchor="lm")
        b = c.button(bx, by, bw, bh, i18n.t("Try Again"), variant="primary",
                     hovered=self.hover(bx, by, bw, bh))
        c.disclaimer()
        if self.hit(b):
            self.reset_run()
            self.goto(IDLE, now)

    # ── main loop ─────────────────────────────────────────────────────────
    def run(self):
        screen_rec = ScreenRecorder("speech")
        win = "Speech Test  |  Q or close the window to quit"
        create_display_window(win, W, H)
        set_mouse_callback(win, self.on_mouse)
        bg = np.empty((H, W, 3), np.uint8)
        bg[:] = theme.bgr("bg")
        while True:
            now = time.time()
            c = Canvas(bg.copy())
            if self.mic_error:
                chips = [(i18n.t("No microphone"), "danger")]
            else:
                chips = [(i18n.t("Microphone ready"), "success")]
                if self.recogniser is not None:
                    chips.append((i18n.t("Phoneme model on"), "info"))
                elif self.ml_loading:
                    chips.append((i18n.t("Loading phoneme model"), "info"))
            c.status_bar(chips, i18n.t(self.task.title))

            screen = {
                NO_MIC: self.screen_no_mic, IDLE: self.screen_idle,
                INSTRUCTION: self.screen_instruction,
                MIC_QUIET: self.screen_mic_quiet, MIC_SPEAK: self.screen_mic_speak,
                COUNTDOWN: self.screen_countdown, RECORDING: self.screen_recording,
                ANALYSING: self.screen_analysing, COMPLETE: self.screen_complete,
            }[self.state]
            screen(c, now)
            self.toasts.render(c, now)

            show(win, screen_rec.frame(c.compose()))
            self.click = None
            # The stream never stops, so drop what nobody will score while the
            # window sits between runs (~64-176 kB/s would otherwise pile up).
            if self.state in (IDLE, INSTRUCTION, COMPLETE) \
                    and self.rec.mark() > 30 * self.rec.rate:
                self.rec.reset()
            key = cv2.waitKey(15) & 0xFF
            screen_rec.key(key)
            if key == ord("q"):
                break
            if window_closed(win):
                break

        self.rec.close()
        screen_rec.close()
        cv2.destroyAllWindows()
        self.audio.close()
        print("\n[INFO] " + i18n.ct("Speech test closed."))


def main():
    try:
        App().run()
    except Exception as e:          # noqa: BLE001 - keep the console readable
        print(f"[ERROR] {type(e).__name__}: {e}")
        pause_before_exit()
        raise


if __name__ == "__main__":
    main()
