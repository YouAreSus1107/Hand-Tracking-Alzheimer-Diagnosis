# Finger-Tapping Test — Revision Plan

_Last updated: 2026-07-23. Target file: `screening_tests/finger_tapping.py`._
_Research basis: [`research/01-webcam-hand-motor.md`](../research/01-webcam-hand-motor.md)._
_All UI work in this plan follows [`UI_STYLE_GUIDE.md`](UI_STYLE_GUIDE.md)._

> **Status: largely shipped (phases 1–4).** The engine/UI split (§C5) is built —
> the engine now lives in `core/tapping/` (`modes.py`, `detector.py`,
> `metrics.py`, `audio.py`) with `finger_tapping.py` reduced to the run loop +
> rendering; the max-speed **B2 "Big & Fast"** mode ships alongside a
> re-calibrated paced **B1**; adaptive/calibrated detection (§C2), richer metrics
> (§C3), the paradigm config (§C1), the beat grid (§A6), shared camera select
> (§A7, `core/camera.py`), the persistent audio worker (§A8), session persistence
> (§C4, `core/session.py`), and the `core/ui/` toolkit (§D) are all in place.
> The **Open Decisions (§F) are resolved** (max-speed primary; OpenCV+PIL). The
> line numbers in §A refer to the pre-refactor file and are kept for history.
> Still open: modes **B3–B7** (§B), the `--validate` Arduino hook (§C6), and the
> optional Qt/web front-end migration (§E.6).

This plan has four parts: **(A)** a line-by-line audit of bugs and logic
problems in the current code, **(B)** a catalog of tapping-test variations to
support, **(C)** algorithm/architecture fixes to make the test more
research-grounded and easier to use, and **(D)** the UI overhaul. It closes with
a phased implementation roadmap.

---

## A. Line-by-Line Code Audit

Severity: 🔴 correctness/validity · 🟠 robustness/usability · 🟡 cleanup.

