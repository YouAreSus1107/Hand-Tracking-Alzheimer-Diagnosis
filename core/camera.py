"""
Shared camera-source selection (audit A7).

The source is normally chosen in the launcher UI, which passes it down to the
tool it spawns through the ``HAND3D_CAMERA`` environment variable — so a
launched tool never stops to ask. Running a script straight from a terminal
still gets the interactive prompt: [1] local webcam (optionally an index) or
[2] an IP-camera stream URL, with Enter defaulting to webcam 0 so a bare
double-click keeps working.

open_capture() also undoes a camera that mirrors its own picture, so every
tool reads the same unmirrored frame from any camera (core/orientation.py).
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path

import cv2

from core import i18n, orientation

# Remembers the capture config that actually worked, so a later run opens the
# camera once instead of probing (each probe = a visible camera-LED flash and
# ~1 s of dead time). Runtime state, git-ignored, alongside .launcher.pid.
_CACHE_PATH = Path(__file__).resolve().parents[1] / ".camera_cache.json"

# Set by launcher.py on the spawned tool's environment. An integer string is a
# webcam index; anything else is handed to OpenCV as a stream URL.
ENV_CAMERA = "HAND3D_CAMERA"
# The camera's name, when the launcher knows it. Saved with each session so a
# person's own-baseline comparison of opening size only uses the same camera
# (core/tapping/baseline.py). Empty for streams and direct runs.
ENV_CAMERA_NAME = "HAND3D_CAMERA_NAME"


def preset_camera_name() -> str:
    return (os.environ.get(ENV_CAMERA_NAME) or "").strip()


def preset_camera_source() -> int | str | None:
    """The source the launcher picked, or None when the tool was run directly."""
    raw = (os.environ.get(ENV_CAMERA) or "").strip()
    if not raw:
        return None
    return int(raw) if raw.isdigit() else raw


def describe_source(source: int | str) -> str:
    return (i18n.ct("webcam {n}", n=source) if isinstance(source, int)
            else str(source))


def pause_before_exit() -> None:
    """Keep a launcher-spawned console open long enough to read the error above.

    launcher.py runs each tool in its own CREATE_NEW_CONSOLE window; with no
    pause here that window closes the instant the process exits, so a camera
    failure prints and is gone before anyone can read it — it just looks like
    the test silently refused to launch.
    """
    try:
        input("\n" + i18n.ct("Press Enter to close..."))
    except EOFError:
        pass


def select_camera_source() -> int | str:
    preset = preset_camera_source()
    if preset is not None:
        print("  " + i18n.ct("Camera source: {source}  (set in the launcher)",
                             source=describe_source(preset)) + "\n")
        return preset
    print(i18n.ct("Camera source:"))
    print("  [1] " + i18n.ct("Webcam (default)  - or type an index, e.g. 0 / 1 / 2"))
    print("  [2] " + i18n.ct("IP stream URL"))
    try:
        choice = input(i18n.ct("Select [1]: ")).strip()
    except EOFError:
        choice = ""
    if choice == "2":
        try:
            url = input(i18n.ct("Stream URL: ")).strip()
        except EOFError:
            url = ""
        return url or 0
    if choice.isdigit() and choice != "1":
        return int(choice)
    return 0


def _configure(cap, width: int, height: int, mjpg: bool,
               fps: int | None = None) -> None:
    """Apply capture properties (best-effort; unsupported ones are ignored)."""
    if mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps:
        cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # keep only the latest frame (low latency)


# A candidate delivering less than this share of the requested frame rate is
# kept only as a fallback. The Razer Kiyo V2 X is why: over DirectShow its
# driver reports 60 fps, ignores the MJPG request and delivers 30 in YUY2,
# while MSMF delivers a true 60 (measured 2026-09-28,
# docs/tests/TREMOR_RESTRUCTURE_PLAN.md §1). A driver's word is not evidence.
DELIVER_FRAC = 0.85
BETTER_BY = 1.25          # a less-preferred backend must beat the best by this
# MSMF hands over a burst of buffered frames right after opening: with 3
# warm-up frames the Razer "measured" 95 fps and the 30 fps ASUS 32. Ten
# drain it; the rate is then timed between the first and last arrival.
MEASURE_WARMUP = 10
MEASURE_FRAMES = 20       # ~0.33 s at 60 fps, ~0.67 s at 30

_BACKEND_NAMES = {cv2.CAP_DSHOW: "DSHOW", cv2.CAP_MSMF: "MSMF"}


def _cache_key(source: int | str, width: int, height: int,
               fps: int | None) -> str:
    """Keyed by the camera's name when the launcher knows it: indices shift
    when cameras are plugged in or out, and an index key would hand one
    camera's backend to whichever camera lands on that index next."""
    name = preset_camera_name() if isinstance(source, int) else ""
    who = f"name:{name}" if name else str(source)
    return f"{who}|{width}x{height}|{fps or 0}"


