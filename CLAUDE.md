# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Camera-based motor screening suite for early cognitive-decline detection. Uses OpenCV + MediaPipe hand tracking (21 landmarks) to run clinical-style motor tests: IIV finger tapping and spiral tracing. Originated as a fork-style clone of a Unity hand-mirroring project; the Unity side is retired (local `archive/` only, git-ignored) and only the Python suite is developed.

## Running

```bash
pip install -r requirements.txt   # opencv-python, mediapipe
python launcher.py                # control hub at http://127.0.0.1:8770
```

Or run tools directly: `python screening_tests/iiv_test.py`, `python screening_tests/spiral_test.py`, `python core/hand_tracking.py`. Each prompts for camera source (`1` webcam / `2` IP stream URL); press `q` to quit. Test scripts use `winsound` → Windows-only.

## Architecture

- **`launcher.py`** — stdlib-only web hub (port 8770). Launches each tool via `subprocess.Popen` in its own console (`cwd=BASE_DIR`); one tool at a time may hold the camera. Packaging instructions in `docs/BUILD_LAUNCHER.md`.
- **`core/hand_utils.py`** — shared by all tools: `HAND_CONNECTIONS`, One-Euro filters (smooth landmark x/y; z left raw), `preprocess_for_mediapipe` (CLAHE + sharpen).
- **`core/hand_tracking.py`** — tracker + UDP broadcast of pixel-scaled landmarks to `127.0.0.1:5052`, format `L:[x1,y1,z1,...]` per hand.
- **`screening_tests/iiv_test.py`** — metronome-paced tapping; scores IIV of inter-tap intervals and sync-latency std dev. Beeps fire `AUDIO_LEAD` early to offset audio latency.
- **`screening_tests/spiral_test.py`** — air spiral tracing; scores path deviation, velocity CV%, normalized jerk, completion, active ratio.
- **`model/hand_landmarker.task`** — MediaPipe model bundle. All scripts resolve it via `__file__`-relative paths (`_REPO_ROOT / "model" / ...`), so they work from any cwd.

## Key Details

- MediaPipe **Tasks API** in VIDEO running mode (not the deprecated `solutions` API) — required for Python 3.12+.
- Screening tests add `core/` to `sys.path` at the top of the file to import `hand_utils`; keep that block first if editing imports.
- No frame flipping — right hand stays right in the feed.
- Test results are display-only so far; nothing is persisted (known gap, see `docs/PROJECT_OVERVIEW.md`).
