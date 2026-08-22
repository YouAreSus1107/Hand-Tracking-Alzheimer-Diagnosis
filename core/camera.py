"""
Shared camera-source selection (audit A7) — the same prompt every tool uses:
[1] local webcam (optionally an index) or [2] an IP-camera stream URL.
Enter defaults to webcam 0 so a bare double-click still works.
"""

from __future__ import annotations

import ctypes
import sys

import cv2


def select_camera_source() -> int | str:
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


def _configure(cap, width: int, height: int, mjpg: bool) -> None:
    """Apply capture properties (best-effort; unsupported ones are ignored)."""
    if mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # keep only the latest frame (low latency)


def open_capture(source: int | str, width: int = 640, height: int = 480):
    """Open the capture; returns cv2.VideoCapture or None on failure.

    For integer webcam sources on Windows we prefer the DirectShow backend over
    OpenCV's default (MSMF): measured lower read latency and no MSMF decode-thread
    contention spikes that otherwise stall MediaPipe inference (see
    docs/FPS_INVESTIGATION_PLAN.md). Each backend is verified with a real test
    read, and we fall back gracefully so a camera that works today never regresses:
      DSHOW+MJPG -> DSHOW (no MJPG) -> MSMF+MJPG -> MSMF (no MJPG).
    IP-stream (str) sources and non-Windows platforms use OpenCV's default open.
    """
    if not isinstance(source, int):
        cap = cv2.VideoCapture(source)
        return cap if cap.isOpened() else (cap.release() or None)

    backends = ([cv2.CAP_DSHOW, cv2.CAP_MSMF]
                if sys.platform.startswith("win") else [None])
    for backend in backends:
        for mjpg in (True, False):   # MJPG helps USB webcams; some cams reject it
            cap = (cv2.VideoCapture(source, backend) if backend is not None
                   else cv2.VideoCapture(source))
            if cap.isOpened():
                _configure(cap, width, height, mjpg)
                ok, _frame = cap.read()   # verify frames actually flow
                if ok:
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
