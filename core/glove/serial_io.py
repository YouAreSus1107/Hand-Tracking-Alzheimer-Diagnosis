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

from .flex import bend_percent, bend_range, default_span, flex_model
from .force import (conductance_us, force_model, force_newtons, force_range,
                    grams_force)
from .imu import (MIN_WINDOW_S, TREMOR_BAND, band_power, held_fraction,
                  magnitude, rms, tilt, to_units)
from .protocol import (KIND_ACCEL, KIND_FLEX, KIND_FSR, KIND_GYRO,
                       PROTO_SUPPORTED, ChannelMeta, FrameAccumulator,
                       GloveFrame, adc_to_mv, kind_from_name, sensor_ohms)

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
                # Same contract for bend: the span lives on the server so the
                # page never carries its own copy of a calibration.
                "flex_model": flex_model(default_span()),
                # And for motion: the tremor band is defined in core/glove/imu.py
                # (matching core/spiral/metrics.py), never in the frontend.
                "imu_model": {"tremor_band": list(TREMOR_BAND),
                              "min_window_s": MIN_WINDOW_S},
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
                    "imu_scale": banner.imu_scale,
                    "imu_present": banner.imu_present,
                    "emg": banner.emg,
                    "cols": list(banner.cols),
                    "channels": list(banner.channels),
                    # Always one entry per channel, in column order — the page
                    # indexes it alongside the frame values, so a short list
                    # would silently shift every readout.
                    "chan": [{"name": m.name, "kind": m.kind,
                              "r_fixed": m.r_fixed}
                             for m in banner.channel_meta],
                    "supported": banner.supported,
                } if banner else None,
            }

    def derived(self, adc: int, channel: int | str | None = None) -> dict:
        """The full chain for one ADC reading, using the banner's constants.

        counts → millivolts → sensor resistance, then a branch by sensor kind:

        * **force** channels continue → conductance → approximate newtons, with
          ``range`` saying whether that force is inside the part's rated band.
        * **flex** channels continue → bend percent against the recorded span,
          with ``range`` saying whether the reading is clamped at either end.

        The branch is the point. The FSR402 force curve is meaningless for a
        bend sensor, and applying it anyway would print a confident newton
        figure for a bending finger. Channels whose kind is unknown stop at
        resistance rather than guessing.

        ``channel`` is the column index (or name); omit it only when the kind
        genuinely does not matter, since the default assumes a force channel
        for backwards compatibility with single-FSR callers.
        """
        with self._lock:
            b = self._acc.banner
        ref = b.adc_ref_mv if b else 3300
        vdiv = b.vdiv_mv if b else 3300
        bits = b.adc_bits if b else 10
        meta = self._meta_for(b, channel)

        # Motion channels never touch the divider maths: there is no resistor
        # in the path, and sensor_ohms() would happily return a plausible
        # resistance for an acceleration.
        if meta.is_imu:
            scale = b.imu_scale if b else 1000
            value = to_units(adc, scale)
            return {"channel": meta.name, "kind": meta.kind, "r_fixed": None,
                    "mv": None, "ohm": None, "us": None, "newtons": None,
                    "gramsf": None, "bend_pct": None,
                    "value": value,
                    "unit": "g" if meta.kind == KIND_ACCEL else "deg/s",
                    "range": "imu"}

        ohm = sensor_ohms(adc, ref, vdiv, meta.r_fixed, bits)
        out = {
            "channel": meta.name,
            "kind": meta.kind,
            "r_fixed": meta.r_fixed,
            "mv": adc_to_mv(adc, ref, bits),
            "ohm": ohm,
            "us": conductance_us(ohm),
            "newtons": None,
            "gramsf": None,
            "bend_pct": None,
            "range": "open",
        }
        if meta.kind == KIND_FLEX:
            span = self._flex_span(meta.name)
            out["bend_pct"] = bend_percent(ohm, span)
            out["range"] = bend_range(ohm, span)
        elif meta.kind == KIND_FSR:
            newtons = force_newtons(ohm)
            out["newtons"] = newtons
            out["gramsf"] = grams_force(newtons)
            out["range"] = force_range(newtons)
        return out

    def imu_summary(self, window_s: float = 3.0) -> dict:
        """Derived motion readout for the Developer page's Motion card.

        Everything the IMU is fitted for, in one poll: orientation from
        gravity, how hard the hand is moving, and the tremor content of the
        acceleration magnitude.

        **Magnitude, not a single axis.** ||a|| is independent of how the board
        happens to be mounted on the glove, so the tremor figure does not
        change meaning when the glove is re-donned — which is exactly the
        failure mode listed for the flex strips in GLOVE_FIRMWARE_PLAN.md §8.

        Every field that cannot be computed comes back as ``None`` with a
        ``note`` saying why, rather than as a zero that reads like a
        measurement of stillness.
        """
        with self._lock:
            banner = self._acc.banner
            frames = [f for f, _ts in self._frames]
            measured_hz = self._acc.rate_hz

        if banner is None:
            return {"present": False, "note": "No banner yet — connect the board."}
        if not banner.imu_present:
            return {"present": False, "imu": banner.imu,
                    "note": "This firmware reports no IMU. Install "
                            "Arduino_LSM9DS1 or Arduino_BMI270_BMM150 to match "
                            "the board revision, then re-flash."}
        idx = banner.imu_index()
        if not idx:
            # Declared but not in the columns: refuse rather than guess an
            # offset, which would read a flex strip as an accelerometer.
            return {"present": False, "imu": banner.imu,
                    "note": "Banner declares an IMU but the six motion columns "
                            "are missing from cols=."}

        # The device's own measured rate is authoritative over the banner's
        # nominal one: spectral results scale directly with it.
        fs = measured_hz if measured_hz > 1 else float(banner.rate or 100)
        want = max(4, int(round(window_s * fs)))
        recent = frames[-want:]
        scale = banner.imu_scale

        def col(name: str, frame) -> float | None:
            i = idx[name]
            return to_units(frame.values[i], scale) if i < len(frame.values) else None

        accel = [(col("ax", f), col("ay", f), col("az", f)) for f in recent]
        gyro = [(col("gx", f), col("gy", f), col("gz", f)) for f in recent]
        accel = [t for t in accel if None not in t]
        gyro = [t for t in gyro if None not in t]
        if not accel:
            return {"present": True, "imu": banner.imu,
                    "note": "No motion samples in the buffer yet."}

        # Tilt from a short average, not a single sample: one frame of ADC-
        # scale noise swings the angle by a degree or two and makes a resting
        # readout look jittery when the board is not moving at all.
        tail = accel[-min(len(accel), max(2, int(fs // 10))):]
        avg = tuple(sum(t[i] for t in tail) / len(tail) for i in range(3))
        orientation = tilt(*avg)

        a_mag = [magnitude(*t) for t in accel]
        g_mag = [magnitude(*t) for t in gyro] if gyro else []
        tremor = band_power(a_mag, fs)

        return {
            "present": True,
            "imu": banner.imu,
            "scale": scale,
            "fs": round(fs, 2),
            "n": len(accel),
            "window_s": round(len(accel) / fs, 2) if fs else None,
            "accel": {"x": accel[-1][0], "y": accel[-1][1], "z": accel[-1][2],
                      "magnitude": a_mag[-1]},
            "gyro": ({"x": gyro[-1][0], "y": gyro[-1][1], "z": gyro[-1][2],
                      "magnitude": g_mag[-1]} if gyro else None),
            "tilt": orientation,
            # Motion RMS on ||a|| about its own mean: gravity cancels out, so
            # this is movement only, in g.
            "motion_rms_g": rms(a_mag),
            "gyro_rms_dps": rms(g_mag) if g_mag else None,
            # Measured, not trusted from a counter — see imu.held_fraction.
            "held_frac": held_fraction(accel),
            "tremor": tremor,
            "tremor_note": None if tremor else (
                f"Needs at least {MIN_WINDOW_S:.0f} s of samples at a rate that "
                f"resolves {TREMOR_BAND[0]}–{TREMOR_BAND[1]} Hz."),
        }

    def imu_series(self, t0: float, t1: float) -> dict:
        """IMU samples whose host arrival time falls in [t0, t1], in g and °/s.

        For a test that records the glove beside the camera (the tremor test,
        docs/tests/TREMOR_TEST_PLAN.md §5): the host clock is the only one
        both streams share, so it selects the window. The **device** clock
        spaces the samples, though — host arrival times come in USB bursts —
        so ``t`` is the device timestamp in seconds and ``fs`` the measured
        device rate, which is what the spectral maths needs.

        Returns ``{"fs", "t", "accel", "gyro"}`` with accel/gyro as lists of
        (x, y, z), or ``{"fs": 0.0, ...}`` with empty lists when there is no
        banner, no IMU or no samples in the window.
        """
        with self._lock:
            banner = self._acc.banner
            frames = [f for f, ts in self._frames if t0 <= ts <= t1]
            measured_hz = self._acc.rate_hz
        empty = {"fs": 0.0, "t": [], "accel": [], "gyro": []}
        if banner is None or not banner.imu_present:
            return empty
        idx = banner.imu_index()
        if not idx or not frames:
            return empty
        scale = banner.imu_scale
        fs = measured_hz if measured_hz > 1 else float(banner.rate or 100)

        ts, accel, gyro = [], [], []
        for f in frames:
            if max(idx.values()) >= len(f.values):
                continue
            a = tuple(to_units(f.values[idx[k]], scale) for k in ("ax", "ay", "az"))
            g = tuple(to_units(f.values[idx[k]], scale) for k in ("gx", "gy", "gz"))
            if None in a or None in g:
                continue
            ts.append(f.t_us / 1_000_000.0)
            accel.append(a)
            gyro.append(g)
        return {"fs": fs, "t": ts, "accel": accel, "gyro": gyro}

    def imu_name(self) -> str | None:
        """The IMU the banner names, or None when there is none."""
        with self._lock:
            banner = self._acc.banner
        return banner.imu if banner is not None and banner.imu_present else None

    def _meta_for(self, banner, channel: int | str | None) -> ChannelMeta:
        """Channel details for an index or name, with a safe fallback.

        Never returns None: an unrecognised channel degrades to the banner's
        global resistor and a kind guessed from the name, which is the same
        path firmware predating the ``chan=`` field takes.
        """
        default_r = banner.r_fixed if banner else 10000
        if banner is not None:
            metas = banner.channel_meta
            if isinstance(channel, int) and 0 <= channel < len(metas):
                return metas[channel]
            if isinstance(channel, str):
                for m in metas:
                    if m.name == channel:
                        return m
        name = channel if isinstance(channel, str) else ""
        # No channel named at all: assume force, matching the original
        # single-FSR behaviour of this method.
        kind = kind_from_name(name) if name else KIND_FSR
        return ChannelMeta(name=name, kind=kind, r_fixed=default_r)

    def _flex_span(self, name: str):
        """Recorded bend span for a flex channel.

        Currently always the provisional default — per-user calibration is
        gate 9 (``calibrate.py``). Isolated here so that landing calibration
        means changing this one method, and so every flex reading today is
        correctly reported as uncalibrated.
        """
        return default_span()

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
