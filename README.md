# Hand-Detection-3D

Webcam motor and eye-movement tests, built to measure the kinds of fine-motor
changes that show up in the early-cognitive-decline literature. Runs on
OpenCV + MediaPipe with no hardware beyond a camera.

The tracking core started as a real-time hand-tracking pipeline driving a rigged
3D hand in Unity. It was rewritten around the MediaPipe Tasks API and pointed at
motor measurement instead.

## Status

This is a research prototype, not a screening tool. Nobody has run it on a
clinical population, and it has not been validated against any reference
instrument. Specifically:

- Scoring thresholds are taken from the papers cited below, not fitted to data
  collected with this pipeline. Treat the status bands as provisional.
- It has mostly been run on one laptop and one camera. Some scaling is tied to
  the capture resolution and will need work on other setups.
- The hand and face landmark models are Google's pretrained MediaPipe bundles.
  What is here is the measurement layer on top of them.

## Tests

| Test | Task | Primary metric |
|---|---|---|
| Finger tapping (`screening_tests/finger_tapping.py`) | Tap thumb and index together, either at maximum speed or on a metronome | CV% of inter-tap intervals, plus beat-sync consistency in paced mode |
| Spiral tracing (`screening_tests/spiral_test.py`) | Trace an Archimedes spiral in the air with the index fingertip | SPARC movement-smoothness index, with normalized jerk and velocity CV% |
| Eye movement (`screening_tests/oculomotor_test.py`) | Look toward a flashing dot, then away from it, then hold fixation | Anti-saccade error rate, Anti − Pro latency, fixation stability (RMS jitter, BCEA) |

Each test writes one JSON file per session to `results/` plus a row in
`results/index.csv`. The launcher charts those over time on its Analysis page.

Sources for the metrics and thresholds: Namkoong & Roh (2024), *Technology and
Health Care* 32(S1):253–264; Suzumura et al.; Roalf et al. (2018); Kachouri et
al. (2021); Schroter et al. (2003); Balasubramanian et al. (2015) for SPARC.
For the oculomotor test: Opwonya et al. (2022), Crawford et al. (2005), and the
Antoniades et al. (2013) protocol. The full reading notes behind those choices
are kept locally and are not published here.

## Setup

```bash
python install.py     # creates .venv, installs deps, downloads model bundles
python launcher.py    # control hub at http://127.0.0.1:8770
```

On Windows, `setup.bat` and `run_hub.bat` do the same by double-click.
`install.py` uses only the standard library and downloads
`model/face_landmarker.task`, which is too large to keep in the repo. If you
manage your own environment, `pip install -r requirements.txt` also works.

To run a test without the launcher, use the venv interpreter:

```bash
.venv/Scripts/python screening_tests/finger_tapping.py
```

Each tool asks for a camera source at startup: `1` for a local webcam, `2` for
an IP stream URL such as the Android IP Webcam app. Press `q` to quit. Audio
cues use `winsound` on Windows and `sounddevice` elsewhere.

Unit tests cover the pure engine code and need no camera or hardware:

```bash
python screening_tests/tests/test_gaze.py
python screening_tests/tests/test_spiral.py
python screening_tests/tests/test_glove.py
```

## Layout

```
launcher.py            Control hub, standard library only
launcher_web/          Hub frontend (index.html, styles.css, app.js, dev.js,
                       background.js, hand3d.js)
core/
  hand_tracking.py     21-landmark tracker + UDP broadcast on port 5052
  hand_utils.py        One-Euro filtering, CLAHE preprocessing, connectivity
  camera.py            Camera-source prompt/open helper
  session.py           Results schema: results/*.json + index.csv
  tapping/             Tapping engine (modes, detector, metrics, audio)
  spiral/              Spiral engine (geometry, metrics)
  gaze/                Gaze engine (tracker, calibrate, detector, metrics,
                       tasks, fixation)
  glove/               Sensor-glove host stack (protocol, force, serial_io)
  ui/                  PIL-overlay UI toolkit (theme, components, anim)
screening_tests/       The three tests, plus tests/ for the engine unit tests
firmware/glove/        Arduino sketch for the sensor glove
model/                 MediaPipe model bundles
results/               Session output (git-ignored)
```

## How the tracking works

- MediaPipe Tasks API (`HandLandmarker`, VIDEO mode), not the deprecated
  `solutions` API, so it runs on Python 3.12+.
- One-Euro filtering on landmark x/y for display. z is left raw, since
  monocular depth is too noisy to smooth usefully. The spiral test measures
  jitter on the raw fingertip, because the filter would erase the signal it is
  looking for.
- CLAHE on the luminance channel plus light sharpening before detection, which
  helps in poor lighting. The displayed frame is untouched.
- `core/hand_tracking.py` broadcasts each hand as
  `L:[x1,y1,z1,...,x21,y21,z21]` over UDP to `127.0.0.1:5052` for any
  downstream consumer.
- The oculomotor test uses the Face Landmarker (478 landmarks including iris).
  Its horizontal gaze proxy is iris-center x relative to the eye corners, which
  is invariant to head translation, smoothed and mapped to screen zones by a
  3-point per-user calibration.

## Sensor glove (in progress)

`firmware/glove/glove.ino` streams 12-bit samples from an Arduino Nano 33 BLE at
100 Hz; `core/glove/` parses the frames, records them, and converts resistance
to approximate force using the published Interlink FSR402 curve. Per-user
calibration is not done yet, so forces are approximate and readings outside the
sensor's rated 0.2–20 N band are flagged rather than reported. Build order and
verification gates are tracked in a local plan document.

## Origins

The tracking pipeline began from
[imadeddinedjekoune/Hand-Detection-3D](https://github.com/imadeddinedjekoune/Hand-Detection-3D),
which mirrored a hand onto a rigged model in Unity. This project modernized the
tracker and redirected it toward motor measurement. The Unity side is retired
and kept only in a local archive.
