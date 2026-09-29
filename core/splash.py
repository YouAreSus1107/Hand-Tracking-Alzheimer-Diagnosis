"""
Console loading screen for the cold-start import gap.

`import cv2` + `import mediapipe` costs ~2 s warm but ~10 s cold — the first
launch after a reboot, or any time Defender/OneDrive has to re-scan the ~130 MB
of native extensions under `.venv`. All of it happens *before* a tool's first
`print()`, so the console the launcher opens sits completely blank and reads as
hung (that is the wait, not the camera). See docs/performance/COLD_START.md.

This module is deliberately stdlib-only and import-cheap, because it runs above
those imports:

    from core.splash import Splash, IMPORT_STEPS   # keep above the heavy imports
    _splash = Splash("Finger Tapping Test", "Modes: ...", IMPORT_STEPS,
                     enabled=__name__ == "__main__")
    import cv2
    _splash.step()                                 # OpenCV stage done
    import mediapipe as mp
    _splash.step()                                 # MediaPipe stage done
    ...
    _splash.done()

On a VT-capable console (Windows Terminal, or conhost since Win10 1703) this
paints a themed loading screen in place: brand header, weighted progress bar,
current stage and elapsed seconds. Elsewhere it degrades to one spinner line.

Every word it prints goes through `i18n.ct()`, so a run the hub launched in
Chinese loads in Chinese, and a console that cannot show CJK (a legacy code
page, or conhost in a Latin font) stays English rather than printing boxes.
Callers pass English; the title, subtitle and stage labels are looked up here.

The bar never lies about a stage it has not finished: within a stage it eases
asymptotically toward that stage's ceiling and only snaps to it on `step()`.
"""

from __future__ import annotations

import atexit
import math
import os
import shutil
import sys
import threading
import time

from core import i18n

# ── Stage tables ───────────────────────────────────────────────────────────
# (label, share of total load time) — measured cold on the reference machine:
# cv2 ~4.6 s, mediapipe ~6.2 s, the pure-python engine modules well under 1 s.
IMPORT_STEPS = (("OpenCV", 0.40), ("MediaPipe", 0.54), ("Test engine", 0.06))
# The oculomotor test never imports mediapipe directly; core.gaze.tracker does.
GAZE_IMPORT_STEPS = (("OpenCV", 0.42), ("Gaze engine + MediaPipe", 0.58))
# The speech test has no camera and no MediaPipe; OpenCV is only its window.
SPEECH_IMPORT_STEPS = (("OpenCV", 0.70), ("Audio engine", 0.30))

# ── Palette (mirrors core/ui/theme.py; duplicated so this stays import-cheap)
_BRAND = (0x12, 0xA5, 0x94)
_TEXT = (0xF8, 0xFA, 0xFC)
_MUTED = (0x94, 0xA3, 0xB8)
_DIM = (0x64, 0x74, 0x8B)

_TAU = 3.0          # s — easing constant for the within-stage creep
_TICK = 0.08
_SLOW_S = 4.0       # after this long, explain the wait instead of just spinning
_FRAMES = "|/-\\"
_BODY_LINES = 4     # bar, blank, status, hint


def _rgb(color: tuple[int, int, int]) -> str:
    return f"\x1b[38;2;{color[0]};{color[1]};{color[2]}m"


_RESET = "\x1b[0m"


def set_console_title(title: str) -> None:
    """Name the console window (it otherwise shows the python.exe path)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:                       # noqa: BLE001 - cosmetic only
        pass


def _enable_vt() -> bool:
    """True once the console understands ANSI escapes (enabling them if needed)."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:                       # noqa: BLE001 - odd stdout wrappers
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_vt = 0x0004                           # VIRTUAL_TERMINAL_PROCESSING
        if mode.value & enable_vt:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | enable_vt))
    except Exception:                       # noqa: BLE001 - no console at all
        return False


def _unicode_ok() -> bool:
    try:
        "█░─".encode(sys.stdout.encoding or "ascii")
        return True
    except Exception:                       # noqa: BLE001 - legacy code page
        return False


