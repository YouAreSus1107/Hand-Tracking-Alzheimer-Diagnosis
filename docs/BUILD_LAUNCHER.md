# Control Hub — running & packaging

`launcher.py` is a self-contained local web app (Python standard library only)
that connects every tool in this project and shows the research behind the
clinical tests. It launches each script in its own console window, so the
camera prompt in the tools still works.

## First-time setup

```bash
python install.py
```

`install.py` (stdlib-only) creates `.venv/`, installs `requirements.txt` into
it, and downloads any missing MediaPipe model bundles — notably
`model/face_landmarker.task`, which is **not** committed. On Windows you can
double-click **`setup.bat`** for the same thing. Users who manage their own
environment can `pip install -r requirements.txt` directly instead.

## Run it (no build needed)

```bash
.venv/Scripts/python launcher.py    # Windows venv path
```

Or on Windows, double-click **`run_hub.bat`** (it prefers the venv interpreter
automatically). Your browser opens to `http://127.0.0.1:8770/`. Press `Ctrl+C`
in the console to stop the hub (any test you launched keeps running in its own
window). Only one tool may hold the camera at a time.

## Build a standalone .exe

The hub's Python server has no dependencies beyond the standard library, but the
tools it launches (`finger_tapping.py`, etc.) still need OpenCV + MediaPipe
installed in whatever Python runs them. The dashboard itself is plain static files
in `launcher_web/` (index.html, styles.css, app.js, background.js, hand3d.js).
Two packaging options:

### Option A — package only the hub (recommended, small exe)

The exe is just the dashboard/launcher; it shells out to the system `python`
to run the tests. Requires Python + `requirements.txt` installed on the machine.

```bash
pip install pyinstaller
pyinstaller --onefile --name HandDetectionHub ^
  --add-data "launcher_web;launcher_web" ^
  launcher.py
```

Output: `dist/HandDetectionHub.exe`. Keep it in the project root (next to the
`screening_tests/`, `core/`, and `model/` folders) so it can find and launch
the tools. The `--add-data "launcher_web;launcher_web"` bundles the dashboard's
static files into the exe (the launcher reads them from `sys._MEIPASS` when
frozen), so `launcher_web/` does **not** need to sit next to the exe.

> Note: a frozen exe sets `sys.executable` to the exe itself, so on a frozen
> build the launcher uses the `python` found on `PATH` to run the test scripts.
> If you package this way, make sure Python is on `PATH`. (For a self-launching
> single distributable, use Option B.)

### Option B — bundle everything (large exe, no Python needed)

Bundle the models, test scripts, and shared `core/` packages into one exe.
Users need nothing installed. The tools import from the `core.*` package path,
so the whole `core/` tree must be bundled — not just individual modules.

```bash
pip install pyinstaller opencv-python mediapipe
pyinstaller --onefile --name HandDetectionHub ^
  --add-data "launcher_web;launcher_web" ^
  --add-data "model/hand_landmarker.task;model" ^
  --add-data "model/face_landmarker.task;model" ^
  --add-data "screening_tests/finger_tapping.py;screening_tests" ^
  --add-data "screening_tests/spiral_test.py;screening_tests" ^
  --add-data "screening_tests/oculomotor_test.py;screening_tests" ^
  --add-data "core;core" ^
  --add-data "docs/alzheimers_hand_tracking_analysis.md;docs" ^
  launcher.py
```

This produces a much larger exe (MediaPipe + OpenCV are ~200 MB+). The tools
run inside the bundled interpreter.

## Files

| File | Role |
|---|---|
| `launcher.py` | The control hub (web server, port 8770) |
| `launcher_web/` | Dashboard frontend (index.html, styles.css, app.js, background.js, hand3d.js) |
| `install.py` / `setup.bat` | One-time setup: `.venv` + deps + model download |
| `run_hub.bat` | Double-click launcher for Windows (prefers the venv) |
| `screening_tests/finger_tapping.py` | Finger-tapping test |
| `screening_tests/spiral_test.py` | Spiral tracing test |
| `screening_tests/oculomotor_test.py` | Pro/anti-saccade eye-movement test |
| `core/hand_tracking.py` | 21-landmark tracker + UDP broadcast |
| `core/` packages | Shared engines/helpers: `hand_utils`, `camera`, `session`, `tapping/`, `gaze/`, `ui/` |
| `model/hand_landmarker.task` | MediaPipe hand model bundle (required) |
| `model/face_landmarker.task` | MediaPipe face/iris model bundle (oculomotor test; not committed — fetched by `install.py`) |
