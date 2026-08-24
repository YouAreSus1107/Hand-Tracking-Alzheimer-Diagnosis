"""
Cognitive Screening Suite — Launcher Hub
========================================
A self-contained local web app that connects every tool in this camera-based
cognitive-screening suite and presents the research behind it. Run it, and it
opens a dashboard in your browser with:

  - System status  (Python, model files, OpenCV, MediaPipe)
  - One-click launch for each tool, spanning motor and oculomotor modalities
    (a speech modality is planned — see docs/ROADMAP.md):
        * Finger Tapping Test       (finger_tapping.py)
        * Spiral Tracing Test       (spiral_test.py)
        * Eye Movement Test         (oculomotor_test.py)
        * Hand Tracking / UDP       (hand_tracking.py)
  - The cognitive-biomarker research summary spanning each modality
  - A link to the full analysis document
  - A Developer page: sensor-glove toolchain, firmware compile/upload, and a
    live scope for the analog channels streaming off the Arduino

The Python server uses the standard library only — no extra pip installs — so
it still packages into a single .exe with PyInstaller (see BUILD_LAUNCHER.md).
The one exception is the Developer page, whose serial reader needs ``pyserial``;
that import is lazy and optional, so the hub runs identically without it and
the page simply reports the dependency as missing.
The frontend lives as plain static files in ``launcher_web/`` (index.html,
styles.css, app.js, dev.js, background.js, hand3d.js), served straight off disk.

Run:   python launcher.py
Quit:  press Ctrl+C in this console, or close the window.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── Paths ──────────────────────────────────────────────────────────────────
# BASE_DIR    — real folder on disk: where the tool scripts live and where the
#               PID file is written (must be a real path even in a frozen exe).
# RESOURCE_DIR — where bundled read-only assets are read from. In a PyInstaller
#               one-file build these are unpacked to sys._MEIPASS; otherwise
#               they sit next to this file.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR

# The Developer page imports core.glove.* from real disk, so BASE_DIR must be
# importable even when the rest of the app is running out of a frozen bundle.
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

WEB_DIR = os.path.join(RESOURCE_DIR, "launcher_web")
ASSETS_DIR = os.path.join(RESOURCE_DIR, "assets")
# Session results live on real disk (git-ignored), written by core/session.py.
RESULTS_DIR = os.path.join(BASE_DIR, "results")
MODEL_FILE = os.path.join(RESOURCE_DIR, "model", "hand_landmarker.task")
FACE_MODEL_FILE = os.path.join(RESOURCE_DIR, "model", "face_landmarker.task")
ANALYSIS_FILE = os.path.join(RESOURCE_DIR, "docs", "alzheimers_hand_tracking_analysis.md")

HOST = "127.0.0.1"
PORT = 8770

# ── MIME types ─────────────────────────────────────────────────────────────
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".bin": "application/octet-stream",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def _mime(path: str) -> str:
    return _MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


# ── Tool registry ──────────────────────────────────────────────────────────
# key -> (script filename, human title)
TOOLS: dict[str, tuple[str, str]] = {
    "iiv":       (os.path.join("screening_tests", "finger_tapping.py"), "Finger Tapping Test"),
    "spiral":    (os.path.join("screening_tests", "spiral_test.py"), "Spiral Tracing Test"),
    "oculomotor": (os.path.join("screening_tests", "oculomotor_test.py"), "Eye Movement Test"),
    "tracking":  (os.path.join("core", "hand_tracking.py"),          "Hand Tracking / UDP Broadcast"),
}

# key -> live subprocess.Popen (only while running)
_procs: dict[str, subprocess.Popen] = {}


# ── Camera source ──────────────────────────────────────────────────────────
# Which camera the tools should use. Chosen in the dashboard (the small chip
# beside "Screening Tools" and on each test page) rather than at the console
# prompt each tool used to open with, and handed to the spawned process through
# core.camera.ENV_CAMERA. Persisted so the choice survives a hub restart.
SETTINGS_FILE = os.path.join(BASE_DIR, ".launcher_settings.json")
ENV_CAMERA = "HAND3D_CAMERA"
_MAX_CAM_INDEX = 9
_STREAM_SCHEMES = ("http://", "https://", "rtsp://", "rtmp://")

_DEFAULT_CAMERA = {"mode": "webcam", "index": 0, "url": ""}
_settings_lock = threading.Lock()


def _read_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _normalise_camera(raw) -> dict:
    """Coerce anything on disk (or off the wire) into a valid camera setting."""
    cam = dict(_DEFAULT_CAMERA)
    if not isinstance(raw, dict):
        return cam
    # The URL is kept even while the webcam is selected, so switching back and
    # forth does not make the user retype it.
    url = str(raw.get("url", "")).strip()
    if url.lower().startswith(_STREAM_SCHEMES):
        cam["url"] = url
        if raw.get("mode") == "stream":
            cam["mode"] = "stream"
    try:
        cam["index"] = max(0, min(_MAX_CAM_INDEX, int(raw.get("index", 0))))
    except (TypeError, ValueError):
        pass
    return cam


def camera_setting() -> dict:
    cam = _normalise_camera(_read_settings().get("camera"))
    cam["label"] = (cam["url"] if cam["mode"] == "stream"
                    else f"Webcam {cam['index']}")
    return cam


def set_camera_setting(raw) -> tuple[bool, str]:
    if isinstance(raw, dict) and raw.get("mode") == "stream":
        url = str(raw.get("url", "")).strip()
        if not url:
            return False, "Enter a stream URL."
        if not url.lower().startswith(_STREAM_SCHEMES):
            return False, "Stream URL must start with http:// or rtsp://."
    cam = _normalise_camera(raw)
    with _settings_lock:
        data = _read_settings()
        data["camera"] = cam
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            return False, f"Could not save the camera choice: {exc}"
    label = cam["url"] if cam["mode"] == "stream" else f"webcam {cam['index']}"
    return True, f"Camera set to {label}."


def _camera_env() -> dict:
    """Process environment for a spawned tool, carrying the camera choice."""
    cam = camera_setting()
    env = os.environ.copy()
    env[ENV_CAMERA] = cam["url"] if cam["mode"] == "stream" else str(cam["index"])
    return env
_procs_lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────

def _dep_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False
    except Exception:  # noqa: BLE001 - a broken package must not break a probe
        return False


def _running(key: str) -> bool:
    """True if the tool's process exists and has not exited."""
    with _procs_lock:
        proc = _procs.get(key)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        # Exited — clean it up.
        _procs.pop(key, None)
        return False


