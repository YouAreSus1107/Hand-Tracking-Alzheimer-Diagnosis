# Oculomotor (Pro/Anti-saccade) Test — Design & Build Plan

_Last updated: 2026-07-23. **Status: built** — `screening_tests/oculomotor_test.py`
+ `core/gaze/`; roadmap phases 1–4 complete (see §7). Live-gaze validation pending._
_Research basis: [`research/04-oculomotor-gaze.md`](../research/04-oculomotor-gaze.md)._
_All UI work in this plan follows [`UI_STYLE_GUIDE.md`](UI_STYLE_GUIDE.md)._

This is the design document for a new **oculomotor screening test** — a
webcam-only pro-saccade / anti-saccade task. It has three parts: **(1)** the
research basis and why this task earns a place in the suite, **(2)** the
**metrics and measurement system** (exactly what is computed and how, honest
about webcam limits), and **(3)** the build plan — task layout, architecture,
UI, and a phased roadmap. It mirrors the structure and engine/UI split proven in
[`FINGER_TAPPING_REVISION_PLAN.md`](FINGER_TAPPING_REVISION_PLAN.md).

First release scope (decided): **pro-saccade + anti-saccade only.** Smooth
pursuit and fixation-stability are deferred (see §7). The stimulus is horizontal
(left/right), which is the axis a webcam estimates most reliably.

---

## 1. Purpose & Research Basis

**Why oculomotor.** Saccadic eye-movement control — especially the *inhibitory*
control probed by the anti-saccade task — is among the **earliest** measurable
signatures of Alzheimer's disease, and it is capturable from a plain webcam. It
adds a cognitive-inhibition domain the current motor tests (tapping, spiral)
don't touch, at zero hardware cost, consistent with the project's laptop-only
thesis ([ROADMAP §5.2](ROADMAP.md)).

### 1.1 Clinical evidence (supports building the test)

