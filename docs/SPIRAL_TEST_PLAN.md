# Spiral Tracing Test — Re-pivot to Self-Paced Jitter / Smoothness

_Last updated: 2026-07-23. **Status: in progress** — reworking
`screening_tests/spiral_test.py` + new `core/spiral/` engine._
_Research basis: [`research/02-drawing-spiral-clock.md`](../research/02-drawing-spiral-clock.md),
[`alzheimers_hand_tracking_analysis.md`](alzheimers_hand_tracking_analysis.md)._
_All UI work follows [`UI_STYLE_GUIDE.md`](UI_STYLE_GUIDE.md); mirrors the
engine/UI split of [`FINGER_TAPPING_REVISION_PLAN.md`](FINGER_TAPPING_REVISION_PLAN.md)
and [`OCULOMOTOR_TEST_PLAN.md`](OCULOMOTOR_TEST_PLAN.md)._

This document re-designs the spiral test around **what the clinical literature
actually measures** — the *quality* of the drawn line (smoothness / tremor) — and
replaces a home-grown accuracy paradigm with literature-standard metrics.

---

## 1. Why change it

### 1.1 The old paradigm measured the wrong thing

The current test renders a yellow **guide dot** that advances along the spiral on
a fixed time grid; the user chases it. That is a **visuomotor pursuit** task — it
conflates *tracking / reaction ability* with *motor quality*, and its headline
(radial deviation as a % of the outer radius, corresponded by swept angle) is a
construction **no paper defines**.

The **clinical Archimedes spiral test is self-paced free tracing.** The patient
draws the spiral at their own comfortable pace; scoring is on the *tremor and
smoothness of the drawn line*, not on matching a pacer. That self-paced line
quality is exactly the "jitter" signal we want.

### 1.2 The old metrics weren't literature-grounded

The scoring bands were self-admittedly provisional — "bracketed around our own
real traces" — and the headline metric is not one any study reports. The
literature-standard drawing / fine-motor markers of cognitive decline are:

- **Movement smoothness** — normalized jerk and, more robustly, **SPARC**
  (Spectral Arc Length; Balasubramanian et al. 2015).
- **Velocity irregularity** — speed coefficient of variation (V-Rel; Schroter et
  al. 2003 rate this "Very High" sensitivity for AD).
- The review's central insight: *"AD doesn't make you slow — it makes you
  irregularly slow"* (Namkoong & Roh 2024; Schroter 2003; Kachouri 2021).

### 1.3 Outcome

A **self-paced** spiral trace whose **headline is movement smoothness (SPARC +
normalized jerk)**, supported by velocity irregularity and a **bounded**
tremor-spectral readout, with honest per-metric provenance and a documented
validation path. Pure metric logic lives in a unit-tested `core/spiral/` engine.

---

## 2. Task design (self-paced)

| Phase | Behavior |
|---|---|
| Idle / Instruction | Purpose card; copy: *"trace the spiral outward smoothly, at your own comfortable pace."* No mention of chasing a dot. |
| Warmup | Existing self-paced circle, unscored. |
| Prepare | Existing center-hold start trigger (fingertip on the center dot for `PREPARE_HOLD`). |
| **Recording** | **No moving guide dot.** Faint full spiral template is shown as a spatial reference; a **user-driven** "traced-so-far" highlight follows the user's own swept progress. Ends when the fingertip reaches the outer terminus **or** a 60 s safety cap. |
| Complete | Headline **Smoothness index** + support table + provenance. |

**Scoreable gates (data quality, not the headline):** minimum trace duration,
minimum coverage of the template, and minimum data-frame count. A short scribble
returns an honest unscorable reason (mirrors the tapping test), never a number.

---

## 3. Metrics & measurement system

### 3.1 Signal — measure jitter on a *minimally-filtered* fingertip

**Critical:** `smooth_landmarks()` One-Euro-filters landmark x/y at
`min_cutoff = 6 Hz` (`core/hand_utils.py`). That filter **removes the very jitter
we want to measure.** So:

- The **metric channel uses the raw fingertip** (`result.hand_landmarks[0][8]`).
- Smoothed landmarks are used **only for on-screen drawing** (skeleton + dot).
- Frame-to-frame velocity is computed from the raw fingertip pixel path.

### 3.2 Metrics

| Metric | Role | Definition | Source |
|---|---|---|---|
| **SPARC** | **headline** | Spectral Arc Length of the normalized speed-profile magnitude spectrum up to a cutoff. Amplitude- and duration-robust. Presented as a mapped **0–100 smoothness index**. | Balasubramanian et al., *On the analysis of movement smoothness*, J NeuroEng Rehabil 2015 |
| Normalized jerk | smoothness (support) | Mean-squared jerk from the position path, time/length-normalized. | Standard smoothness measure |
| Velocity CV % | irregularity (support) | SD/mean of speed (V-Rel). | Schroter et al. 2003 |
| Tremor power fraction + dominant freq | tremor (support, **caveated**) | Detrend position, PSD, fraction of power in the tremor band + its peak. | PD spiral-tremor analysis |
| Spatial accuracy (deviation) | accuracy (support) | Swept-angle radial deviation — independent of the removed guide dot. | Kachouri 2021 |
| Completion / coverage | **gate** | Fraction of template visited. | — |