def launch_tool(key: str) -> tuple[bool, str]:
    """Spawn the tool's script in its own console. Returns (ok, message)."""
    if key not in TOOLS:
        return False, f"Unknown tool: {key}"

    if _running(key):
        return False, "Already running."

    # Only one tool can hold the webcam at a time.
    for other in TOOLS:
        if other != key and _running(other):
            return False, f"'{TOOLS[other][1]}' is using the camera. Stop it first."

    script, _title = TOOLS[key]
    script_path = os.path.join(BASE_DIR, script)
    if not os.path.exists(script_path):
        return False, f"Script not found: {script}"

    # Give each tool its own console so print()/input() (e.g. the camera
    # prompt in hand_tracking.py) have somewhere to go.
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]

    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=BASE_DIR,
            env=_camera_env(),      # the tool reads its source from here
            creationflags=creationflags,
        )
    except OSError as exc:
        return False, f"Failed to launch: {exc}"

    with _procs_lock:
        _procs[key] = proc
    return True, "Launched."


def stop_tool(key: str) -> tuple[bool, str]:
    with _procs_lock:
        proc = _procs.get(key)
    if proc is None or proc.poll() is not None:
        return False, "Not running."
    try:
        proc.terminate()
    except OSError as exc:
        return False, f"Failed to stop: {exc}"
    return True, "Stopping."


# ── Developer page: sensor glove + firmware toolchain ─────────────────────
# Everything below serves the Developer page. It is kept out of the core hub
# path on purpose: the glove reader is constructed lazily so that importing or
# running launcher.py never requires pyserial.

FIRMWARE_DIR = os.path.join(BASE_DIR, "firmware", "glove")
FQBN = "arduino:mbed_nano:nano33ble"

_glove = None
_glove_lock = threading.Lock()