| # | Sev | Location | Problem | Fix |
|---|----|----------|---------|-----|
| A1 | 🔴 | L61–93, 70–71, 273, 525, 9, 66–67 | **Stale 3 s → 1 s paradigm.** `METRONOME_INTERVAL = 1.0` but the module docstring ("every 3 seconds"), `TAP_DEBOUNCE` comment ("min real ITI ~3000 ms"), `max_iti` comment ("4500 ms"), the beat-arc comment ("3 s window"), and the IIV thresholds ("calibrated for this slower-paced 3 s paradigm") all still describe 3 s. Calibration and copy no longer match behavior. | Pick the paradigm deliberately (see §B/§C1), then make **one config block** the single source of truth and derive all dependent values + copy from it. |
| A2 | 🔴 | L86, 249–250 | **Sync window mis-centered at 1 s.** `TAP_WINDOW_LEAD = AUDIO_LEAD + 0.5 = 0.7`. Window = `[bt-0.7, next_bt-0.7)` = `[bt-0.7, bt+0.3)`. Normal reaction time is 150–400 ms, so a tap at bt+0.35 s falls **past** the window end (bt+0.3) and is misassigned to the next beat. At the old 3 s interval the window ended at bt+2.3 s and hid this. | Derive the window from the paradigm: for a self-paced/max-speed test drop beat-locked windowing entirely; for a paced test set window end ≥ bt + max_expected_RT (≈ bt+0.6 s) and never exceed the interval. |
| A3 | 🔴 | L65, 382–387 | **Fixed absolute tap threshold** (`0.065` normalized distance). Normalized landmark distance scales with apparent hand size (hand size × distance-to-camera). A large or close hand may never dip below 0.065 (missed taps); a small/far hand may sit below it (false "always touching"). | **Per-session calibration** + adaptive threshold: sample open/closed distance during warm-up, set threshold at a fraction of the observed range (e.g. `min + 0.3·(max−min)`) with hysteresis. See §C2. |
| A4 | 🔴 | L66, 388 | **Fixed 300 ms debounce blocks fast tapping.** Fine for 1 Hz paced, but max-speed tapping (5–7 Hz → 140–200 ms ITI) would have real taps rejected as bounce. Blocks the most clinically-cited paradigm (§B2). | Make debounce paradigm-dependent (e.g. 80 ms for max-speed) or replace threshold+debounce with **peak/valley detection** on the distance signal (§C2). |
| A5 | 🔴 | L1–24 vs 70 | **Paradigm ↔ citation mismatch.** Cited work (Suzumura magnetic tapping, Roalf) is *self-paced max-speed* tapping; the code implements *metronome-synced 1 Hz* tapping. IIV in the literature is usually measured on self-paced fast tapping. Current thresholds are not traceable to any cited source. | Implement the self-paced max-speed paradigm as the primary, literature-aligned mode (§B2); keep paced-sync as a secondary rhythm mode with its own honestly-labeled thresholds. |
| A6 | 🟠 | L368–376 | **Metronome drift under frame drops.** If a frame takes longer than one interval, `next_beat_time += INTERVAL` advances only once per frame and `beep_fired` toggling can skip or bunch beeps. | Schedule beats on an absolute grid (`beat_k = t0 + k·INTERVAL`) and, each frame, fire all beats whose time has passed; compute the current beat index from elapsed time. |
| A7 | 🟠 | L319–321 | **Camera hardcoded to index 0.** Other tools (`hand_tracking.py`) prompt for source (webcam / IP stream). Inconsistent; fails on multi-camera machines. | Shared camera-selection helper in `core/` reused by every tool. |
| A8 | 🟠 | L373 | **New thread per beep.** ~30 short-lived daemon threads/run. Works, but audio-start jitter varies. | Single persistent audio worker consuming a queue, or pre-scheduled playback. |
| A9 | 🟡 | L130–131, 284–315, 506 | **Sync biomarker computed but never shown** (`sync_label` marked "no longer shown"; `res_mean_lat_ms`/`res_sync_std_ms` unused in UI). Dead surface. | Either surface sync as a secondary metric in paced mode or remove it; don't compute-and-discard. |
| A10 | 🔴 | L500–505 | **Silent ramp-up trim can under-fill.** `steady_taps = response_times[3:] if len>6 else response_times`, then `compute_iiv` needs ≥10. A run with 11 hits drops to 8 → returns `None` with no clear reason to the user. | Make trim and minimum counts explicit and paradigm-scaled; show *why* a run was unscorable (too few taps / hand lost) rather than a generic "try again". |
| A11 | 🟠 | L65–68, 382–393 | **No amplitude/velocity/decrement extraction** although the module cites decrement and the research file recommends it. Only binary touch events are captured; the rich distance signal is thrown away. | Log the full per-frame distance/time series; derive amplitude, tap velocity, and speed decrement (§C3). |
| A12 | 🔴 | whole file | **No persistence/export.** Results are rendered then discarded on "Try Again" (L613–618). No session record → no longitudinal use, no validation, no clinical pilot. | Shared session schema written to `results/` (§C4) — the #1 roadmap prerequisite. |
| A13 | 🟠 | L353–355 | **Every frame is CLAHE+sharpened then run through MediaPipe** with no FPS guard. On slow machines detection lags, which worsens A6 and tap-timing resolution (30 fps → 33 ms quantization already limits IIV precision). | Measure and display actual FPS; warn if < 24; consider skipping preprocessing when detection confidence is already high. |
| A14 | 🟡 | L95–105, 138–140, 111–132 | **Globals + drawing + logic + audio all in one 629-line script.** Hard to test, hard to reuse across the planned variants. | Refactor into an engine/UI split (§C5) so every variant reuses one detector + one metrics core. |
| A15 | 🟡 | L343 | **Frame is mirrored** (`flip`), good for user, but handedness from MediaPipe is then left/right-swapped relative to the label. Not used today, but will matter when handedness is recorded. | Record true handedness before flip, or account for the flip when labeling. |

**Headline:** A1–A5 and A10/A12 are the ones that affect scientific validity and
must be resolved before the test is trustworthy. A2 in particular means current
sync/hit numbers at the 1 s interval are partly wrong.

---

## B. Tapping-Test Variations to Support

The refactor should treat "test mode" as configuration so all of these share one
engine. Each is backed by the literature in
[`research/01-webcam-hand-motor.md`](../research/01-webcam-hand-motor.md).

| Mode | Description | Primary metrics | Research basis |
|---|---|---|---|
| **B1. Paced single-tap (current)** | One tap per metronome beep; index↔thumb. | IIV (tap-to-tap CV), beat-sync SD | Rhythm-consistency paradigms; keep but re-calibrate. |
| **B2. Max-speed "Big & Fast"** | Tap index↔thumb as big and fast as possible, 10 s. **Primary, most literature-aligned.** | Mean frequency, rhythm CV, IIV, **amplitude**, **speed decrement** | TapTalk "Big and Fast"; Suzumura; Roalf. |
| **B3. Dual-task** | Max-speed tapping **while counting backward** (e.g. from 100 by 7s). | Tapping metrics **+ dual-task cost** (Δ vs single-task) | TapTalk "Dual-Task"; dual-task cost is itself sensitive. |
| **B4. Sequence / multi-finger** | Index→middle→ring→(little) to thumb, repeating. | Sequence rate, error/ordering accuracy, transition-time variability | TapTalk "Sequence"; apraxia/sequencing sensitivity. |
| **B5. Alternating index–middle** | Alternate index and middle finger taps (classic dysdiadochokinesia). | Alternation rate, asymmetry, rhythm CV | 60-s alternating-tap AUC 0.75–0.89 (research file). |
| **B6. Bimanual** | Both hands tap; compare left vs right. | Inter-hand asymmetry, phase coupling | Asymmetry is an early lateralized marker. |
| **B7. Self-paced steady** | Tap at a comfortable steady rate (no metronome). | Preferred rate, IIV, drift over time | Self-paced IIV; removes beat-sync confound. |