**Opwonya et al. (2022) — meta-analysis.** *"Saccadic Eye Movement in Mild
Cognitive Impairment and Alzheimer's Disease: A Systematic Review and
Meta-Analysis,"* **Neuropsychology Review** 32(2):193–227.
DOI [10.1007/s11065-021-09495-3](https://doi.org/10.1007/s11065-021-09495-3) ·
[PMC9090874](https://pmc.ncbi.nlm.nih.gov/articles/PMC9090874/).
Pooling 27 task-condition datasets, the **anti-saccade error rate** shows a
**large** effect separating AD dementia from controls (**SMD 1.59**, 95% CI
1.09–2.09) and a **moderate** effect for MCI (SMD 0.55). Latency effects are
smaller (anti-saccade latency: ADD 0.55, MCI 0.35; prosaccade latency: ADD 0.39,
MCI n.s.). The review's headline conclusion: **anti-saccade paradigms outperform
prosaccade paradigms** at telling patients from controls — which is exactly why
the anti-saccade *error rate* is this test's headline metric.

**Crawford et al. (2005) — patient study.** *"Inhibitory control of saccadic eye
movements and cognitive impairment in Alzheimer's disease,"* **Biological
Psychiatry** 57(9):1052–1060.
[PMID 15860346](https://pubmed.ncbi.nlm.nih.gov/15860346/).
AD patients produced a roughly **10-fold** increase in uncorrected anti-saccade
errors (**mean 25.4%** vs controls), and error frequency **correlated with
dementia severity**. This anchors the "elevated" end of the scoring bands and
demonstrates the effect is large enough to survive a coarse consumer sensor.

### 1.2 Measurement methodology (how the task is done)

**Antoniades et al. (2013) — the standardised protocol.** *"An internationally
standardised antisaccade protocol,"* **Vision Research** 84:1–5.
DOI [10.1016/j.visres.2013.02.007](https://doi.org/10.1016/j.visres.2013.02.007)
· [PMID 23474300](https://pubmed.ncbi.nlm.nih.gov/23474300/).
The reference protocol for clinical saccade testing. Its two headline endpoints
are **correct anti-saccade latency** (ms from target onset to the first correct
eye movement) and **anti-saccade error rate** (% of trials whose first saccade
goes *toward* the target). Key design rules this test adopts: run a **prosaccade
block first** as a baseline, use a **gap** between fixation offset and target
onset, **exclude anticipatory / express saccades** (implausibly short latencies),
and **distinguish corrected from uncorrected errors**.

**Webcam adaptation (secondary methods refs).** Remote/browser anti-saccade
validation — [bioRxiv 2023.07.11.548447](https://www.biorxiv.org/content/10.1101/2023.07.11.548447v1.full)
and a remote eye-tracking validation ([PMC12798852](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12798852/))
— reproduce the laboratory signatures on consumer webcams: anti-saccade latency
> prosaccade latency, erroneous responses have *shorter* reaction times, and the
gap paradigm raises error rate while lowering latency. Reported **healthy median
error rate ≈ 5.8%** (range 2–25%), which anchors the "typical" end of the bands.

---

## 2. Task Design

Two task modes, one shared gaze engine (parallels the `TapMode` registry in
`core/tapping/modes.py`):

| Mode | Instruction | Role | Headline metric |
|---|---|---|---|
| **Prosaccade** | "Look **toward** the dot when it appears." | Baseline / warm-up; establishes each user's normal saccade latency and a latency floor to subtract. | Prosaccade latency (ms) |
| **Anti-saccade** | "Look to the **opposite side** from the dot — away from it." | **Primary**, literature-aligned. | **Anti-saccade error rate (%)** |

### 2.1 Trial structure (per trial)

```
 central fixation cross        target dot (L or R)         return
 (jittered 1.0–2.0 s)   ─gap─►  at fixed eccentricity  ──►  to center
                        200 ms   held ~1.0 s                 (inter-trial)
```

- **Gap paradigm:** the fixation cross is removed ~200 ms *before* the target
  appears (Antoniades). Raises error rate and shortens latency, sharpening the
  inhibitory signal.
- **Direction:** target steps **left or right** only, at a fixed horizontal
  screen eccentricity. L/R order is randomised and count-balanced within a block.
- **Blocks:** prosaccade block first (baseline), then anti-saccade block.
- **Trial counts (screening length):** ~**16 prosaccade** + ~**24 anti-saccade**
  scored trials, preceded by ~3 unscored practice trials per block. This is
  deliberately **shorter than the clinical 40–60 trials** — an explicit
  screening-vs-precision trade the results screen should state (§6). Configurable
  per mode.

### 2.2 Per-user calibration (required, runs first)

Iris geometry differs per face and per seating distance, so absolute gaze angle
is unreliable without calibration. A short **3-point** sequence — look at
**center → left → right** targets — maps the raw iris signal to screen zones and
sets the **central deadband** (the band around center that counts as "not yet
moved"). This reuses the guided-calibration pattern already built for tapping
(`finger_tapping.py` `screen_calibration` + `core/tapping/detector.py`
`Calibrator`): a live progress gauge, "having trouble?" coaching, and a
face-visibility guard.

---

## 3. Metrics & Measurement System

### 3.1 From pixels to a gaze signal

MediaPipe **Face Landmarker** returns 478 landmarks including the **iris**
(refined iris landmarks). Per eye, the horizontal gaze proxy is the iris-center x
expressed **relative to the inner/outer eye-corner x** (so it is invariant to
head translation):

```
gaze_x_eye = (iris_center_x − eye_inner_x) / (eye_outer_x − eye_inner_x)   # ~0..1
gaze_x     = mean(gaze_x_left, gaze_x_right)      # averaged across eyes
```

`gaze_x` is **One-Euro smoothed** (same filter family as the hand landmarks in
`core/hand_utils.py`), then mapped through the calibration to a signed
**horizontal gaze position** in [−1, +1], with a central **deadband**
`[−δ, +δ]`.

### 3.2 Event extraction (pure, unit-testable)

Per trial, timing is anchored to **t₀ = the frame on which the target dot is
first actually rendered** (not its intended time — the render frame is stamped,
matching how tapping stamps beats on an absolute grid).

- **Saccade onset:** the first frame after t₀ at which `gaze_x` leaves the
  deadband, i.e. `|gaze_x| > δ`, and keeps that sign for ≥2 frames (debounce
  against single-frame tracker noise).
- **Direction:** `sign(gaze_x)` at onset → left / right.
- **Latency:** `t(onset) − t₀`, in ms.
- **Correct vs error:**
  - *Prosaccade:* correct if onset direction is **toward** the target.
  - *Anti-saccade:* **error** if onset direction is **toward** the target
    (failure of inhibition); correct if **away**.
- **Corrected error:** an anti-saccade error whose gaze subsequently crosses to
  the correct side within the hold window → counted separately (Antoniades).

**Validity filters (per trial):**
- Exclude **anticipatory / express** saccades: latency **< 90 ms** (cannot be a
  genuine stimulus-driven response).
- Exclude **misses / no-response:** no deadband crossing before the hold window
  ends (~800 ms cutoff), or the face was not tracked for the trial.
- A run is **scoreable** only with a minimum count of valid anti-saccade trials
  (and a minimum face-visible ratio); otherwise the results screen explains *why*
  (too few valid trials / face lost) rather than a generic failure — mirroring
  the tapping test's honest unscorable-run handling.

### 3.3 Run endpoints

| Metric | Definition | Notes |
|---|---|---|
| **Anti-saccade error rate %** | uncorrected+corrected anti errors ÷ valid anti trials | **headline** — best AD discriminator (Opwonya SMD 1.59) |
| Corrected-error rate % | anti errors later self-corrected ÷ valid anti trials | inhibition vs error-monitoring |
| Correct anti-saccade latency (ms) | mean latency of correct anti trials | coarse at 30 fps (§3.4) |
| Prosaccade latency (ms) | mean latency of correct pro trials | per-user baseline |
| **Anti − Pro latency (ms)** | anti latency minus pro latency | **cancels the fixed camera+display offset** — the robust latency readout |
| Latency CV % | SD/mean of correct latencies | timing variability |
| Express/anticipatory count | trials excluded by the <90 ms filter | validity transparency |
| Valid-trial count, face-visible ratio | data-quality gates | drives scoreable/unscorable |

Every metric is persisted; the results card surfaces the headline + a compact
table, each with a plain-language line (style-guide tone).

### 3.4 The 30 fps caveat (state it plainly)

A saccade lasts **30–100 ms**, so at 30 fps (33 ms/frame) a webcam **cannot**
resolve saccade *velocity or trajectory* — those metrics are deliberately **out
of scope**. What a webcam *can* recover:

- **Direction → error rate:** fully robust. Direction is a coarse left/right
  decision that survives low frame rate and low spatial precision. This is why
  error rate, not latency, is the primary endpoint — and it happens to be the
  strongest biomarker anyway.
- **Latency:** measurable but quantised to ±1 frame (~33 ms), plus an **unknown
  but roughly fixed** camera-exposure + display-render offset.

**Mitigations built into the design:**
1. **Request 60 fps** capture (`cap.set(CAP_PROP_FPS, 60)` + MJPG fourcc) and
   fall back to 30; report the *actual* measured fps and warn below 24 (as the
   tapping test already does).
2. **Stamp the true render frame** as t₀.
3. **Report Anti − Pro latency:** the fixed sensor/display offset is common to
   both blocks, so the difference cancels it — a far more trustworthy latency
   figure than either absolute value.
4. Keep **error rate** as the headline; treat absolute latencies as secondary.

---

## 4. Architecture

Reuse the `finger_tapping.py` engine/UI split — **reuse, don't re-invent.** Pure
logic in `core/gaze/`, run-loop + rendering in the screening script.

**New files (this feature):**
| File | Role | Parallels |
|---|---|---|
| `model/face_landmarker.task` | **New MediaPipe model download** (~3.7 MB) — the only external asset. Resolve via `__file__`-relative path. | `model/hand_landmarker.task` |
| `core/gaze/tracker.py` | Face Landmarker wrapper → smoothed horizontal `gaze_x`. | `App.detect_hand` |
| `core/gaze/calibrate.py` | 3-point calibration → deadband + L/R mapping. | `core/tapping/detector.py` `Calibrator` |
| `core/gaze/detector.py` | gaze signal → saccade onset/direction events (pure). | `core/tapping/detector.py` `TapDetector` |
| `core/gaze/metrics.py` | trials → error rate + latency stats (pure functions). | `core/tapping/metrics.py` |
| `core/gaze/tasks.py` | `SaccadeTask` registry (pro/anti), stimulus schedule + copy. | `core/tapping/modes.py` `TapMode` |
| `screening_tests/oculomotor_test.py` | run loop + rendering only (state machine + `App`). | `screening_tests/finger_tapping.py` |

**Reused as-is:**
- `core/ui/` — `Canvas`, components, `theme`, `anim` for **every** screen.
- `core/camera.py` — `select_camera_source` / `open_capture`.
- `core/session.py` — `save_session(test="oculomotor", mode="anti"/"pro", …)`.
  Extend `_INDEX_FIELDS` with oculomotor columns (`error_rate_pct`,
  `antisaccade_latency_ms`, `prosaccade_latency_ms`, `anti_minus_pro_ms`,
  `valid_trials`); the full metrics dict already lands in the per-session JSON.
- `core/tapping/audio.py` — `AudioWorker` / `build_tone` for an optional target
  tick (a cue when the dot jumps).
- One-Euro filter helpers from `core/hand_utils.py`.
- `launcher.py` — add a `TOOLS["oculomotor"]` entry; optionally surface
  `face_landmarker.task` presence in `status_payload`.

---

## 5. UI Screens

State machine reused from the tapping test, rendered entirely through `core/ui`
per `UI_STYLE_GUIDE.md`: **IDLE → INSTRUCTION → CALIBRATION (3-point) →
COUNTDOWN → PRACTICE → RECORDING (trials) → COMPLETE.**

- **Idle / start:** calm hero card, purpose line, one primary CTA (Prosaccade
  baseline → Anti-saccade), medical disclaimer ribbon.
- **Instruction:** short animated schematic — a dot jumps aside, an arrow shows
  looking **away** (anti) — over large accessible type, not a wall of text.
- **Calibration:** "look at each dot" with a filling gauge and face-visibility
  coaching toast; sets the deadband.
- **Countdown:** the style-guide eased ring + scale-pop number.
- **Practice:** a few unscored trials with immediate correct/incorrect feedback
  so the user learns the (counter-intuitive) anti-saccade rule.
- **Recording:** the fixation cross + jumping target dot, a subtle per-trial
  correct/incorrect tick, a live trials-done chip, and a progress bar. **The
  jumping dot is essential signal, not decoration**, so it is **exempt from
  `REDUCED_MOTION`** (which still governs UI flourishes like ring pulses).
- **Complete:** results card — big **anti-saccade error rate**, a color **+ icon**
  status badge (never color alone), the compact metric table (latencies, Anti−Pro,
  valid trials), the reference bands, the screening-length note, and the saved
  path. Values count up (style-guide motion).

---

## 6. Scoring Bands & Honesty

Anti-saccade **error rate** bands (non-diagnostic):

| Band | Range | Provenance |
|---|---|---|
| Typical | **< 20%** | healthy webcam median ≈ 5.8%; lab healthy 2–25% |
| Monitor | **20–40%** | around the AD mean of ~25.4% (Crawford) |
| Elevated | **> 40%** | well above healthy range |

Bands carry an honest provenance note (as the tapping modes do via
`thresholds_note`) and the results screen states: **screening, not diagnosis**;
short-form (fewer trials than clinical); performance depends on lighting, camera
quality, glasses, and attention. All per the style guide's tone and
accessibility rules (min type sizes for the 50–89 target group, WCAG-AA
contrast, icon+label+color status).

---

## 7. Phased Roadmap

1. **[DONE] Model + gaze signal:** `face_landmarker.task` added; `core/gaze/tracker.py`
   produces a One-Euro-smoothed averaged iris ratio with a blink guard. Live
   left/center/right classification is set by the calibration layer.
2. **[DONE] Calibration + detector + metrics** (`core/gaze/calibrate.py`,
   `detector.py`, `metrics.py`): pure, unit-tested against synthetic gaze traces
   (`screening_tests/tests/test_gaze.py`, 18 tests).
3. **[DONE] Task engine + run loop** (`core/gaze/tasks.py`,
   `screening_tests/oculomotor_test.py`): prosaccade then anti-saccade, full
   screen flow via `core/ui` (idle → instruction → 3-point calibration →
   countdown → practice → recording → complete), gap paradigm, 60 fps request.
4. **[DONE] Persistence:** `save_session(test="oculomotor", mode="pro_anti", …)`;
   `_INDEX_FIELDS` extended with the oculomotor columns; launcher `TOOLS` entry,
   dashboard card + detail page, and `face_model_present` status.
5. **(Later)** smooth pursuit and fixation-stability tasks (added as further
   `SaccadeTask`-style entries reusing the same engine); optional DL gaze
   classifier once labelled data exists (research file §"Repos / tools").

**Not yet validated on live gaze.** The engine and UI are complete and pass
synthetic-trace unit tests, but the deadband defaults, blink threshold, and
latency behavior still need tuning against real webcam sessions.

---

## 8. Open Decisions
- **Capture fps:** attempt 60 fps for finer latency, fall back to 30 — accept the
  variability, or hard-require ≥ a threshold before allowing a scored run?
- **Trial counts:** pro 16 / anti 24 (screening) vs longer blocks for stability.
- **Calibration:** 3-point vs 5-point; auto re-calibrate if the face box drifts
  significantly mid-session?
- **Latency reporting:** show absolute latencies at all, or lead with **Anti − Pro**
  only, to avoid over-trusting the offset-laden absolutes?
