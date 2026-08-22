# Hand-Detection-3D — Project Overview & Progress

_Last updated: 2026-07-24_

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
run_hub.bat ──► launcher.py  (stdlib-only web server @ http://127.0.0.1:8770)
                   │  serves the dashboard frontend from launcher_web/
                   │  (index.html, styles.css, app.js, background.js, hand3d.js)
                   │  launches each tool in its own console window:
                   ├─► screening_tests/finger_tapping.py  Finger-tapping test
                   ├─► screening_tests/spiral_test.py      Spiral tracing test
                   ├─► screening_tests/oculomotor_test.py  Pro/anti-saccade test
                   └─► core/hand_tracking.py               21-landmark tracker + UDP
                            │
       shared core/ ────────┤
        ├─ hand_utils.py    │  One-Euro filters, CLAHE, HAND_CONNECTIONS
        ├─ camera.py        │  camera-source prompt/open helper
        ├─ session.py       │  results schema → results/*.json + index.csv
        ├─ tapping/         │  tapping engine (modes, detector, metrics, audio)
        ├─ gaze/            │  gaze engine (tracker, calibrate, detector, metrics, tasks)
        └─ ui/              │  PIL-overlay UI toolkit (theme, components, anim)
                            │
                            ├── model/hand_landmarker.task
                            └── model/face_landmarker.task
```

### File Roles

| File | Role |
|---|---|
| `launcher.py` | Control hub **web server**: system status, one-click tool launch, serves the research summary. Python standard library only, so it packages cleanly with PyInstaller (see `docs/BUILD_LAUNCHER.md`). The dashboard frontend is served as static files from `launcher_web/`. |
| `launcher_web/` | Dashboard frontend served by the hub: `index.html`, `styles.css`, `app.js` (UI + launch/stop API calls, the longitudinal **Analysis** view, and the **Why This** differentiation page), `background.js` (WebGL reaction-diffusion), `hand3d.js` (Three.js hand model). The **Why This** tab summarises how the suite differs from other at-home screeners (pillars, a suite-vs-consumer-vs-TAS-Test matrix), drawing on `research/` + `ROADMAP.md`. Bundled into the exe via `--add-data` for frozen builds. |
| `run_hub.bat` | Windows double-click entry point for the hub. |
| `screening_tests/finger_tapping.py` | **Finger Tapping Test** — run loop + rendering only. Metronome-paced (and max-speed) tapping; headline metric is CV% of inter-tap intervals, plus beat-sync consistency (Suzumura et al., Roalf et al. 2018). The engine lives in `core/tapping/`. Persists each session via `core/session.py`. |
| `screening_tests/spiral_test.py` | **Spiral Tracing Test.** Air-traced Archimedes spiral; measures path deviation (% of spiral radius), velocity CV%, normalized jerk, completion %, active ratio (Kachouri et al. 2021, Schroter et al. 2003). Persists to `results/` via `core/session.py`. |
| `screening_tests/oculomotor_test.py` | **Eye Movement Test** (pro/anti-saccade) — run loop + rendering only. A dot flashes left/right; look toward it (prosaccade baseline, 16 trials) then away from it (anti-saccade, 24 trials), then a **fixation-stability hold** ("Part 3 — Hold Still"). Headline metric is anti-saccade error rate %; latency leads with Anti − Pro (cancels the fixed camera/display offset); fixation stability adds RMS jitter, 2-D BCEA, and saccadic-intrusion rate as a secondary readout. Engine in `core/gaze/`. Persists each session via `core/session.py`. (Opwonya et al. 2022, Crawford et al. 2005, Antoniades et al. 2013.) |
| `core/hand_tracking.py` | General 21-landmark tracker; skeleton overlay + per-hand UDP broadcast to `127.0.0.1:5052` (`L:[x1,y1,z1,...]` / `R:[...]`, pixel-scaled). |
| `core/hand_utils.py` | Shared helpers: `HAND_CONNECTIONS`, One-Euro landmark filtering, CLAHE + sharpening preprocessing. |
| `core/camera.py` | Shared camera-source prompt/open helper (local webcam vs. IP stream). |
| `core/session.py` | **Shared results schema.** `save_session(...)` writes one JSON per session to `results/` (git-ignored) and appends a row to `results/index.csv` for longitudinal views. Designed to be reused by the spiral test and the future glove stream. |
| `core/tapping/` | Finger-tapping engine: `modes.py` (TapMode registry — max-speed + paced), `detector.py` (calibrated hysteresis tap detection), `metrics.py` (pure scoring functions), `audio.py` (beep worker). |
| `core/gaze/` | Oculomotor engine: `tracker.py` (Face Landmarker → head-invariant, One-Euro-smoothed iris ratio + vertical proxy + blink guard), `calibrate.py` (3-point deadband + L/R mapping), `detector.py` (pure saccade onset/direction/latency events), `metrics.py` (pure scoring), `tasks.py` (SaccadeTask registry — pro + anti), `fixation.py` (fixation-stability analyzer: RMS jitter, BCEA, intrusion rate). Pure logic unit-tested in `screening_tests/tests/test_gaze.py`. |
| `core/ui/` | Shared UI toolkit implementing `docs/UI_STYLE_GUIDE.md`: `theme.py` (design tokens), `components.py` (PIL-overlay Canvas: panels, chips, buttons, toasts, sparkline), `anim.py` (easing). |
| `model/hand_landmarker.task` | MediaPipe hand-landmarker model bundle (~7.5 MB). Scripts resolve it via `__file__`-relative paths. |
| `model/face_landmarker.task` | MediaPipe face-landmarker model bundle (~3.7 MB, 478 landmarks incl. iris) for the oculomotor test. Resolved via `__file__`-relative path. |
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
- Audio cues play via `winsound` on Windows (system-default playback device)
  and via `sounddevice` (PortAudio) on macOS/Linux.

## Progress Timeline

| When | Milestone |
|---|---|
| Sep 2023 | Cloned base project: Python tracker → UDP → rigged Blender hand in Unity. |
| Apr 3–4, 2026 | Pivot: tracker modernized to the Tasks API; Unity project retired to `archive/`; Alzheimer's research analysis written. |
| Apr 8, 2026 | Shared utilities factored into `hand_utils.py`; `spiral_test.py` built. |
| Jun 17, 2026 | `finger_tapping.py` refined (windowed tap paradigm, audio-lead compensation, sync-consistency metric). |
| Jul 6, 2026 | `launcher.py` control hub + packaging docs — the suite became a single product. |
| Jul 20, 2026 | Repository reorganized into `core/`, `screening_tests/`, `model/`, `docs/`; fresh git history with new documentation. |
| Jul 22, 2026 | `launcher.py` slimmed 1,747 → 337 lines: the embedded dashboard was extracted into static `launcher_web/` files (HTML/CSS/JS); frozen-exe path resolution added via `sys._MEIPASS`. |
| Jul 23, 2026 | Finger-tapping reworked into an engine (`core/tapping/`) + thin run loop; **session persistence** shipped (`core/session.py` → `results/*.json` + `index.csv`); shared `core/camera.py` helper and `core/ui/` toolkit (per `UI_STYLE_GUIDE.md`) added. |
| Jul 23, 2026 | **Oculomotor (pro/anti-saccade) test built:** `model/face_landmarker.task` added; gaze engine in `core/gaze/` (tracker, 3-point calibration, pure saccade detector + metrics, task registry) with unit tests; `screening_tests/oculomotor_test.py` run loop; persistence + launcher card/detail page wired. Headline: anti-saccade error rate %. |
| Jul 23, 2026 | **Spiral persistence + cross-platform audio.** Spiral test wired into the shared results schema (fixed a `mean_dev_px`/`mean_dev_pct` key-mismatch crash on the results screen; corrected `%`-of-radius units); `core/session.py` gained spiral index columns with a one-time `index.csv` header migration. Audio backend (`core/tapping/audio.py`) made cross-platform: `winsound` on Windows (system-default device), `sounddevice` on macOS/Linux. |
| Jul 24, 2026 | **Fixation-stability test added** (research §10.3, plan §7 phase 5): a "Part 3 — Hold Still" block after the anti-saccade block. New `core/gaze/fixation.py` computes RMS jitter (headline), 2-D BCEA at P=0.68, and saccadic-intrusion rate; `tracker.py` gained an (uncalibrated) vertical iris proxy for the second BCEA axis; three fixation columns added to the results schema, with unit tests. Reported as a secondary readout — BCEA is relative (degrees pending viewing-distance work), and metrics sit above the One-Euro smoothing floor. |

## Known Gaps / Suggested Next Steps

- **Session persistence — done for all three tests.** `core/session.py`
  writes one JSON per session to `results/` plus an append-only `index.csv`,
  used by finger tapping, spiral, and oculomotor alike. Remaining work: build
  a **longitudinal view** over the index.
- **Cross-platform audio — done.** `core/tapping/audio.py` plays via
  `winsound` on Windows and `sounddevice` on macOS/Linux.
- **Hand jitter/tremor at rest** is discussed in the research doc but not yet a
  standalone test — a postural-tremor measurement could be a third tool. (Note:
  *gaze* fixation jitter is now measured by the oculomotor test's Part 3.)
- **Oculomotor test now built, incl. fixation stability.** The webcam
  pro/anti-saccade test designed in
  [`OCULOMOTOR_TEST_PLAN.md`](OCULOMOTOR_TEST_PLAN.md) is implemented
  (`screening_tests/oculomotor_test.py` + `core/gaze/`), persists to the shared
  results schema, and is launchable from the hub. The fixation-stability task
  (plan §7 phase 5) shipped as "Part 3 — Hold Still" (`core/gaze/fixation.py`).
  Remaining: smooth-pursuit (needs a continuous 2-D gaze estimator), a
  *calibrated* vertical axis / BCEA in degrees (research §10.1, §10.6), and
  validation against live gaze data to tune the deadband and latency offsets.

See [`ROADMAP.md`](ROADMAP.md) for the detailed forward plan — the planned
wearable "Hand Digital Twin" (co-contraction) integration, the `speech_tests/`
module, additional laptop-only tests (oculomotor, Trail Making, keystroke), and
the clinical pilot — and how each maps to the published literature.