class Splash:
    """Loading screen covering a slow module-import block."""

    def __init__(self, title: str, subtitle: str | None = None,
                 steps: tuple[tuple[str, float], ...] = IMPORT_STEPS,
                 enabled: bool = True):
        self.enabled = enabled
        self._steps = steps
        self._index = 0                 # stages completed
        self._t0 = time.perf_counter()
        self._t_stage = self._t0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._painted = False           # a body block is on screen
        self._final = ""                # status text once finished
        self._vt = False
        if not enabled:
            return

        title = i18n.ct(title)
        subtitle = i18n.ct(subtitle) if subtitle else subtitle
        set_console_title(f"{title} - Hand Detection 3D")
        self._vt = _enable_vt()
        if self._vt:
            self._fill, self._empty, self._rule, self._mark = (
                "█", "░", "─", "▸")
            if not _unicode_ok():
                self._fill, self._empty, self._rule, self._mark = "#", ".", "-", ">"
            self._header(title, subtitle)
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        else:                           # piped, redirected, or a dumb terminal
            print("=" * 52)
            print(f"  {title}")
            if subtitle:
                print(f"  {subtitle}")
            print("=" * 52)
            print(f"  {self._loading()}", flush=True)
        atexit.register(self._teardown)

    # ── geometry ───────────────────────────────────────────────────────────
    @property
    def _width(self) -> int:
        try:
            cols = shutil.get_terminal_size((60, 24)).columns
        except Exception:                   # noqa: BLE001
            cols = 60
        return max(34, min(cols - 2, 64))

    def _label(self) -> str:
        index = min(self._index, len(self._steps) - 1)
        return i18n.ct(self._steps[index][0])

    def _loading(self) -> str:
        return i18n.ct("Loading {what}...", what=self._label())

    def _fraction(self) -> float:
        """Completed stages, plus an eased creep through the current one."""
        if self._index >= len(self._steps):
            return 1.0
        base = sum(w for _, w in self._steps[:self._index])
        share = self._steps[self._index][1]
        elapsed = time.perf_counter() - self._t_stage
        return base + share * (1.0 - math.exp(-elapsed / _TAU))

    # ── painting ───────────────────────────────────────────────────────────
    def _write(self, text: str) -> None:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:                   # noqa: BLE001 - console went away
            self._stop.set()

    def _header(self, title: str, subtitle: str | None) -> None:
        width = self._width
        lines = [
            "",
            f"  {_rgb(_BRAND)}HAND DETECTION 3D{_RESET}",
            f"  {_rgb(_DIM)}{self._rule * (width - 2)}{_RESET}",
            "",
            f"  {_rgb(_TEXT)}{title}{_RESET}",
        ]
        if subtitle:
            lines.append(f"  {_rgb(_MUTED)}{subtitle}{_RESET}")
        lines.append("")
        self._write("\x1b[2J\x1b[H\x1b[?25l" + "\n".join(lines) + "\n")

    def _body(self) -> list[str]:
        """The four repainted lines: bar, blank, status, hint.

        Right edges are laid out from the *plain* text lengths — the color
        escapes are zero-width on screen but not in `len()`.
        """
        width = self._width
        bar_w = width - 12
        frac = 1.0 if self._final else self._fraction()
        filled = int(round(bar_w * frac))
        bar = (f"{_rgb(_BRAND)}{self._fill * filled}{_RESET}"
               f"{_rgb(_DIM)}{self._empty * (bar_w - filled)}{_RESET}")
        pct = f"{frac * 100:3.0f}%"
        bar_line = (f"  {bar}{' ' * max(1, width - 2 - bar_w - len(pct))}"
                    f"{_rgb(_MUTED)}{pct}{_RESET}")

        elapsed = time.perf_counter() - self._t0
        if self._final:                     # the elapsed time is in the text
            mark, text, clock = self._mark, self._final, ""
        else:
            mark = _FRAMES[int(elapsed / _TICK) % len(_FRAMES)]
            text, clock = self._loading(), f"{elapsed:5.1f}s"
        # Columns, not len(): a CJK character is one char but two cells wide.
        gap = " " * max(2, width - 6 - i18n.text_width(text) - len(clock))
        status = (f"  {_rgb(_BRAND)}{mark}{_RESET} {_rgb(_TEXT)}{text}{_RESET}"
                  f"{gap}{_rgb(_DIM)}{clock}{_RESET}")

        hint = ""
        if not self._final and elapsed > _SLOW_S:
            hint = i18n.ct(
                "First launch reads ~130 MB of vision libraries from disk.")
        elif self._final and elapsed > _SLOW_S + 2.0:
            hint = i18n.ct("Slow cold start - see "
                           "docs/performance/COLD_START.md to speed it up.")
        if hint:
            hint = f"  {_rgb(_DIM)}{hint}{_RESET}"

        return [bar_line, "", status, hint]

    def _paint(self) -> None:
        with self._lock:
            if self._stop.is_set() and not self._final:
                return
            out = f"\x1b[{_BODY_LINES}A" if self._painted else ""
            out += "".join(f"\x1b[2K{line}\n" for line in self._body())
            self._painted = True
            self._write(out)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._paint()
            self._stop.wait(_TICK)

    def _teardown(self) -> None:
        """Stop the painter and put the cursor back (also runs on a crash)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None
        if self._vt:
            self._write("\x1b[?25h")

    # ── public ─────────────────────────────────────────────────────────────
    def step(self) -> None:
        """Mark the current import stage complete and advance the bar."""
        if not self.enabled:
            return
        self._index = min(self._index + 1, len(self._steps))
        self._t_stage = time.perf_counter()
        if self._vt:
            self._paint()
        elif self._index < len(self._steps):
            print(f"  {self._loading()}", flush=True)

    def done(self, note: str = "Ready") -> None:
        if not self.enabled:
            return
        self.enabled = False
        self._index = len(self._steps)
        elapsed = time.perf_counter() - self._t0
        self._final = i18n.ct("{note} in {secs} s", note=i18n.ct(note),
                              secs=f"{elapsed:.1f}")
        self._teardown()
        if self._vt:
            self._paint()
            self._write("\n")
        else:
            print(f"  {self._final}\n", flush=True)
