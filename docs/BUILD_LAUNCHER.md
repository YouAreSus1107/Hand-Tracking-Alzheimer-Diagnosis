# Control Hub — running & packaging

`launcher.py` is a self-contained local web app (Python standard library only)
that connects every tool in this project and shows the research behind the
clinical tests. It launches each script in its own console window, so the
camera prompt in `hand_tracking.py` still works.

## Run it (no build needed)

```bash
python launcher.py
```

Or on Windows, double-click **`run_hub.bat`**. Your browser opens to
`http://127.0.0.1:8770/`. Press `Ctrl+C` in the console to stop the hub
(any test you launched keeps running in its own window).

## Build a standalone .exe

The hub itself has no dependencies beyond the standard library, but the tools
it launches (`iiv_test.py`, etc.) still need OpenCV + MediaPipe installed in
whatever Python runs them. Two packaging options:

### Option A — package only the hub (recommended, small exe)

The exe is just the dashboard/launcher; it shells out to the system `python`
to run the tests. Requires Python + `requirements.txt` installed on the machine.

```bash
pip install pyinstaller
pyinstaller --onefile --name HandDetectionHub launcher.py
```

Output: `dist/HandDetectionHub.exe`. Keep it in the project root (next to the
`screening_tests/`, `core/`, and `model/` folders) so it can find and launch
the tools.

> Note: a frozen exe sets `sys.executable` to the exe itself, so on a frozen
> build the launcher uses the `python` found on `PATH` to run the test scripts.
> If you package this way, make sure Python is on `PATH`. (For a self-launching
> single distributable, use Option B.)

### Option B — bundle everything (large exe, no Python needed)

Bundle the model and data files into one exe. Users need nothing installed.

```bash
pip install pyinstaller opencv-python mediapipe
pyinstaller --onefile --name HandDetectionHub ^
  --add-data "model/hand_landmarker.task;model" ^
  --add-data "screening_tests/iiv_test.py;screening_tests" ^
  --add-data "screening_tests/spiral_test.py;screening_tests" ^
  --add-data "core/hand_tracking.py;core" ^
  --add-data "core/hand_utils.py;core" ^
  --add-data "docs/alzheimers_hand_tracking_analysis.md;docs" ^
  launcher.py
```

This produces a much larger exe (MediaPipe + OpenCV are ~200 MB+). The tools
run inside the bundled interpreter.

## Files

| File | Role |
|---|---|
| `launcher.py` | The control hub (web server + dashboard) |
| `run_hub.bat` | Double-click launcher for Windows |
| `screening_tests/iiv_test.py` | IIV finger-tapping test |
| `screening_tests/spiral_test.py` | Spiral tracing test |
| `core/hand_tracking.py` | 21-landmark tracker + UDP broadcast |
| `core/hand_utils.py` | Shared filtering/preprocessing helpers |
| `model/hand_landmarker.task` | MediaPipe model bundle (required) |