def _get_glove():
    """The process-wide GloveReader, built on first use."""
    global _glove
    with _glove_lock:
        if _glove is None:
            from core.glove.serial_io import GloveReader
            _glove = GloveReader(RESULTS_DIR)
        return _glove


def _venv_python() -> str:
    """The repo's .venv interpreter if it exists, else whatever is running us."""
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    cand = os.path.join(BASE_DIR, ".venv", sub, exe)
    return cand if os.path.exists(cand) else sys.executable


def _arduino_cli() -> str | None:
    """Locate arduino-cli: our known install dir first, then PATH."""
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Programs", "arduino-cli", "arduino-cli.exe")
    if os.path.exists(local):
        return local
    return shutil.which("arduino-cli")


def _arduino_data_dir() -> str:
    if os.name == "nt":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arduino15")
    return os.path.join(os.path.expanduser("~"), ".arduino15")


#: The two IMU libraries, keyed by the name the firmware reports in its
#: banner. WHICH ONE IS CORRECT DEPENDS ON THE BOARD REVISION (plan §1.3): the
#: original Nano 33 BLE carries an LSM9DS1, the Rev2 a BMI270 + BMM150.
#: Installing the wrong one compiles cleanly and reports no motion.
#:
#: The sketch picks one explicitly with a `#define GLOVE_IMU_…` line, so what
#: matters here is not "which is installed" but "is the one the sketch selected
#: installed" — a mismatch fails the compile with a missing-header error, which
#: is the loud failure the sketch's comment explains it chose on purpose.
IMU_LIBS = (("BMI270_BMM150", "Arduino_BMI270_BMM150"),
            ("LSM9DS1", "Arduino_LSM9DS1"))

#: Maps the sketch's selection macro to the banner name above.
IMU_SELECT_MACROS = {"GLOVE_IMU_BMI270": "BMI270_BMM150",
                     "GLOVE_IMU_LSM9DS1": "LSM9DS1",
                     "GLOVE_IMU_NONE": "none"}

_arduino_user_dir_cache: str | None = None


def _arduino_user_dir() -> str:
    """arduino-cli's sketchbook directory, where `lib install` puts libraries.

    Asked of the CLI once and cached: this is polled every few seconds by the
    Developer page and spawning a process each time would be absurd.
    """
    global _arduino_user_dir_cache
    if _arduino_user_dir_cache is not None:
        return _arduino_user_dir_cache
    default = os.path.join(os.path.expanduser("~"), "Documents", "Arduino")
    cli = _arduino_cli()
    out = ""
    if cli:
        try:
            # encoding= is not optional: text=True decodes with the locale
            # codec, and a sketchbook path containing non-ASCII characters
            # (this repo's own OneDrive path does) raises UnicodeDecodeError
            # inside subprocess's reader thread, leaving stdout as None.
            out = (subprocess.run([cli, "config", "get", "directories.user"],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=15).stdout or "").strip()
        except Exception:  # noqa: BLE001 - a probe must never break the page
            out = ""
    _arduino_user_dir_cache = out if out and os.path.isdir(out) else default
    return _arduino_user_dir_cache


def _imu_libs_present() -> list[str]:
    """Installed IMU libraries, by banner name, in __has_include order."""
    libdir = os.path.join(_arduino_user_dir(), "libraries")
    return [name for name, folder in IMU_LIBS
            if os.path.isdir(os.path.join(libdir, folder))]


def _sketch_imu_selection() -> str | None:
    """Which IMU the sketch is currently set to build against.

    Read from the source rather than assumed, because the choice is a one-line
    edit in glove.ino (board revision decides it) and the page would otherwise
    report a library state that has nothing to do with what will be flashed.
    Returns the banner name, "none", or None if the sketch cannot be read.
    """
    path = os.path.join(FIRMWARE_DIR, "glove.ino")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                # Only an uncommented #define counts; the alternatives sit
                # commented out directly beneath it.
                m = re.match(r"\s*#define\s+(GLOVE_IMU_\w+)", line)
                if m and m.group(1) in IMU_SELECT_MACROS:
                    return IMU_SELECT_MACROS[m.group(1)]
    except OSError:
        return None
    return None


