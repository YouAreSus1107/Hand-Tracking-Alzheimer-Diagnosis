# Hand-Detection-3D — Camera-Based Motor Screening Suite

Webcam-based hand-motion tests for detecting fine-motor changes associated
with early cognitive decline (Alzheimer's disease in particular). Built on
OpenCV + MediaPipe hand tracking — no wearables, no special hardware, just a
camera.

The suite grew out of a real-time hand-tracking pipeline (originally driving a
rigged 3D hand in Unity) and repurposes that tracking core to measure motor
biomarkers identified in the clinical literature: tapping-rhythm variability,
beat synchronization, and drawing smoothness.

## The Tests

| Test | What the patient does | What it measures |
|---|---|---|
| **IIV Finger Tapping** (`screening_tests/iiv_test.py`) | Taps thumb and index finger once per metronome beep | **IIV** — intra-individual variability of inter-tap intervals (rhythm consistency), and **sync consistency** — variability of tap latency after each beat. Both degrade early in AD. |
| **Spiral Tracing** (`screening_tests/spiral_test.py`) | Traces an on-screen Archimedes spiral in the air with the index fingertip | Path deviation, velocity variability (CV%), normalized jerk (smoothness), completion %, active-movement ratio. |

Research grounding: Namkoong & Roh (2024) systematic review, *Technology and
Health Care* 32(S1):253–264, plus Suzumura et al., Roalf et al. (2018),
Kachouri et al. (2021), Schroter et al. (2003). See
[`docs/alzheimers_hand_tracking_analysis.md`](docs/alzheimers_hand_tracking_analysis.md)
for the full analysis.

## Quick Start

```bash
pip install -r requirements.txt
python launcher.py          # or double-click run_hub.bat on Windows
```

The launcher opens a control hub at `http://127.0.0.1:8770` with system
status, one-click launch for each test, and the research summary. Each tool
can also be run directly, e.g. `python screening_tests/iiv_test.py`.

On startup each tool asks for a camera source: `1` local webcam (default) or
`2` an IP stream URL (e.g. the Android "IP Webcam" app). Press `q` to quit a
test window.

> **Note:** the test scripts use `winsound` for audio cues, so they are
> Windows-only as written.

## Repository Layout

```
launcher.py            Control hub (stdlib-only web server + dashboard)
run_hub.bat            Windows double-click entry point
core/
  hand_tracking.py     21-landmark tracker + UDP broadcast (port 5052)
  hand_utils.py        Shared: One-Euro filtering, CLAHE preprocessing,
                       landmark connectivity
screening_tests/
  iiv_test.py          IIV finger-tapping test
  spiral_test.py       Spiral tracing test
model/
  hand_landmarker.task MediaPipe hand-landmarker model bundle (~7.5 MB)
docs/
  alzheimers_hand_tracking_analysis.md   Research deep-dive
  BUILD_LAUNCHER.md    Packaging the hub as a standalone .exe
  PROJECT_OVERVIEW.md  Architecture and progress notes
archive/               Retired Unity project (local only, not in git)
```

## How the Tracking Works

- **MediaPipe Tasks API** (`HandLandmarker`, VIDEO mode) — the modern API,
  compatible with Python 3.12+.
- **One-Euro filtering** on landmark x/y: heavy smoothing at rest to kill
  jitter, light smoothing during fast motion to preserve tap edges. z is left
  raw (monocular depth is too noisy to smooth usefully).
- **Preprocessing** before detection: CLAHE on the luminance channel plus
  gentle sharpening, for reliable detection in poor lighting.
- `core/hand_tracking.py` broadcasts each hand as
  `L:[x1,y1,z1,...,x21,y21,z21]` / `R:[...]` (pixel-scaled) over UDP to
  `127.0.0.1:5052` for any downstream consumer.

## Origins

The tracking pipeline started from
[imadeddinedjekoune/Hand-Detection-3D](https://github.com/imadeddinedjekoune/Hand-Detection-3D),
which mirrored a real hand onto a Blender-modeled, rigged hand in Unity. This
project modernized the tracker (Tasks API, filtering, preprocessing) and
redirected it toward clinical motor screening; the Unity receiver side was
retired and is kept only as a local archive.