Minimum first release: **B2 (primary)** + a re-calibrated **B1**. B3–B7 are
config variations that reuse the same detector and metrics.

---

## C. Algorithm & Architecture Fixes

### C1. One paradigm config, single source of truth
Replace the scattered constants with a `TapMode` dataclass: `name`, `duration`,
`paced` (bool), `interval`, `debounce`, `expected_rate_hz`, `min_taps`,
`trim_taps`, thresholds, and **display copy**. Every dependent value (window
width, `max_iti`, instruction text, threshold bands) is derived from it, killing
the A1 class of bugs. Ship a `MODES` registry keyed by B1–B7.

### C2. Robust tap detection (replaces fixed threshold + debounce)
1. **Warm-up calibration:** during the practice phase, record the distance
   signal while the user does a few slow open/close taps; capture `d_open`
   (max) and `d_closed` (min).
2. **Adaptive threshold with hysteresis:** close when
   `d < d_closed + 0.30·(d_open − d_closed)`, re-open only above
   `d_closed + 0.55·(d_open − d_closed)` — hysteresis prevents chatter near the
   boundary (a cleaner replacement for the fixed debounce).
3. **Peak/valley detection option:** for max-speed modes, detect local minima of
   the smoothed distance signal (each valley = one tap) with a minimum
   inter-valley time = `0.5 / expected_rate_hz`. More amplitude/scale-robust
   than a global threshold (the TapTalk approach).
4. Keep the existing One-Euro + distance-EMA smoothing, but expose the EMA alpha
   per mode (fast modes need less lag).

### C3. Richer metrics
Log the **full `(t, distance)` series**, then derive per run:
- **Frequency** (taps/s) and **inter-tap interval (ITI)** series.
- **IIV** = SD of ITI; **CV%** = IIV/mean·100 (scale-invariant — the headline).
- **Amplitude** = mean valley-to-peak excursion; **amplitude CV**.
- **Speed decrement** = slope of frequency over the trial (fatigue/bradykinesia).
- **Opening/closing velocity** from the distance derivative.
- **Sync SD** (paced modes only): SD of (tap − beat) latency.
- **Dual-task cost** (B3): relative change vs the single-task baseline run.
Report every metric with its literature reference and a plain-language line.

### C4. Session persistence & export (shared schema)
On completion, write one JSON per session to `results/` and append a row to a
CSV index. Proposed schema (shared with every future test and the glove):
```json
{
  "session_id": "uuid", "timestamp": "ISO-8601", "test": "finger_tapping",
  "mode": "big_and_fast", "hand": "right", "duration_s": 10,
  "device": {"camera_fps": 29.7, "resolution": "640x480", "app_version": "x"},
  "metrics": {"frequency_hz": 4.9, "iiv_ms": 41.2, "cv_pct": 12.1,
              "amplitude_cv_pct": 8.0, "decrement_pct_per_s": -1.4,
              "sync_sd_ms": null, "hits": 48, "misses": 0},
  "raw": {"tap_times_s": [...], "distance_series": [[t,d], ...],
          "beat_times_s": [...]}
}
```
This unblocks longitudinal tracking, the Arduino validation comparison, and the
clinical pilot (roadmap §6, items 1/6/9).

### C5. Engine / UI split (testability + reuse)
Refactor `finger_tapping.py` into:
- `core/tapping/detector.py` — landmarks → calibrated distance → tap events
  (pure, unit-testable, no OpenCV window).
- `core/tapping/metrics.py` — series → metrics (pure functions; test against
  the Brazilian FTT dataset / synthetic signals).
- `core/tapping/modes.py` — the `TapMode` registry (B1–B7).
- `core/session.py` — the shared results schema/writer (C4).
- `screening_tests/finger_tapping.py` — the run loop + rendering only, driving
  the above and the UI components from the style guide.
This makes the metrics independently verifiable against the Arduino ground truth
(research file §"Cheap validation").