def _mbed_core_present() -> bool:
    return os.path.isdir(os.path.join(_arduino_data_dir(), "packages", "arduino",
                                      "hardware", "mbed_nano"))


def dev_env_payload() -> dict:
    """Toolchain probe backing the Developer page's status pills."""
    cli = _arduino_cli()
    try:
        from core.glove.serial_io import has_pyserial, list_ports
        pyserial = has_pyserial()
        ports = list_ports()
    except Exception:  # noqa: BLE001 - never let a probe break the page
        pyserial, ports = False, []

    # Which interpreter is running this hub. Informational only: what actually
    # matters is whether the packages import HERE, not which python it is. A
    # non-venv interpreter with everything installed is perfectly fine, so the
    # UI must key its warning on `missing_deps`, never on `on_venv`.
    venv_py = _venv_python()
    on_venv = os.path.normcase(sys.executable) == os.path.normcase(venv_py)

    importlib.invalidate_caches()   # see a package installed since startup
    deps = {name: _dep_present(mod) for name, mod in
            (("pyserial", "serial"), ("opencv", "cv2"), ("mediapipe", "mediapipe"))}
    missing_deps = sorted(n for n, ok in deps.items() if not ok)

    imu_libs = _imu_libs_present() if cli else []
    imu_selected = _sketch_imu_selection()
    return {
        "python_exe": sys.executable,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}."
                          f"{sys.version_info.micro}",
        "deps": deps,
        "missing_deps": missing_deps,
        "venv_python": venv_py,
        "venv_present": os.path.exists(os.path.join(BASE_DIR, ".venv")),
        "on_venv": on_venv,
        "pyserial": pyserial,
        "arduino_cli": cli,
        "arduino_cli_present": cli is not None,
        "mbed_core": _mbed_core_present(),
        # Which IMU library the sketch would compile against, and whether the
        # ambiguous both-installed case needs resolving.
        "imu_libs": imu_libs,
        # What glove.ino will actually compile against, and whether that
        # library is present. "none" is a valid selection, not a problem.
        "imu_selected": imu_selected,
        "imu_ready": (imu_selected == "none"
                      or (imu_selected is not None and imu_selected in imu_libs)),
        "arduino_user_dir": _arduino_user_dir() if cli else None,
        "sketch_present": os.path.isfile(os.path.join(FIRMWARE_DIR, "glove.ino")),
        "fqbn": FQBN,
        "ports": ports,
        # None means "cannot tell" — without pyserial there is no way to look,
        # which is NOT the same as "no board plugged in".
        "board_detected": any(p["is_glove"] for p in ports) if pyserial else None,
    }


def _dev_command(task: str, port: str | None) -> tuple[list[str] | None, str]:
    """Build the argv for a dev task, or explain why it can't run."""
    if task == "setup":
        return [sys.executable, os.path.join(BASE_DIR, "install.py")], "Running setup…"
    if task == "install_pyserial":
        # Install into the interpreter running THIS process, not the venv:
        # this hub is what has to import pyserial, and installing into a
        # different interpreter is a no-op it can never see.
        return ([sys.executable, "-m", "pip", "install", "pyserial"],
                f"Installing pyserial into {os.path.basename(sys.executable)}…")
    if task.startswith("install_imu_"):
        cli = _arduino_cli()
        if cli is None:
            return None, "arduino-cli not found — install the toolchain first."
        wanted = task[len("install_imu_"):].upper()
        folder = next((f for n, f in IMU_LIBS if n.upper().startswith(wanted)), None)
        if folder is None:
            return None, f"Unknown IMU library: {task}"
        return ([cli, "lib", "install", folder],
                f"Installing {folder} — re-flash the firmware afterwards.")

    if task == "tests":
        script = os.path.join(BASE_DIR, "screening_tests", "tests", "test_glove.py")
        return [_venv_python(), script], "Running glove tests…"

    if task in ("compile", "upload"):
        cli = _arduino_cli()
        if cli is None:
            return None, ("arduino-cli not found. Expected it in "
                          r"%LOCALAPPDATA%\Programs\arduino-cli\ or on PATH.")
        if not os.path.isfile(os.path.join(FIRMWARE_DIR, "glove.ino")):
            return None, "firmware/glove/glove.ino is missing."
        if task == "compile":
            return [cli, "compile", "--fqbn", FQBN, FIRMWARE_DIR], "Compiling firmware…"
        if not port:
            return None, "No port selected — pick the board's port first."
        return ([cli, "upload", "-p", port, "--fqbn", FQBN, FIRMWARE_DIR],
                f"Uploading to {port}…")

    return None, f"Unknown task: {task}"