def _load_cached(key: str) -> list | None:
    """The [backend, mjpg, measured_fps, ask_fps] that last worked for this
    key, if any. Older two- and three-element entries are still honoured."""
    try:
        entry = json.loads(_CACHE_PATH.read_text("utf-8")).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    if (isinstance(entry, list) and len(entry) in (2, 3, 4)
            and isinstance(entry[1], bool)):
        return entry
    return None


def _store_cached(key: str, combo: tuple, measured: float | None) -> None:
    """Remember a working combo; a read-only checkout just means no cache."""
    try:
        try:
            data = json.loads(_CACHE_PATH.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        entry = [combo[0], combo[1]]
        if measured is not None:
            entry.append(round(measured, 1))
            if len(combo) > 2 and not combo[2]:
                entry.append(False)      # opened without asking for a rate
        data[key] = entry
        _CACHE_PATH.write_text(json.dumps(data), "utf-8")
    except OSError:
        pass


def _fourcc_str(cap) -> str:
    try:
        v = int(cap.get(cv2.CAP_PROP_FOURCC))
    except (cv2.error, TypeError, ValueError):
        return ""
    s = "".join(chr((v >> 8 * i) & 0xFF) for i in range(4))
    return s if s.isprintable() and s.strip() else ""


def measure_fps(cap, frames: int = MEASURE_FRAMES,
                warmup: int = MEASURE_WARMUP) -> float:
    """Frames per second actually delivered, timed over `frames` reads."""
    for _ in range(warmup):
        cap.read()
    stamps = []
    for _ in range(frames):
        ok, _f = cap.read()
        if ok:
            stamps.append(time.perf_counter())
    if len(stamps) < 2 or stamps[-1] <= stamps[0]:
        return 0.0
    return (len(stamps) - 1) / (stamps[-1] - stamps[0])


class Capture:
    """A cv2.VideoCapture whose read() undoes a camera's own mirroring.

    `mirrored` starts from the answer saved for this source (core/orientation.py)
    and is set by core/mirror_check.py when the source has never been checked.
    Everything else is passed straight through to the wrapped capture.

    It also says what was actually negotiated (`info()`, saved in each
    session's `device` block), and `frame_time_ms()` gives the device's own
    timestamp for the frame just read when the backend has one: MSMF's
    CAP_PROP_POS_MSEC steps exactly one frame period per frame, and jumps by
    whole periods over frames that were not read, where host read times
    jitter by ±7 ms (measured on the Razer at 60 fps, 2026-09-28).
    """

    def __init__(self, cap, source: int | str, backend: int | None = None,
                 fps_requested: int | None = None,
                 fps_measured: float | None = None):
        self._cap = cap
        self.source = source
        self.mirrored = bool(orientation.load(source))
        self.backend = _BACKEND_NAMES.get(backend, "default") \
            if backend is not None else "default"
        self.fps_requested = fps_requested
        self.fps_measured = fps_measured

    def read(self):
        ok, frame = self._cap.read()
        if ok and self.mirrored:
            frame = cv2.flip(frame, 1)
        return ok, frame

    def frame_time_ms(self) -> float | None:
        """Device timestamp (ms) of the last frame read, or None when this
        backend has no trustworthy one (DSHOW reports nothing useful)."""
        if self.backend != "MSMF":
            return None
        try:
            v = float(self._cap.get(cv2.CAP_PROP_POS_MSEC))
        except (cv2.error, TypeError, ValueError):
            return None
        return v if v > 0 else None

    def info(self) -> dict:
        """What was negotiated, for a session's `device` block."""
        try:
            drv = float(self._cap.get(cv2.CAP_PROP_FPS))
        except (cv2.error, TypeError, ValueError):
            drv = -1.0
        return {
            "backend": self.backend,
            "fourcc": _fourcc_str(self._cap),
            "fps_requested": self.fps_requested,
            "fps_driver": round(drv, 1) if drv > 0 else None,
            "fps_measured": (round(self.fps_measured, 1)
                             if self.fps_measured else None),
        }

    def __getattr__(self, name):
        return getattr(self._cap, name)


def capture_info(cap) -> dict:
    """The `device` fields every camera test saves: which camera, and what
    the capture really negotiated. Tolerates any capture-like object (the
    run-loop harness passes a fake), which then just reports the name."""
    out = {"camera_name": preset_camera_name()}
    info = getattr(cap, "info", None)
    if callable(info):
        try:
            out.update(info())
        except Exception:  # noqa: BLE001 - provenance must never end a run
            pass
    return out


def open_capture(source: int | str, width: int = 640, height: int = 480,
                 fps: int | None = None) -> Capture | None:
    """Open the capture; returns a Capture (see above) or None on failure.

    Frames come back unmirrored whatever the camera does, provided the camera
    has been checked (core/mirror_check.ensure_orientation).

    For integer webcam sources on Windows we prefer the DirectShow backend over
    OpenCV's default (MSMF): measured lower read latency and no MSMF decode-thread
    contention spikes that otherwise stall MediaPipe inference (see
    docs/performance/FPS_FINDINGS.md). Each candidate is verified with a real test read, and
    we fall back gracefully so a camera that works today never regresses:
    DSHOW+MJPG -> DSHOW (no MJPG) -> MSMF+MJPG -> MSMF (no MJPG).

    Every candidate that has to be tried costs a camera open — a visible LED
    flash plus ~1 s of warm-up — so the combo that succeeds is cached to
    `.camera_cache.json` and tried first next time: steady state is one open.
    A stale cache entry simply fails its test read and the full probe resumes.

    `fps` is requested during configuration rather than by re-setting the
    property after opening, which would renegotiate the stream (another flash).

    When `fps` is asked for, the request itself is not trusted: each
    candidate's delivered rate is timed (~0.5 s), and the first to reach
    DELIVER_FRAC of it is taken. Measured 2026-09-28: the Razer Kiyo V2 X
    delivers 30 over DirectShow whatever is asked and 60 over MSMF; the ASUS
    delivers 30 over DirectShow when NO rate is asked, but only 15 when 60 is
    (or MJPG, which it lacks), and 30 over MSMF. So the preferred backend is
    also tried without the rate request, and when nothing reaches the rate
    the most-preferred candidate within BETTER_BY of the best is reopened.
    The answer is cached, so only the first launch pays for the probe.
    IP-stream (str) sources and non-Windows platforms use OpenCV's default open.
    """
    if not isinstance(source, int):
        cap = cv2.VideoCapture(source)
        return Capture(cap, source) if cap.isOpened() else (cap.release() or None)

    # (backend, mjpg, ask for the rate), in order of preference: DSHOW first
    # (lower read latency, no MSMF decode-thread contention, FPS_FINDINGS.md).
    if sys.platform.startswith("win"):
        pref = [(cv2.CAP_DSHOW, True), (cv2.CAP_DSHOW, False),
                (cv2.CAP_MSMF, True), (cv2.CAP_MSMF, False)]
    else:
        pref = [(None, True), (None, False)]
    if fps:
        candidates = ([(b, m, True) for b, m in pref[:2]]
                      + [(pref[1][0], False, False)]
                      + [(b, m, True) for b, m in pref[2:]])
    else:
        candidates = [(b, m, False) for b, m in pref]
    order = list(candidates)

    key = _cache_key(source, width, height, fps)
    cached = _load_cached(key)
    cached_combo = None
    if cached is not None:
        cached_combo = (cached[0], cached[1],
                        bool(fps) and (cached[3] if len(cached) > 3 else True))
        if cached_combo in candidates:
            candidates.remove(cached_combo)
        candidates.insert(0, cached_combo)
    want = DELIVER_FRAC * fps if fps else 0.0

    # The source index is DirectShow's (the launcher resolves the chosen
    # camera's name against DirectShow's list). MSMF numbers cameras by Media
    # Foundation's own list, which skips DirectShow-only virtual cameras, so
    # the same integer can open a different camera there. Mapped by name once,
    # on the first MSMF attempt; None means MSMF cannot see this camera at all.
    msmf = {}

    def index_for(backend):
        if backend != getattr(cv2, "CAP_MSMF", None):
            return source
        if "i" not in msmf:
            from core.camera_list import msmf_index
            msmf["i"] = msmf_index(preset_camera_name(), source)
        return msmf["i"]

    def attempt(combo):
        backend, mjpg, ask = combo
        idx = index_for(backend)
        if idx is None:
            return None, None
        cap = (cv2.VideoCapture(idx, backend) if backend is not None
               else cv2.VideoCapture(idx))
        if cap.isOpened():
            _configure(cap, width, height, mjpg, fps if ask else None)
            ok, _frame = cap.read()   # verify frames actually flow
            if ok:
                return cap, (measure_fps(cap) if fps else None)
        cap.release()
        return None, None

    def done(cap, combo, measured):
        if (cached is None or cached_combo != combo
                or (fps and len(cached) < 3)):
            _store_cached(key, combo, measured)
        return Capture(cap, source, combo[0], fps, measured)

    tried = []                         # (measured, combo) of the short ones
    for combo in candidates:
        cap, measured = attempt(combo)
        if cap is None:
            continue
        # A cached answer that was already the best this camera could do
        # stands while it still delivers what it did then; otherwise every
        # launch of a 30 fps camera would re-probe every candidate.
        floor = want
        if cached is not None and len(cached) >= 3 and fps and combo == cached_combo:
            floor = min(want, DELIVER_FRAC * cached[2])
        if not fps or measured >= floor:
            return done(cap, combo, measured)
        cap.release()                  # a device opens once: release before the next
        tried.append((measured, combo))

    if not tried:
        return None
    # Nothing reached the rate. The most-preferred candidate within BETTER_BY
    # of the best wins: a later backend has to be clearly faster, not 29.5
    # against 29.3 -- which is how the ASUS first landed on MSMF.
    top = max(m for m, _ in tried)
    rank = lambda c: order.index(c) if c in order else len(order)  # noqa: E731
    pick = min((c for m, c in tried if m * BETTER_BY >= top), key=rank)
    cap, measured = attempt(pick)
    if cap is None:
        return None
    return done(cap, pick, measured)


def _screen_size() -> tuple[int, int]:
    """Primary-monitor pixel size (Windows). Falls back to 1280x720."""
    try:
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return 1280, 720


def create_display_window(name: str, frame_w: int, frame_h: int,
                          screen_fraction: float = 0.9) -> None:
    """Create a resizable, aspect-locked window sized to fit the screen.

    Uses WINDOW_NORMAL (keeps the OS title bar with minimize / maximize /
    close ✕) plus WINDOW_KEEPRATIO so the camera image is letterboxed rather
    than stretched — no horizontal distortion, even if the user resizes.
    The window is opened at the largest whole-screen-fraction scale of the
    frame that still fits, preserving aspect ratio.
    """
    cv2.namedWindow(name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    sw, sh = _screen_size()
    scale = min(sw * screen_fraction / frame_w, sh * screen_fraction / frame_h)
    cv2.resizeWindow(name, max(int(frame_w * scale), frame_w // 2),
                     max(int(frame_h * scale), frame_h // 2))


def window_closed(name: str) -> bool:
    """True once the user clicks the window's ✕ (or it is otherwise gone)."""
    try:
        return cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True
