"""
Shared camera-source selection (audit A7).

The source is normally chosen in the launcher UI, which passes it down to the
tool it spawns through the ``HAND3D_CAMERA`` environment variable — so a
launched tool never stops to ask. Running a script straight from a terminal
still gets the interactive prompt: [1] local webcam (optionally an index) or
[2] an IP-camera stream URL, with Enter defaulting to webcam 0 so a bare
double-click keeps working.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

import cv2

# Remembers the capture config that actually worked, so a later run opens the
# camera once instead of probing (each probe = a visible camera-LED flash and
# ~1 s of dead time). Runtime state, git-ignored, alongside .launcher.pid.
_CACHE_PATH = Path(__file__).resolve().parents[1] / ".camera_cache.json"

# Set by launcher.py on the spawned tool's environment. An integer string is a
# webcam index; anything else is handed to OpenCV as a stream URL.
ENV_CAMERA = "HAND3D_CAMERA"


def preset_camera_source() -> int | str | None:
    """The source the launcher picked, or None when the tool was run directly."""
    raw = (os.environ.get(ENV_CAMERA) or "").strip()
    if not raw:
        return None
    return int(raw) if raw.isdigit() else raw


def describe_source(source: int | str) -> str:
    return f"webcam {source}" if isinstance(source, int) else str(source)


def select_camera_source() -> int | str:
    preset = preset_camera_source()
    if preset is not None:
        print(f"  Camera source: {describe_source(preset)}"
              f"  (set in the launcher)\n")
        return preset
    print("Camera source:")
    print("  [1] Webcam (default)  - or type an index, e.g. 0 / 1 / 2")
    print("  [2] IP stream URL")
    try:
        choice = input("Select [1]: ").strip()
    except EOFError:
        choice = ""
    if choice == "2":
        try:
            url = input("Stream URL: ").strip()
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


def _load_cached(key: str) -> list | None:
    """The [backend, mjpg] combo that last worked for this source, if any."""
    try:
        entry = json.loads(_CACHE_PATH.read_text("utf-8")).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    if (isinstance(entry, list) and len(entry) == 2
            and isinstance(entry[1], bool)):
        return entry
    return None


def _store_cached(key: str, combo: tuple) -> None:
    """Remember a working combo; a read-only checkout just means no cache."""
    try:
        try:
            data = json.loads(_CACHE_PATH.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[key] = [combo[0], combo[1]]
        _CACHE_PATH.write_text(json.dumps(data), "utf-8")
    except OSError:
        pass


def open_capture(source: int | str, width: int = 640, height: int = 480,
                 fps: int | None = None):
    """Open the capture; returns cv2.VideoCapture or None on failure.

    For integer webcam sources on Windows we prefer the DirectShow backend over
    OpenCV's default (MSMF): measured lower read latency and no MSMF decode-thread
    contention spikes that otherwise stall MediaPipe inference (see
    docs/FPS_INVESTIGATION_PLAN.md). Each candidate is verified with a real test
    read, and we fall back gracefully so a camera that works today never
    regresses:  DSHOW+MJPG -> DSHOW (no MJPG) -> MSMF+MJPG -> MSMF (no MJPG).

    Every candidate that has to be tried costs a camera open — a visible LED
    flash plus ~1 s of warm-up — so the combo that succeeds is cached to
    `.camera_cache.json` and tried first next time: steady state is one open.
    A stale cache entry simply fails its test read and the full probe resumes.

    `fps` is requested during configuration rather than by re-setting the
    property after opening, which would renegotiate the stream (another flash).
    IP-stream (str) sources and non-Windows platforms use OpenCV's default open.
    """
    if not isinstance(source, int):
        cap = cv2.VideoCapture(source)
        return cap if cap.isOpened() else (cap.release() or None)

    if sys.platform.startswith("win"):
        candidates = [(cv2.CAP_DSHOW, True), (cv2.CAP_DSHOW, False),
                      (cv2.CAP_MSMF, True), (cv2.CAP_MSMF, False)]
    else:
        candidates = [(None, True), (None, False)]

    key = f"{source}|{width}x{height}|{fps or 0}"
    cached = _load_cached(key)
    if cached is not None:
        combo = (cached[0], cached[1])
        if combo in candidates:
            candidates.remove(combo)
        candidates.insert(0, combo)

    for combo in candidates:
        backend, mjpg = combo
        cap = (cv2.VideoCapture(source, backend) if backend is not None
               else cv2.VideoCapture(source))
        if cap.isOpened():
            _configure(cap, width, height, mjpg, fps)
            ok, _frame = cap.read()   # verify frames actually flow
            if ok:
                if cached != [combo[0], combo[1]]:
                    _store_cached(key, combo)
                return cap
        cap.release()
    return None


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