def run_dev_task(task: str, port: str | None) -> tuple[bool, str]:
    """Spawn a dev task in its own console so its output is visible."""
    argv, message = _dev_command(task, port)
    if argv is None:
        return False, message

    note = ""
    if task == "upload":
        # Windows allows one owner per COM port: the reader must let go or
        # bossac cannot open the board.
        glove = _get_glove()
        if glove.is_connected():
            glove.disconnect()
            note = " Disconnected the live stream first — reconnect when it finishes."

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
    try:
        subprocess.Popen(argv, cwd=BASE_DIR, creationflags=creationflags)
    except OSError as exc:
        return False, f"Failed to start: {exc}"
    return True, message + note


def sessions_payload() -> dict:
    """All saved sessions for the longitudinal view, newest last.

    Reads the per-session JSON files in ``results/`` (the CSV index has stale
    columns for some tests) and strips the heavy per-frame ``raw`` arrays so
    the payload stays small. The frontend groups + charts these client-side.
    """
    sessions: list[dict] = []
    if os.path.isdir(RESULTS_DIR):
        for name in sorted(os.listdir(RESULTS_DIR)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(RESULTS_DIR, name), "r", encoding="utf-8") as fh:
                    rec = json.load(fh)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            rec.pop("raw", None)  # drop per-frame landmark arrays — charts don't need them
            sessions.append(rec)
    sessions.sort(key=lambda r: r.get("timestamp", ""))
    return {"sessions": sessions}


def status_payload() -> dict:
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "model_present": os.path.exists(MODEL_FILE),
        "face_model_present": os.path.exists(FACE_MODEL_FILE),
        "opencv": _dep_present("cv2"),
        "mediapipe": _dep_present("mediapipe"),
        "analysis_present": os.path.exists(ANALYSIS_FILE),
        "running": {key: _running(key) for key in TOOLS},
        # Rides along on the 3 s poll the dashboard already makes, so the
        # camera chip needs no endpoint of its own to stay in sync.
        "camera": camera_setting(),
    }


