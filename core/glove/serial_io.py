"""Serial transport for the sensor glove — the I/O half of ``core.glove``.

Owns the COM port in a background thread, parses lines through the pure
``protocol`` module, and keeps a bounded ring buffer the web UI can poll.

pyserial is an **optional** dependency: ``launcher.py`` must keep running (and
stay PyInstaller-packageable) on a machine that has never touched the glove, so
the import is guarded and ``HAS_PYSERIAL`` is the flag callers check first.
"""

from __future__ import annotations

import csv
import importlib
import os
import threading
import time
from collections import deque
from datetime import datetime

from .force import (conductance_us, force_model, force_newtons, force_range,
                    grams_force)
from .protocol import (PROTO_SUPPORTED, FrameAccumulator, GloveFrame,
                       adc_to_mv, sensor_ohms)

serial = None       # type: ignore[assignment]
_list_ports = None  # type: ignore[assignment]
HAS_PYSERIAL = False


def has_pyserial() -> bool:
    """Is pyserial importable *right now*?

    Deliberately re-checked on each call rather than frozen at import time: the
    Developer page can install pyserial into the running interpreter, and a
    cached False would keep reporting "missing" until the hub was restarted.
    """
    global serial, _list_ports, HAS_PYSERIAL
    if HAS_PYSERIAL:
        return True
    importlib.invalidate_caches()   # pick up a package installed since startup
    try:
        import serial as _serial
        from serial.tools import list_ports as _lp
    except ImportError:
        return False
    serial, _list_ports, HAS_PYSERIAL = _serial, _lp, True
    return True


has_pyserial()   # opportunistic first attempt, so the common case is resolved

BAUD = 115200          # ignored by native USB CDC, but harmless and correct for AVR
FRAME_BUFFER = 6000    # 60 s at 100 Hz
CONSOLE_LINES = 200    # raw lines kept for the on-page serial console
COMMANDS = ("?", "S", "X", "Z", "D")

#: USB vendor ID of Arduino SA — how the Nano 33 BLE identifies itself.
ARDUINO_VID = 0x2341


def list_ports() -> list[dict]:
    """Enumerate serial ports, flagging the ones that look like the glove.

    Returns ``[]`` when pyserial is missing — callers must check
    :func:`has_pyserial` first, because "no ports" and "cannot look" are
    different answers and must not be shown to the user as the same thing.
    """
    if not has_pyserial():
        return []
    out: list[dict] = []
    for p in _list_ports.comports():
        out.append({
            "port": p.device,
            "description": p.description or "",
            "hwid": p.hwid or "",
            "is_glove": p.vid == ARDUINO_VID,
        })
    # Likely boards first, then natural port order.
    out.sort(key=lambda d: (not d["is_glove"], d["port"]))
    return out


def default_port() -> str | None:
    """Best guess at the glove's port, or None if nothing looks like it."""
    for p in list_ports():
        if p["is_glove"]:
            return p["port"]
    return None


