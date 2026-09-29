"""
Walking Test - seated part
==========================
The first part of the walking test in docs/tests/GAIT_TEST_PLAN.md: the
seated tier, which needs about a metre of floor and carries no fall risk.

  1. Right Leg Stamps    10 s, lift and stamp the right foot (UPDRS 3.8)
  2. Left Leg Stamps     10 s, the same with the left
  3. Five Sit-to-Stands  as fast as safely possible (UPDRS 3.9)

The camera is side-on, 2-3 m away, with the whole body in the picture. A
phone streaming over Wi-Fi works through the camera chip's URL option.

Before the first block the person raises their right arm. That settles which
of the pose model's labels is the person's right on this camera, since the
model's convention has not been verified here (core/gait/body.py).

Headline (core/gait/metrics.py): the five-sit-to-stand time. Leg agility is
reported per leg with the left/right difference. Everything is measured on
the RAW landmarks; frames where part of the body is out of the picture are
left out (core/framing.py). Only landmarks are saved, never video.

This file is the run loop + rendering only; the engine lives in core/gait/.

Run:  python screening_tests/gait_test.py     Quit: press 'q'
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))

# Stdlib-only, and above the heavy imports on purpose (see core/splash.py).
from core import i18n
from core.splash import Splash, IMPORT_STEPS
_splash = Splash("Walking Test",
                 "Click 'Start Test' in the camera window.  Q to quit.",
                 IMPORT_STEPS, enabled=__name__ == "__main__")

import cv2
_splash.step()               # OpenCV in
from core.gait.pose import PoseTracker   # imports mediapipe (quietly)
_splash.step()               # MediaPipe in

from core.camera import (capture_info, select_camera_source, open_capture,
                         create_display_window, window_closed, pause_before_exit)
from core.screen_recorder import ScreenRecorder
from core.session import save_session
from core.tapping.audio import AudioWorker, build_tone
from core.ui import theme
from core.ui.anim import ease_out_cubic, lerp
from core.ui.coach import Coach, PRI_EDGE, PRI_HAND, PRI_SETUP
from core.ui.components import Canvas, get_font
from core import framing
from core.gait import body, seated
from core.gait import metrics as gm
from core.gait.phases import BLOCKS, SEATED_ORDER, LEG_AGILITY, SIT_TO_STAND

_splash.done()

APP_VERSION = "0.1.0"

# ── Test Configuration ────────────────────────────────────────────────────
COUNTDOWN_FROM = 3
POSITION_HOLD_S = 1.5        # seated still and in view this long before a block
ARM_HOLD_S = 1.0             # the raised arm must stay up this long
STS_TAIL_S = 0.5             # keep recording this long after the fifth sit
KEY_ADVANCE = (13, 32)       # Enter / Space press the screen's main button

(IDLE, SETUP, INSTRUCTION, POSITION, COUNTDOWN, RECORDING, COMPLETE) = (
    "idle", "setup", "instruction", "position", "countdown", "recording",
    "complete")

SIDE_NAMES = {"left": "Left leg", "right": "Right leg"}


def body_hint(edges) -> str:
    """Framing advice for a whole body. The person is 2-3 m from the camera,
    so moving the camera is usually easier than moving the chair."""
    if "bottom" in edges:
        return "Move the camera back so your feet are in view"
    if "top" in edges:
        return "Move the camera back so your head is in view"
    return "Move toward the middle of the picture"


class App:
    def __init__(self, cap):
        self.cap = cap
        self.tracker = PoseTracker()
        self.audio = AudioWorker()
        self.start_wav = build_tone(880, 100)
        self.tick_wav = build_tone(660, 60)
        self.done_wav = build_tone(523, 180)
        self.ok_wav = build_tone(988, 80)

        self.state = IDLE
        self.coach = Coach()
        self.monitor = framing.FramingMonitor()
        self.pts: list | None = None           # raw pixel landmarks, this frame
        self.vis: list | None = None

        self.mouse = (0, 0)
        self.click: tuple[int, int] | None = None
        self.advance = False
        self.fps = 30.0
        self._last_frame_t: float | None = None
        self.frame_size = (640, 480)
        self.reset_run()

    # ── run-scoped state ──────────────────────────────────────────────────
    def reset_run(self):
        self.sides = body.SideMap()
        self.block_i = 0
        self.t_state = time.time()
        self.record_start = 0.0
        self._pos_since: float | None = None
        self._arm_since: float | None = None
        self._arm_side: str | None = None
        self._ref: list[dict] = []             # samples while seated still
        self.refs: dict = {}
        self.recorder: seated.LegRecorder | None = None
        self.counter: seated.StandCounter | None = None
        self._sts_done_at: float | None = None
        self.cells: dict = {}                  # {block key: analysis}
        self.raw_blocks: dict = {}
        self.windows: dict = {}
        self.rec_frames = self.rec_trusted = 0
        self.results = None
        self.saved_path = None
        self.monitor = framing.FramingMonitor()

    @property
    def block(self):
        return BLOCKS[SEATED_ORDER[self.block_i]]

    def goto(self, state: str, now: float):
        self.state = state
        self.t_state = now
        self.coach.clear()

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
        """Clicked, or Space/Enter -- the helper's key, so nobody walks back
        to the laptop between blocks."""
        return self.hit(rect) or self.advance

    def hover(self, x, y, w, h) -> bool:
        mx, my = self.mouse
        return x <= mx <= x + w and y <= my <= y + h

    # ── geometry helpers ──────────────────────────────────────────────────
    def _norm_body(self):
        """The framing check's view: body joints, normalised, display-mirrored
        so the edge bands land on the side the person sees."""
        if self.pts is None:
            return None
        fw, fh = self.frame_size
        return [(1.0 - self.pts[i][0] / fw, self.pts[i][1] / fh) for i in body.BODY]

    @property
    def trusted(self) -> bool:
        return self.pts is not None and not self.monitor.untrusted

    def _capture_ref(self):
        """One sample of the seated pose, for the block's reference values."""
        p, v = self.pts, self.vis
        blk = self.block
        s = {"lean": body.trunk_lean_deg(p)}
        if blk.kind == LEG_AGILITY:
            hip = p[self.sides.idx(blk.side, "hip")]
            knee = p[self.sides.idx(blk.side, "knee")]
            s.update(knee_y=knee[1], thigh=body.dist(hip, knee))
        else:
            # the side nearer the camera: its hip and knee are seen, not guessed
            best = max(body.SIDES, key=lambda sd: v[body.model_idx(sd, "hip")]
                       + v[body.model_idx(sd, "knee")])
            hip, knee = p[body.model_idx(best, "hip")], p[body.model_idx(best, "knee")]
            s.update(side=best, thigh=body.dist(hip, knee),
                     offset=knee[1] - hip[1])
        self._ref.append(s)

    def _settle_ref(self) -> dict:
        def med(key):
            vals = sorted(x[key] for x in self._ref if x.get(key) is not None)
            return vals[len(vals) // 2] if vals else None
        ref = {k: med(k) for k in ("knee_y", "thigh", "offset", "lean")}
        sides = [x["side"] for x in self._ref if "side" in x]
        if sides:
            ref["side"] = max(set(sides), key=sides.count)
        return ref

    # ── screens ───────────────────────────────────────────────────────────
    def screen_idle(self, c: Canvas, now: float):
        w, h = c.w, c.h
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        px, py, ph = (w - pw) // 2, h // 2 - 140, 262
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 36, i18n.t("Walking Test"), role="h1", anchor="mm")
        c.text(w // 2, py + 74, i18n.t("Seated part: leg stamps and five "
                                       "sit-to-stands."),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 100,
               i18n.t("Use a sturdy chair. Have someone with you."),
               role="body", color="text-muted", anchor="mm")
        c.text(w // 2, py + 128,
               i18n.t("Camera side-on, 2-3 m away, whole body in view."),
               role="caption", color="brand", anchor="mm")
        c.text(w // 2, py + 150,
               i18n.t("Your helper presses Space to move on."),
               role="caption", color="text-muted", anchor="mm")
        bw = pw - 2 * theme.SPACE[4]
        bx, by = px + theme.SPACE[4], py + 186
        b = c.button(bx, by, bw, 48, i18n.t("Start Test"), variant="primary",
                     hovered=self.hover(bx, by, bw, 48), icon="play")
        c.disclaimer()
        if self.pressed(b):
            self.reset_run()
            self._arm_since = None
            self.goto(SETUP, now)

    def screen_setup(self, c: Canvas, now: float):
        """Whole body in view, then the arm-raise check."""
        w, h = c.w, c.h
        pw = min(600, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, 56
        c.panel(px, py, pw, 128, alpha=0.85)
        elapsed = now - self.t_state
        if not self.trusted:
            self._arm_side = self._arm_since = None
            c.text(w // 2, py + 40, i18n.t("Sit so your whole body is in view"),
                   role="h2", anchor="mm", color="brand")
            c.text(w // 2, py + 80, i18n.t("Side-on to the camera, feet included."),
                   role="body_l", anchor="mm", color="text-muted")
        else:
            c.text(w // 2, py + 40, i18n.t("Raise your right arm above your head"),
                   role="h2", anchor="mm", color="brand")
            c.text(w // 2, py + 80,
                   i18n.t("This tells the test which side is which."),
                   role="body_l", anchor="mm", color="text-muted")
            up = body.raised_side(self.pts)
            if up is not None and up == self._arm_side:
                held = now - (self._arm_since or now)
                c.progress_bar(theme.SAFE_MARGIN, h - 44,
                               w - 2 * theme.SAFE_MARGIN,
                               min(1.0, held / ARM_HOLD_S), color="success",
                               label=i18n.t("hold it up"))
                if held >= ARM_HOLD_S:
                    # the model called the person's right arm `up`
                    self.sides = body.SideMap(swapped=(up != "right"))
                    self.audio.play(self.ok_wav)
                    self._begin_block(now)
                    return
            else:
                self._arm_side = up
                self._arm_since = now if up is not None else None
        # The check can be skipped: without it the left/right labels are the
        # model's own, and the result's confidence says so.
        if elapsed > 3.0:
            bw = 200
            bx, by = w // 2 - bw // 2, py + 142
            b = c.button(bx, by, bw, 40, i18n.t("Skip this check"),
                         variant="ghost", hovered=self.hover(bx, by, bw, 40))
            if self.pressed(b):
                self._begin_block(now)

    def _begin_block(self, now: float):
        self._ref = []
        self.goto(INSTRUCTION, now)

    def screen_instruction(self, c: Canvas, now: float):
        w, h = c.w, c.h
        blk = self.block
        lines = i18n.tk(f"gait.{blk.key}.instructions", blk.instructions)
        pw = min(620, w - 2 * theme.SAFE_MARGIN)
        ph = 132 + len(lines) * 34 + 84
        px, py = (w - pw) // 2, (h - ph) // 2
        c.panel(px, py, pw, ph)
        c.text(w // 2, py + 30,
               i18n.t("Part {n} of {total}", n=self.block_i + 1,
                      total=len(SEATED_ORDER)),
               role="caption", color="text-muted", anchor="mm")
        c.text(w // 2, py + 66, i18n.t(blk.title), role="h1", anchor="mm",
               color="brand")
        for i, line in enumerate(lines):
            c.text(w // 2, py + 112 + i * 34, line, role="h2", anchor="mm")
        c.text(w // 2, py + 118 + len(lines) * 34,
               i18n.t("Press Space when ready."),
               role="caption", color="text-muted", anchor="mm")
        bw = 200
        bx, by = w // 2 - bw // 2, py + ph - 64
        b = c.button(bx, by, bw, 48, i18n.t("I'm Ready"), variant="success",
                     hovered=self.hover(bx, by, bw, 48), icon="check")
        c.disclaimer()
        if self.pressed(b):
            self._pos_since = None
            self._ref = []
            self.goto(POSITION, now)

    def screen_position(self, c: Canvas, now: float):
        """Seated still, whole body trusted, for a moment: that is the
        reference pose every block is measured from."""
        w, h = c.w, c.h
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, 56
        c.panel(px, py, pw, 96, alpha=0.85)
        c.text(w // 2, py + 34, i18n.t("Sit still"), role="h1", anchor="mm",
               color="brand")
        c.text(w // 2, py + 70, i18n.t(self.block.cue), role="body_l",
               color="text-muted", anchor="mm")
        if not self.trusted:
            self._pos_since = None
            self._ref = []
            return
        if self._pos_since is None:
            self._pos_since = now
        self._capture_ref()
        held = now - self._pos_since
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       min(1.0, held / POSITION_HOLD_S), color="success",
                       label=i18n.t("hold still"))
        if held >= POSITION_HOLD_S:
            self.refs[self.block.key] = self._settle_ref()
            self.goto(COUNTDOWN, now)

    def screen_countdown(self, c: Canvas, now: float):
        w, h = c.w, c.h
        elapsed = now - self.t_state
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining <= 0:
            self._start_recording(now)
            return
        frac_sec = elapsed - int(elapsed)
        c.ring(w // 2, h // 2, 80, "brand", thickness=5,
               sweep_deg=360 * (1 - frac_sec) if not theme.REDUCED_MOTION else 360)
        scale = lerp(1.3, 1.0, ease_out_cubic(frac_sec / 0.3)) \
            if not theme.REDUCED_MOTION else 1.0
        c._dirty = True
        c.draw.text((w // 2, h // 2), str(remaining),
                    font=get_font("bold", int(84 * scale)),
                    fill=theme.rgba("text", 1.0), anchor="mm")
        c.text(w // 2, h // 2 - 124, i18n.t(self.block.cue), role="h1",
               anchor="mm", color="text-muted")
        if int(elapsed) != getattr(self, "_last_tick", -1):
            self._last_tick = int(elapsed)
            self.audio.play(self.tick_wav)

    def _start_recording(self, now: float):
        self.record_start = now
        blk = self.block
        if blk.kind == LEG_AGILITY:
            self.recorder = seated.LegRecorder()
        else:
            self.counter = seated.StandCounter(now)
            self._sts_done_at = None
        self.audio.play(self.start_wav)
        self.goto(RECORDING, now)

    def screen_recording(self, c: Canvas, now: float):
        w, h = c.w, c.h
        blk = self.block
        ref = self.refs.get(blk.key) or {}
        elapsed = now - self.record_start
        self.rec_frames += 1
        ok = self.trusted
        if ok:
            self.rec_trusted += 1
        p = self.pts

        if blk.kind == LEG_AGILITY:
            lift = None
            if ok and ref.get("thigh") and ref.get("knee_y") is not None:
                knee = p[self.sides.idx(blk.side, "knee")]
                lift = seated.knee_lift(knee[1], ref["knee_y"], ref["thigh"])
            if self.recorder.update(now, lift):
                self.audio.play(self.tick_wav)
            count_label = i18n.t("{n} stamps", n=len(self.recorder.stamps))
            done = elapsed >= blk.duration_s
            frac = elapsed / blk.duration_s
            left_label = i18n.t("{s} s left", s=f"{max(0.0, blk.duration_s - elapsed):.0f}")
        else:
            if ok and ref.get("thigh") and ref.get("offset") is not None:
                sd = ref.get("side", "left")
                hip = p[body.model_idx(sd, "hip")]
                knee = p[body.model_idx(sd, "knee")]
                sh = p[body.model_idx(sd, "shoulder")]
                s = seated.stand_index(hip[1], knee[1], ref["thigh"], ref["offset"])
                hands = seated.hands_low(
                    [p[body.model_idx(x, "wrist")][1] for x in body.SIDES],
                    sh[1], hip[1])
                before = self.counter.n_stands
                self.counter.update(now, s, body.trunk_lean_deg(p), hands)
                if self.counter.n_stands > before:
                    self.audio.play(self.ok_wav)
            n = self.counter.n_stands
            count_label = i18n.t("{n} of {total} stands", n=min(n, seated.TARGET_STANDS),
                                 total=seated.TARGET_STANDS)
            if self.counter.done and self._sts_done_at is None:
                self._sts_done_at = now
            done = (elapsed >= blk.duration_s or
                    (self._sts_done_at is not None
                     and now - self._sts_done_at >= STS_TAIL_S))
            frac = min(n, seated.TARGET_STANDS) / seated.TARGET_STANDS
            left_label = count_label

        # far-view HUD: one big line, one big count
        pw = min(560, w - 2 * theme.SAFE_MARGIN)
        px, py = (w - pw) // 2, 56
        c.panel(px, py, pw, 110, alpha=0.8)
        c.text(w // 2, py + 36, i18n.t(blk.cue), role="h2", anchor="mm",
               color="brand")
        c._dirty = True
        c.draw.text((w // 2, py + 80), count_label,
                    font=get_font("bold", 30), fill=theme.rgba("text", 1.0),
                    anchor="mm")
        c.progress_bar(theme.SAFE_MARGIN, h - 44, w - 2 * theme.SAFE_MARGIN,
                       min(1.0, frac), color="success", label=left_label)
        if self.pts is None:
            self.coach.say(i18n.t("Stay in the picture"), PRI_HAND)

        if done:
            self._end_block(now)

    def _end_block(self, now: float):
        blk = self.block
        self.audio.play(self.done_wav)
        self.windows[blk.key] = (self.record_start, now)
        blackouts = [b for b in self.monitor.blackouts
                     if framing.overlaps(b[0], b[1], [(self.record_start, now)])]
        t0 = self.record_start
        if blk.kind == LEG_AGILITY:
            cell = seated.analyse_leg(self.recorder.stamps, self.recorder.series,
                                      blackouts)
            self.raw_blocks[blk.key] = {
                "side": blk.side,
                "stamps": [round(t - t0, 3) for t in self.recorder.stamps],
                "lift": [[round(t - t0, 3), round(d, 3)]
                         for t, d in self.recorder.series],
                "threshold": [[round(t - t0, 3), round(lo, 3), round(hi, 3)]
                              for t, lo, hi in self.recorder.detector.threshold_series],
                "ref": self.refs.get(blk.key),
            }
        else:
            cell = seated.analyse_sts(self.counter, blackouts)
            self.raw_blocks[blk.key] = {
                "stand_index": [[round(t - t0, 3), round(s, 3)]
                                for t, s in self.counter.series],
                "stands": [{k: (round(v - t0, 3) if isinstance(v, float)
                                and k in ("start", "up", "down") else v)
                            for k, v in s.items()} for s in self.counter.stands],
                "failed_attempts": self.counter.failed,
                "ref": self.refs.get(blk.key),
            }
        self.raw_blocks[blk.key]["blackouts"] = [
            [round(a - t0, 3), round(b - t0, 3)] for a, b in blackouts]
        self.cells[blk.key] = cell
        if self.block_i + 1 < len(SEATED_ORDER):
            self.block_i += 1
            self._begin_block(now)
        else:
            self._finish(now)

    def _finish(self, now: float):
        self.monitor.finish()
        legs = {BLOCKS[k].side: self.cells.get(k) for k in SEATED_ORDER
                if BLOCKS[k].kind == LEG_AGILITY}
        sts = next((self.cells.get(k) for k in SEATED_ORDER
                    if BLOCKS[k].kind == SIT_TO_STAND), None)
        trusted = self.rec_trusted / self.rec_frames if self.rec_frames else 0.0
        self.results = gm.compute_metrics(legs=legs, sts=sts,
                                          trusted_frac=trusted,
                                          sides_checked=self.sides.checked,
                                          fps=self.fps)
        self.results["trusted_pct"] = round(100.0 * trusted, 1)
        self._save_session()
        self.goto(COMPLETE, now)

    def _save_session(self):
        r = self.results
        metrics = {k: v for k, v in r.items() if k not in ("legs", "sts")}
        # one line per block for the session list; the detail lives in raw
        metrics["blocks"] = {k: {kk: vv for kk, vv in (c or {}).items()}
                             for k, c in self.cells.items()}
        raw = {
            "setup": {"view": "side", "sides_checked": self.sides.checked,
                      "sides_swapped": self.sides.swapped, "tier": "seated"},
            "blocks": self.raw_blocks,
        }
        duration = sum(b - a for a, b in self.windows.values())
        fw, fh = self.frame_size
        try:
            self.saved_path = save_session(
                test="gait", mode="seated", hand=None,
                duration_s=duration,
                device={"camera_fps": round(self.fps, 1),
                        "resolution": f"{fw}x{fh}", "app_version": APP_VERSION,
                        "pose_model": "pose_landmarker_lite",
                        **capture_info(self.cap)},
                metrics=metrics, raw=raw)
        except OSError as e:
            self.saved_path = None
            print(f"[WARN] Could not save session: {e}")

    def screen_complete(self, c: Canvas, now: float):
        w, h = c.w, c.h
        r = self.results
        pw = min(620, w - 2 * theme.SAFE_MARGIN)
        bh = 42
        if r["scoreable"]:
            conf_off = 150
            table_off = conf_off + 62
            foot_off = table_off + 4 * 22 + 12
            btn_off = foot_off + 22
        else:
            reason = r.get("reason") or "Something went wrong - please try again."
            lines = i18n.wrap(i18n.t(reason), 50)[:3]
            btn_off = 108 + len(lines) * 26 + 12
        ph = btn_off + bh + 12
        px, py = (w - pw) // 2, max(40, min((h - ph) // 2, h - 30 - ph))
        c.panel(px, py, pw, ph, alpha=0.92)
        c.text(w // 2, py + 28, i18n.t("Walking Test - Results"), role="h2",
               anchor="mm")

        if r["scoreable"]:
            c.badge(w // 2, py + 48, i18n.t(r["label"]), r["status"])
            big = (f"{r['sts5_s']:.1f} s" if r.get("sts5_s") is not None
                   else f"{r.get('n_stands', 0)}/{seated.TARGET_STANDS}")
            c._dirty = True
            c.draw.text((w // 2, py + 104), big, font=get_font("mono", 36),
                        fill=theme.rgba("text", 1.0), anchor="mm")
            c.text(w // 2, py + 132, i18n.t("Five sit-to-stands"),
                   role="caption", color="text-muted", anchor="mm")
            conf = r.get("confidence_pct") or 0
            status = "success" if conf >= 75 else "info" if conf >= 45 else "warning"
            level = "High" if conf >= 75 else "Moderate" if conf >= 45 else "Low"
            reasons = r.get("confidence_reasons") or []
            cw = min(380, pw - 2 * theme.SPACE[4])
            c.confidence_card(px + (pw - cw) // 2, py + conf_off, cw,
                              label=i18n.t("Measurement confidence"),
                              value=i18n.t("{level} - {pct}%", level=i18n.t(level),
                                           pct=f"{conf:.0f}"),
                              detail=i18n.t(reasons[0]) if reasons else "",
                              progress=conf / 100.0, status=status)
            x0, x1 = px + theme.SPACE[4], px + pw - theme.SPACE[4]
            ty = py + table_off
            rows = []
            for side in ("right", "left"):
                cell = (r.get("legs") or {}).get(side) or {}
                if cell.get("scored"):
                    val = i18n.t("{hz} stamps/s, lift {amp}%",
                                 hz=f"{cell['rate_hz']:.1f}",
                                 amp=f"{cell['amp_pct']:.0f}"
                                 if cell.get("amp_pct") is not None else "-")
                else:
                    val = "-"
                rows.append((i18n.t(SIDE_NAMES[side]), val))
            rows.append((i18n.t("Rises"),
                         i18n.t("{n} stands, {f} failed, hands used {u}",
                                n=r.get("n_stands", 0),
                                f=r.get("failed_attempts", 0),
                                u=r.get("hands_used", 0))))
            weak = r.get("weaker_leg")
            rows.append((i18n.t("Left vs right"),
                         i18n.t("{leg} weaker", leg=i18n.t(SIDE_NAMES[weak]))
                         if weak else i18n.t("No clear difference")))
            for i, (k, v) in enumerate(rows):
                c.text(x0, ty + i * 22, k, role="caption", color="text-muted")
                c.text(x1, ty + i * 22, v, role="caption", anchor="ra")
            foot = [f"{r.get('fps', 0):.0f} fps"]
            if self.saved_path:
                foot.append(i18n.t("Saved: results/{name}",
                                   name=self.saved_path.name))
            c.text(w // 2, py + foot_off, "  ·  ".join(foot), role="caption",
                   color="text-muted", anchor="mm")
        else:
            c.badge(w // 2, py + 52, i18n.t("Couldn't score this run"), "warning")
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

    # ── drawing ───────────────────────────────────────────────────────────
    def _draw_skeleton(self, frame):
        """Drawn on the mirrored display frame, from the raw landmarks."""
        if self.pts is None:
            return
        fw = self.frame_size[0]
        pts = [(int(fw - x), int(y)) for x, y in self.pts]
        color = (148, 165, 18) if self.trusted else (60, 170, 245)   # BGR
        for a, b in body.EDGES:
            cv2.line(frame, pts[a], pts[b], color, 3, cv2.LINE_AA)
        for i in body.BODY:
            cv2.circle(frame, pts[i], 4, (250, 250, 248), -1, cv2.LINE_AA)

    def _draw_framing(self, c: Canvas):
        mon = self.monitor
        if mon.level not in (framing.CLIPPED, framing.NEAR):
            return
        pts = self._norm_body()
        along = None
        if pts:
            along = (sum(p[0] for p in pts) / len(pts),
                     sum(p[1] for p in pts) / len(pts))
        clipped = mon.level == framing.CLIPPED
        c.edge_alert(mon.edges, "warning", along, strong=clipped)
        if clipped:
            self.coach.say(i18n.t(body_hint(mon.edges)), PRI_EDGE)

    def _status_chips(self):
        if self.pts is None:
            chips = [(i18n.t("No one in view"), "warning")]
        elif self.monitor.level == framing.CLIPPED:
            chips = [(i18n.t("Body at the edge"), "warning")]
        else:
            chips = [(i18n.t("Body in view"), "success")]
        if self.sides.checked:
            chips.append((i18n.t("Sides checked"), "success"))
        if self.fps < 15:
            chips.append((f"{self.fps:.0f} fps", "warning"))
        return chips

    # ── main loop ─────────────────────────────────────────────────────────
    def run(self):
        screen_rec = ScreenRecorder("gait")
        win = "Walking Test  |  Q or close the window to quit"
        window_ready = False
        while self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                continue
            now = time.time()
            if self._last_frame_t is not None:
                dt = max(1e-3, now - self._last_frame_t)
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)
            self._last_frame_t = now
            fh, fw = frame.shape[:2]
            self.frame_size = (fw, fh)

            # Detect on the camera's own (already un-mirrored) picture, so the
            # model sees a person the right way round; mirror only for display.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.pts, self.vis = self.tracker.detect(rgb, now, (fw, fh))
            self.monitor.update(self._norm_body(), now)

            frame = cv2.flip(frame, 1)
            if not window_ready:
                create_display_window(win, frame.shape[1], frame.shape[0])
                cv2.setMouseCallback(win, self.on_mouse)
                window_ready = True
            self._draw_skeleton(frame)

            c = Canvas(frame)
            c.status_bar(self._status_chips(), i18n.t("Walking Test"))

            if self.state == IDLE:
                self.screen_idle(c, now)
            elif self.state == SETUP:
                self.screen_setup(c, now)
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

            if self.state in (SETUP, POSITION, COUNTDOWN, RECORDING):
                self._draw_framing(c)
                if self.pts is None and self.state != RECORDING:
                    self.coach.say(i18n.t("Stay in the picture"), PRI_SETUP)
            self.coach.render(c, now)

            cv2.imshow(win, screen_rec.frame(c.compose()))
            self.click = None
            key = cv2.waitKey(5) & 0xFF
            screen_rec.key(key)
            self.advance = key in KEY_ADVANCE
            if key == ord("q"):
                break
            if window_closed(win):
                break

        self.cap.release()
        screen_rec.close()
        cv2.destroyAllWindows()
        self.tracker.close()
        self.audio.close()
        print("\n[INFO] " + i18n.ct("Walking test closed."))


def main():
    source = select_camera_source()
    print("[INFO] " + i18n.ct("Opening camera and loading the pose model - a few seconds..."))
    cap = open_capture(source, fps=30)
    if cap is None:
        print("[ERROR] " + i18n.ct("Could not open camera."))
        pause_before_exit()
        sys.exit(1)
    # No mirroring check here: it needs a hand beside the face, close to the
    # camera. A saved answer is already applied by open_capture(); without one,
    # the arm-raise check settles left and right for this test.
    try:
        app = App(cap)
    except FileNotFoundError as e:          # the pose model is not in git
        print(f"[ERROR] {e}")
        cap.release()
        pause_before_exit()
        sys.exit(1)
    app.run()


if __name__ == "__main__":
    main()