# ── HTTP Handler ───────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    # Silence the default per-request logging noise.
    def log_message(self, *args):  # noqa: D401
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Never cache — prevents stale UI after code changes.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _serve_dir_file(self, directory: str, name: str):
        """Serve a single file from *directory*, guarded against path traversal."""
        safe = os.path.basename(name.split("?", 1)[0])
        fpath = os.path.join(directory, safe)
        if safe and os.path.isfile(fpath):
            with open(fpath, "rb") as f:
                self._send(200, f.read(), _mime(safe))
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path

        if self.path in ("/", "/index.html"):
            self._serve_dir_file(WEB_DIR, "index.html")
        elif self.path == "/api/status":
            self._send_json(status_payload())
        elif self.path == "/api/sessions":
            self._send_json(sessions_payload())
        elif route == "/api/dev/env":
            self._send_json(dev_env_payload())
        elif route == "/api/glove/status":
            self._send_json(_get_glove().stats())
        elif route == "/api/glove/imu":
            # Derived motion readout. Separate from /samples on purpose: the
            # raw columns already ride in the sample stream at 10 Hz, and this
            # one runs a small DFT, so the page polls it far less often.
            self._send_json(_get_glove().imu_summary())
        elif route == "/api/glove/ports":
            from core.glove.serial_io import HAS_PYSERIAL, list_ports
            self._send_json({"pyserial": HAS_PYSERIAL, "ports": list_ports()})
        elif route == "/api/glove/samples":
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:
                since = int(q.get("since", ["-1"])[0])
            except ValueError:
                since = -1
            try:
                limit = max(1, min(2000, int(q.get("max", ["2000"])[0])))
            except ValueError:
                limit = 2000
            self._send_json(_get_glove().snapshot(since, limit))
        elif self.path == "/analysis":
            if os.path.exists(ANALYSIS_FILE):
                with open(ANALYSIS_FILE, "r", encoding="utf-8") as fh:
                    text = fh.read()
                self._send(200, text.encode("utf-8"), "text/plain; charset=utf-8")
            else:
                self._send(404, b"Analysis document not found.", "text/plain; charset=utf-8")
        elif self.path.startswith("/assets/"):
            self._serve_dir_file(ASSETS_DIR, self.path.split("/assets/", 1)[1])
        else:
            # Static frontend files: styles.css, app.js, background.js, hand3d.js …
            self._serve_dir_file(WEB_DIR, self.path.lstrip("/"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            data = {}
        key = data.get("test", "")
        route = urllib.parse.urlsplit(self.path).path

        # ── Developer page endpoints (no tool-running state to report) ──
        if route.startswith("/api/glove/") or route.startswith("/api/dev/"):
            ok, msg = self._dev_post(route, data)
            self._send_json({"ok": ok, "message": msg})
            return

        if self.path == "/api/launch":
            ok, msg = launch_tool(key)
        elif self.path == "/api/stop":
            ok, msg = stop_tool(key)
        elif route == "/api/camera":
            ok, msg = set_camera_setting(data.get("camera"))
            self._send_json({"ok": ok, "message": msg,
                             "camera": camera_setting()})
            return
        else:
            self._send_json({"ok": False, "message": "Unknown endpoint"}, code=404)
            return

        running = {k: _running(k) for k in TOOLS}
        self._send_json({"ok": ok, "message": msg, "running": running})

    def _dev_post(self, route: str, data: dict) -> tuple[bool, str]:
        if route == "/api/dev/run":
            return run_dev_task(str(data.get("task", "")), data.get("port") or None)

        glove = _get_glove()
        if route == "/api/glove/connect":
            return glove.connect(str(data.get("port", "")))
        if route == "/api/glove/disconnect":
            return glove.disconnect()
        if route == "/api/glove/command":
            return glove.send_command(str(data.get("cmd", "")))
        if route == "/api/glove/record":
            return glove.start_recording() if data.get("on") else glove.stop_recording()
        return False, f"Unknown endpoint: {route}"


# ── Stale-server cleanup ──────────────────────────────────────────────────

def _kill_stale_hubs(port: int) -> int:
    """Kill any existing processes listening on *port*. Returns count killed."""
    if os.name != "nt":
        return 0
    killed = 0
    my_pid = os.getpid()
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"],
            text=True, creationflags=0x08000000,   # CREATE_NO_WINDOW
        )
        pids: set[int] = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and f"127.0.0.1:{port}" in parts[1] and parts[3] == "LISTENING":
                try:
                    pid = int(parts[4])
                    if pid != my_pid and pid != 0:
                        pids.add(pid)
                except ValueError:
                    pass
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
            except OSError:
                pass
    except (subprocess.SubprocessError, OSError):
        pass
    return killed


# ── PID file for single-instance guard ────────────────────────────────────

_PID_FILE = os.path.join(BASE_DIR, ".launcher.pid")


def _write_pid():
    try:
        with open(_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def _remove_pid():
    try:
        os.remove(_PID_FILE)
    except OSError:
        pass


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    # Kill any stale hub processes hogging our port.
    n = _kill_stale_hubs(PORT)
    if n:
        print(f"[INFO] Killed {n} stale hub process(es) on port {PORT}.")
        import time; time.sleep(0.4)  # brief pause for OS to release the socket

    server = None
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        print(f"[ERROR] Port {PORT} still in use. Close the old hub and retry.")
        sys.exit(1)

    _write_pid()

    url = f"http://{HOST}:{PORT}/"
    print("=" * 56)
    print("  Cognitive Screening Suite — Control Hub")
    print("=" * 56)
    print(f"  Dashboard:  {url}")
    print("  Opening your browser… (Ctrl+C here to quit)")
    print("=" * 56)

    threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down hub.")
    finally:
        server.server_close()
        _remove_pid()


if __name__ == "__main__":
    main()