### 3.3 The webcam-limits caveat (state it plainly)

- **30 fps → Nyquist 15 Hz.** Physiological tremor (8–12 Hz) sits at the edge and
  is partly unresolvable/aliased; essential/rest tremor (4–8 Hz) is resolvable
  with caution. Tracker quantization confounds the high-frequency bands.
- **Therefore smoothness (SPARC / jerk / velocity CV) is the trustworthy headline**
  — it survives low frame rate. The tremor-spectral figure is **secondary and
  explicitly caveated**, never the headline.
- **Mitigations:** request 60 fps capture (fall back to 30, report actual, warn
  < 24 — as the tapping/oculomotor tests do); measure on the raw fingertip;
  band-limit the tremor readout to what the actual fps resolves.

---

## 4. Scoring bands & validation path

Bands for each metric carry an honest **provenance note** and every results
screen states: **screening, not diagnosis**; provisional; performance depends on
lighting, camera, and distance.

Bands are **provisional** — bracketed from our own traces plus the literature's
*direction* — until validated. **Validation path:** score the public
**HandPD / NewHandPD** spiral datasets (PD labels; method transfers) to calibrate
cutoffs, then re-target to cognitive cohorts
([`research/07-datasets-and-tools.md`](../research/07-datasets-and-tools.md)).
This is a documented plan to *earn* thresholds, not a claim of validation now.

---

## 5. Architecture — `core/spiral/` engine

Mirror `core/tapping/` and `core/gaze/`: pure logic in `core/spiral/`, run loop +
rendering stays in the screening script.

| File | Role | Parallels |
|---|---|---|
| `core/spiral/__init__.py` | package exports | `core/gaze/__init__.py` |
| `core/spiral/geometry.py` | spiral gen, arc-length resample, nearest-point (moved pure fns) | — |
| `core/spiral/metrics.py` | SPARC, jerk, velocity CV, tremor spectral, deviation, completion, active ratio — all pure | `core/tapping/metrics.py` |
| `screening_tests/tests/test_spiral.py` | unit tests on synthetic traces | `screening_tests/tests/test_gaze.py` |

**Modified:** `screening_tests/spiral_test.py` (remove guide-dot pacing,
completion end-condition, raw-fingertip capture, new `_finish` / `screen_complete`,
60 fps request); `core/session.py` `_INDEX_FIELDS` (+ `sparc`, `tremor_power_frac`).

**Reused as-is:** `core/ui/*`, `core/camera.py`, `core/session.py`,
`core/tapping/audio.py`, One-Euro helpers (display only).

---

## 6. UI (per `UI_STYLE_GUIDE.md`)

- **Instruction:** new self-paced copy; drop the "keep near the yellow dot" line.
- **Recording:** no guide dot; faint template + user-driven traced-so-far
  highlight; HUD shows elapsed + a live smoothness proxy; fingertip colored by
  the live smoothness band.
- **Complete:** headline **Smoothness index** with count-up + status badge (color
  **and** icon, never color alone); support table (velocity CV, norm. jerk, tremor
  readout w/ caveat, completion, frames); provenance + screening disclaimer.

---

## 7. Phased roadmap

1. **[in progress] Engine + tests** — `geometry.py` + `metrics.py` (move existing
   pure fns, add SPARC + tremor); `test_spiral.py` on synthetic traces. No live
   behavior change yet.
2. **Signal channel** — raw-fingertip capture; 60 fps request.
3. **Paradigm swap** — remove pacing; self-paced completion end; user-driven
   progress highlight.
4. **Scoring + UI** — new bands/provenance; `_finish` + `screen_complete` rework;
   `save_session` index fields; instruction copy.
5. **(Later)** validate bands on HandPD/NewHandPD; optional explainable-classifier
   track.

---

## 8. Verification

- **Unit:** `python screening_tests/tests/test_spiral.py` — clean spiral scores
  smooth; injected 5 Hz tremor lowers SPARC and raises the tremor readout; SPARC
  stable under duration/amplitude scaling; degenerate/short traces return `None`,
  not a crash.
- **End-to-end:** `.venv/Scripts/python screening_tests/spiral_test.py` — smooth
  slow trace → high smoothness / low tremor; deliberately shaky trace → the
  reverse; no guide dot; self-paced completion ends the run; results card + saved
  JSON/CSV carry the new metrics.
- **Regression:** launcher card still launches; `results/index.csv` gains the new
  columns without breaking old rows.
