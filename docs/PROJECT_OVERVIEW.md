# Hand-Detection-3D — Project Overview & Progress

_Last updated: 2026-07-20_

## What This Project Is

A **camera-based motor screening suite** for early cognitive-decline
detection. It uses OpenCV + MediaPipe hand tracking (21 landmarks from a
plain webcam) to run clinical-style motor tests measuring hand jitter, tapping
rhythm, and drawing smoothness — biomarkers associated with **early
Alzheimer's disease** in the literature (Namkoong & Roh 2024 and related
studies).

The tracking pipeline originated from a cloned repository
([imadeddinedjekoune/Hand-Detection-3D](https://github.com/imadeddinedjekoune/Hand-Detection-3D)),
which streamed hand landmarks over UDP to a rigged 3D hand in Unity. In April
2026 the tracker was modernized (MediaPipe Tasks API, One-Euro filtering,
CLAHE preprocessing) and repurposed for screening; the Unity receiver was
retired to a local `archive/` folder (git-ignored).

## Architecture

```
run_hub.bat ──► launcher.py  (stdlib-only web hub @ http://127.0.0.1:8770)
                   │ launches each tool in its own console window
                   ├─► screening_tests/iiv_test.py     IIV finger-tapping test
                   ├─► screening_tests/spiral_test.py  Spiral tracing test
                   └─► core/hand_tracking.py           21-landmark tracker + UDP
                            │
                            └── core/hand_utils.py + model/hand_landmarker.task
```

### File Roles

| File | Role |
|---|---|
| `launcher.py` | Control hub: system status, one-click tool launch, research summary page. Standard library only, so it packages cleanly with PyInstaller (see `docs/BUILD_LAUNCHER.md`). |
| `run_hub.bat` | Windows double-click entry point for the hub. |
| `screening_tests/iiv_test.py` | **IIV Finger Tapping Test.** Metronome-paced tapping; measures Intra-Individual Variability of inter-tap intervals and beat-sync consistency (Suzumura et al., Roalf et al. 2018). |
| `screening_tests/spiral_test.py` | **Spiral Tracing Test.** Air-traced Archimedes spiral; measures path deviation, velocity CV%, normalized jerk, completion %, active ratio (Kachouri et al. 2021, Schroter et al. 2003). |
| `core/hand_tracking.py` | General 21-landmark tracker; skeleton overlay + per-hand UDP broadcast to `127.0.0.1:5052` (`L:[x1,y1,z1,...]` / `R:[...]`, pixel-scaled). |
| `core/hand_utils.py` | Shared helpers: `HAND_CONNECTIONS`, One-Euro landmark filtering, CLAHE + sharpening preprocessing. |
| `model/hand_landmarker.task` | MediaPipe hand-landmarker model bundle (~7.5 MB). Scripts resolve it via `__file__`-relative paths. |
| `docs/alzheimers_hand_tracking_analysis.md` | Research deep-dive: evidence base, biomarkers, mapping to webcam tracking. Served by the hub. |
| `docs/BUILD_LAUNCHER.md` | Running the hub and packaging it as a standalone `.exe`. |

### Technical Notes

- All trackers use the **MediaPipe Tasks API** (`HandLandmarker`, VIDEO
  running mode), not the deprecated `solutions` API — required for
  Python 3.12+.
- Landmark x/y are smoothed with per-hand **One-Euro filters**; z is left raw
  (monocular depth is too noisy to smooth usefully).
- Frames are preprocessed (CLAHE on luminance + gentle sharpening) before
  detection; the display frame is untouched.
- Camera source selectable at startup: local webcam or IP stream (e.g.
  Android "IP Webcam" app).
- Audio cues use `winsound` — the test scripts are **Windows-only** as
  written.

## Progress Timeline

| When | Milestone |
|---|---|
| Sep 2023 | Cloned base project: Python tracker → UDP → rigged Blender hand in Unity. |
| Apr 3–4, 2026 | Pivot: tracker modernized to the Tasks API; Unity project retired to `archive/`; Alzheimer's research analysis written. |
| Apr 8, 2026 | Shared utilities factored into `hand_utils.py`; `spiral_test.py` built. |
| Jun 17, 2026 | `iiv_test.py` refined (windowed tap paradigm, audio-lead compensation, sync-consistency metric). |
| Jul 6, 2026 | `launcher.py` control hub + packaging docs — the suite became a single product. |
| Jul 20, 2026 | Repository reorganized into `core/`, `screening_tests/`, `model/`, `docs/`; fresh git history with new documentation. |

## Known Gaps / Suggested Next Steps

- **No results persistence.** Both tests render scores on screen only;
  saving per-session CSV/JSON would enable longitudinal comparison per
  patient.
- **Windows-only audio** (`winsound`) limits portability; a cross-platform
  audio backend would remove that.
- **Jitter/tremor at rest** is discussed in the research doc but not yet a
  standalone test — a postural-tremor measurement could be a third tool.