class GloveReader:
    """Background serial reader with a polled ring buffer.

    Thread-safety: every mutable field is touched only under ``_lock``. The
    reader thread appends; HTTP handler threads read snapshots.
    """

    def __init__(self, results_dir: str):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ser = None

        self._frames: deque[tuple[GloveFrame, float]] = deque(maxlen=FRAME_BUFFER)
        self._console: deque[str] = deque(maxlen=CONSOLE_LINES)
        self._acc = FrameAccumulator()

        self.port: str | None = None
        self.last_error: str = ""
        self._connected_at: float = 0.0

        self._results_dir = results_dir
        self._csv_file = None
        self._csv_writer = None
        self._csv_path: str | None = None
        self._csv_rows = 0

    # ── lifecycle ─────────────────────────────────────────────────────────

    def connect(self, port: str) -> tuple[bool, str]:
        if not has_pyserial():
            return False, "pyserial is not installed. Use the Install pyserial button."
        if self.is_connected():
            return False, f"Already connected to {self.port}."
        if not port:
            return False, "No port selected."

        try:
            ser = serial.Serial(port, BAUD, timeout=0.2)
        except Exception as exc:  # noqa: BLE001 - pyserial raises several types
            # Windows allows exactly one owner per COM port, and this is by far
            # the most common failure, so name the likely culprit rather than
            # surfacing a bare OS error.
            hint = ""
            if "denied" in str(exc).lower() or "PermissionError" in type(exc).__name__:
                hint = (" — the port is held by something else. Close the Arduino "
                        "Serial Monitor or press_test.ps1 and try again.")
            return False, f"Could not open {port}: {exc}{hint}"

        # The firmware's `if (!Serial)` guard reflects DTR: without this it
        # treats the host as absent and drops every frame.
        try:
            ser.dtr = True
        except OSError:
            pass

        with self._lock:
            self._ser = ser
            self.port = port
            self.last_error = ""
            self._frames.clear()
            self._console.clear()
            self._acc = FrameAccumulator()
            self._connected_at = time.time()

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="glove-reader", daemon=True)
        self._thread.start()

        # Let the native-USB port settle, then ask for the banner and stream.
        time.sleep(0.8)
        self.send_command("?")
        self.send_command("S")
        return True, f"Connected to {port}."

    def disconnect(self) -> tuple[bool, str]:
        if not self.is_connected():
            return False, "Not connected."
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.5)
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:  # noqa: BLE001
                    pass
            self._ser = None
            was = self.port
            self.port = None
        self.stop_recording()
        return True, f"Disconnected from {was}."

    def is_connected(self) -> bool:
        with self._lock:
            return self._ser is not None

    # ── reader thread ─────────────────────────────────────────────────────

    def _run(self) -> None:
        buf = b""
        while not self._stop.is_set():
            with self._lock:
                ser = self._ser
            if ser is None:
                break
            try:
                chunk = ser.read(4096) or b""
                if not chunk:
                    continue
                buf += chunk
                *lines, buf = buf.split(b"\n")
            except Exception as exc:  # noqa: BLE001 - unplugged mid-read
                with self._lock:
                    self.last_error = f"Read failed: {exc}"
                break

            for raw in lines:
                text = raw.decode("utf-8", "replace").strip()
                if not text:
                    continue
                self._ingest(text)

    def _ingest(self, text: str) -> None:
        now = time.time()
        with self._lock:
            frame = self._acc.feed(text)
            if frame is None:
                # Banners, #DIAG, #ZERO and anything unrecognised: console only.
                self._console.append(text)
                return
            self._frames.append((frame, now))
            if self._csv_writer is not None:
                try:
                    self._csv_writer.writerow(
                        [f"{now:.6f}", frame.seq, frame.t_us, *frame.values])
                    self._csv_rows += 1
                except (OSError, ValueError):
                    pass

    # ── commands ──────────────────────────────────────────────────────────

    def send_command(self, cmd: str) -> tuple[bool, str]:
        cmd = (cmd or "").strip().upper()
        if cmd not in COMMANDS:
            return False, f"Unknown command: {cmd!r}"
        with self._lock:
            ser = self._ser
            if ser is None:
                return False, "Not connected."
            try:
                ser.write((cmd + "\n").encode("ascii"))
            except Exception as exc:  # noqa: BLE001
                return False, f"Write failed: {exc}"
            if cmd == "Z":
                # The board restarts its counters, so ours must follow or every
                # subsequent frame looks like a huge backwards jump.
                self._acc.reset_counters()
                self._frames.clear()
        return True, f"Sent {cmd}."

    # ── polling API ───────────────────────────────────────────────────────

    def snapshot(self, since_seq: int = -1, limit: int = 2000) -> dict:
        """Frames newer than ``since_seq``, plus stream health and console."""
        with self._lock:
            frames = [f for f, _ts in self._frames if f.seq > since_seq]
            if len(frames) > limit:
                frames = frames[-limit:]
            banner = self._acc.banner
            payload = {
                "frames": [[f.seq, f.t_us, *f.values] for f in frames],
                "cols": list(banner.cols) if banner else [],
                "channels": list(banner.channels) if banner else [],
                "rate_hz": round(self._acc.rate_hz, 3),
                "dropped": self._acc.dropped,
                "total": self._acc.total,
                "console": list(self._console),
                "connected": self._ser is not None,
            }
            self._console.clear()   # console lines are delivered once
        return payload

    def stats(self) -> dict:
        with self._lock:
            banner = self._acc.banner
            uptime = time.time() - self._connected_at if self._ser is not None else 0.0
            return {
                "pyserial": has_pyserial(),
                "connected": self._ser is not None,
                "port": self.port,
                "rate_hz": round(self._acc.rate_hz, 3),
                "dropped": self._acc.dropped,
                "total": self._acc.total,
                "uptime_s": round(uptime, 1),
                "last_error": self.last_error,
                "recording": self._csv_path is not None,
                "record_path": os.path.basename(self._csv_path) if self._csv_path else None,
                "record_rows": self._csv_rows,
                "proto_supported": PROTO_SUPPORTED,
                # Shipped to the frontend so the force curve is written down in
                # exactly one place (core/glove/force.py) and dev.js merely
                # interpolates the points it is given.
                "force_model": force_model(),
                "banner": {
                    "fw": banner.fw,
                    "proto": banner.proto,
                    "board": banner.board,
                    "rate": banner.rate,
                    "adc_bits": banner.adc_bits,
                    "adc_ref_mv": banner.adc_ref_mv,
                    "vdiv_mv": banner.vdiv_mv,
                    "r_fixed": banner.r_fixed,
                    "imu": banner.imu,
                    "emg": banner.emg,
                    "cols": list(banner.cols),
                    "channels": list(banner.channels),
                    "supported": banner.supported,
                } if banner else None,
            }

    def derived(self, adc: int) -> dict:
        """The full chain for one ADC reading, using the banner's constants.

        counts → millivolts → sensor resistance → conductance → approximate
        force. ``range`` says whether that force is inside the part's rated
        band, so callers can badge it instead of implying false precision.
        """
        with self._lock:
            b = self._acc.banner
        ref = b.adc_ref_mv if b else 3300
        vdiv = b.vdiv_mv if b else 3300
        rfix = b.r_fixed if b else 10000
        bits = b.adc_bits if b else 10

        ohm = sensor_ohms(adc, ref, vdiv, rfix, bits)
        newtons = force_newtons(ohm)
        return {
            "mv": adc_to_mv(adc, ref, bits),
            "ohm": ohm,
            "us": conductance_us(ohm),
            "newtons": newtons,
            "gramsf": grams_force(newtons),
            "range": force_range(newtons),
        }

    # ── CSV recording ─────────────────────────────────────────────────────

    def start_recording(self) -> tuple[bool, str]:
        if not self.is_connected():
            return False, "Connect to the board first."
        with self._lock:
            if self._csv_path is not None:
                return False, "Already recording."
            banner = self._acc.banner
            channels = list(banner.channels) if banner else []
            outdir = os.path.join(self._results_dir, "glove")
            try:
                os.makedirs(outdir, exist_ok=True)
                name = "glove_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
                path = os.path.join(outdir, name)
                fh = open(path, "w", newline="", encoding="utf-8")
            except OSError as exc:
                return False, f"Could not start recording: {exc}"
            writer = csv.writer(fh)
            # host_time is a COARSE arrival stamp: pyserial hands us a whole
            # buffered chunk at once, so a burst of frames shares nearly the
            # same value. Use it only to align against the camera clock
            # (ROADMAP §3.1); per-sample timing comes from the device's t_us.
            writer.writerow(["host_time", "seq", "t_us", *channels])
            self._csv_file = fh
            self._csv_writer = writer
            self._csv_path = path
            self._csv_rows = 0
        return True, f"Recording to results/glove/{os.path.basename(path)}"

    def stop_recording(self) -> tuple[bool, str]:
        with self._lock:
            if self._csv_path is None:
                return False, "Not recording."
            path, rows = self._csv_path, self._csv_rows
            try:
                self._csv_file.close()
            except OSError:
                pass
            self._csv_file = None
            self._csv_writer = None
            self._csv_path = None
        return True, f"Saved {rows} rows to {os.path.basename(path)}"