### C6. Validation hook
Add an optional `--validate` flag that timestamps tap events to the shared
session file so they can be aligned against an Arduino contact-switch/IMU stream
(research file). Output a Bland-Altman-style agreement summary — reproducing
TapTalk's validation on a ~$25 budget.

---

## D. UI Overhaul

**All visual work must conform to [`UI_STYLE_GUIDE.md`](UI_STYLE_GUIDE.md)** —
that file is the design system (tokens, components, motion, accessibility). This
section is the *plan*; the style guide is the *spec*.

### D1. Rendering-stack decision
The current UI is raw `cv2.putText`/`rectangle` (aliased Hershey fonts, hard
rectangles, no easing). Two viable paths, both compatible with the style guide
(which is framework-neutral):
- **Near-term (recommended):** stay in OpenCV but upgrade the drawing layer —
  render text/rounded panels via **Pillow (PIL)** for real anti-aliased fonts
  (Inter/Source Sans), use `cv2.LINE_AA` everywhere, and add an **easing/anim
  helper** so values interpolate frame-to-frame. Gets ~80% of the polish with no
  new framework.
- **Long-term (for a truly "app"-grade product):** move the camera view into a
  **PySide6/Qt** window (or a local web UI like `launcher.py` already uses) with
  the video as a widget and real UI chrome around it. Recommended once the test
  set stabilizes; the style guide tokens carry straight over.

### D2. Concrete UI improvements (per screen)
- **Global:** a persistent top **status bar** — hand-detected indicator,
  lighting/FPS quality chip, current mode, and a subtle brand mark. Rounded
  translucent panels (style-guide `surface` tokens), consistent 8-pt spacing,
  drop shadows for legibility over video.
- **Idle / start:** calm hero card, one primary CTA, plain-language purpose line,
  and a prominent **medical disclaimer** (style-guide tone rules).
- **Instruction:** an **animated demo** — a looping schematic hand showing the
  tap gesture — instead of a wall of text; large accessible type (≥18 px body).
- **Calibration (new):** guided "open and close your hand a few times" step with
  a live gauge filling as calibration completes (drives C2).
- **Countdown:** animated ring that sweeps down with an eased scale-pop on each
  number (motion spec in the style guide).
- **Recording:** replace the current beat arc with the style-guide **beat/rhythm
  indicator** — a pulsing ring that expands on the beat and a live **tap
  sparkline** of the distance signal so the user sees their own rhythm. Live
  metric chips (rate, taps) as styled cards. Gentle border pulse (not a harsh
  white flash) on each tap, respecting reduced-motion.
- **Real-time guidance:** friendly, specific coaching — "Move a little closer",
  "Great rhythm", "Keep your hand in frame" — using the style-guide feedback
  toasts, not raw orange text.
- **Complete / results:** a **results card** with a big headline metric, a
  color+icon status badge (never color alone — accessibility), a small trend
  area (once persistence exists), the reference bands, and clear
  **Retry / Save / Export** actions. Animate values counting up.
- **Accessibility:** minimum type sizes for the 50–89 target group, WCAG-AA
  contrast, color-blind-safe status (icon+label+color), audio cue options, and a
  reduced-motion mode — all defined in the style guide.

### D3. Reusable UI toolkit
Extract the drawing helpers into `core/ui/` (`components.py`, `theme.py`,
`anim.py`) implementing the style-guide tokens/components so **every** test
(tapping, spiral, future speech/oculomotor screens) shares one look. This is
what makes the suite feel like a single professional product.

---

## E. Phased Implementation Roadmap

1. **Correctness patch** (small, high-value): fix A1/A2 (paradigm config +
   window), A6 (beat grid), A7 (camera select); align copy. Ships a trustworthy
   version of the *current* paced test.
2. **Detector + metrics refactor** (C1/C2/C3/C5): engine-UI split, adaptive
   detection, richer metrics. Add mode **B2 (max-speed)** as primary.
3. **Persistence & validation** (C4/C6): session schema + Arduino agreement
   report.
4. **UI toolkit + overhaul** (D1–D3): PIL/anim upgrade, style-guide components,
   redesigned screens.
5. **Additional modes** (B3–B7) as config.
6. **(Later)** optional PySide6/web front-end migration.

## F. Open Decisions (need your input before coding)
- **Primary paradigm:** adopt **max-speed (B2)** as the default (best
  literature support), keeping paced-IIV (B1) as a secondary mode? (Recommended.)
- **Rendering path:** OpenCV+PIL upgrade now, Qt/web later — agree?
- **Validation hardware:** MPU-6050 (feeds the glove) vs contact switch — which
  to design the `--validate` hook around first?
