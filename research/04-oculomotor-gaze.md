# Oculomotor: Webcam Eye Tracking & Saccades

Maps to: oculomotor test (webcam only) — **built** (`screening_tests/oculomotor_test.py`
+ `core/gaze/`), designed in [`../docs/OCULOMOTOR_TEST_PLAN.md`](../docs/OCULOMOTOR_TEST_PLAN.md).
Pro/anti-saccade first release: anti-saccade error rate is the headline metric,
latency reported as Anti − Pro. Section 10 below is the forward plan for this
test now that the v1 pipeline works.

## Core papers (test rationale + methodology)

**Saccadic eye movement in MCI and AD — systematic review & meta-analysis
(Neuropsychology Review 2022)** — Opwonya et al.
[PMC9090874](https://pmc.ncbi.nlm.nih.gov/articles/PMC9090874/) ·
[doi:10.1007/s11065-021-09495-3](https://doi.org/10.1007/s11065-021-09495-3)
→ Anti-saccade **error rate** separates AD dementia from controls with a *large*
effect (**SMD 1.59**, CI 1.09–2.09); MCI moderate (0.55). Anti-saccade beats
prosaccade for discrimination. **The headline justification** — error rate is the
primary endpoint.

**Inhibitory control of saccades in AD (Biological Psychiatry 2005)** — Crawford
et al. [PMID 15860346](https://pubmed.ncbi.nlm.nih.gov/15860346/)
→ AD ~**10×** more uncorrected anti-saccade errors (**mean 25.4%** vs controls);
error rate correlates with dementia severity. Anchors the "elevated" scoring band.

**An internationally standardised antisaccade protocol (Vision Research 2013)** —
Antoniades et al. [PMID 23474300](https://pubmed.ncbi.nlm.nih.gov/23474300/) ·
[doi:10.1016/j.visres.2013.02.007](https://doi.org/10.1016/j.visres.2013.02.007)
→ **How the task is measured:** prosaccade baseline block first, gap paradigm,
headline endpoints = correct anti-saccade **latency** + anti-saccade **error
rate**, exclude anticipatory/express saccades, separate corrected vs uncorrected
errors. The measurement spec the plan adapts for webcam.

## Papers (webcam feasibility)

**Classification of Alzheimer's from webcam-based gaze data (ACM 2023)**
[dl.acm.org/10.1145/3591126](https://dl.acm.org/doi/10.1145/3591126)
Deep learning on **webcam** (not lab eye-tracker) gaze data classifies AD.
→ Proves consumer-webcam gaze is sufficient signal — no infrared eye-tracker
needed. Direct precedent for a laptop-only oculomotor test.

**Fine-tuning pretrained models on gaze data for AD (ETRA 2024)**
[dl.acm.org/10.1145/3649902.3656360](https://dl.acm.org/doi/10.1145/3649902.3656360)
Transfer learning (e.g. gazeNet) improves AD detection from gaze.
→ Path to a model without collecting huge data from scratch.

**Web-based eye tracking — antisaccade as a case study (bioRxiv 2023)**
[biorxiv 2023.07.11.548447](https://www.biorxiv.org/content/10.1101/2023.07.11.548447v1.full)
Remote, browser-based antisaccade task is feasible for cognitive assessment.
→ Shows the *antisaccade* paradigm specifically works over the web/webcam — the
task to build first.

**Deep learning approach on eye-tracking for AD (Frontiers 2022)**
[PMC9500464](https://pmc.ncbi.nlm.nih.gov/articles/PMC9500464/)
DL on eye-movement data improves diagnostic performance (reported gains up to
~18% over baselines).
→ Quantifies the payoff of ML over raw metrics.

**AI-driven eye-tracking prediction model on mobile devices (2024)**
[PMC11671572](https://pmc.ncbi.nlm.nih.gov/articles/PMC11671572/)
Builds an AD prediction model from an eye-tracking task on ordinary mobile
device cameras.
→ Consumer-camera oculomotor screening is actively productized — validates
feasibility and UX.

## Why antisaccade specifically
Across studies, **antisaccade error rate** cleanly separates groups: healthy
adults err on ~20% of trials vs ~50–80% in AD, with elevated errors even in
early AD/MCI. Prosaccade/antisaccade **latency** is also prolonged.
→ Antisaccade error rate + saccade latency are the highest-value, simplest
oculomotor endpoints to compute.

## Repos / tools
- **MediaPipe Face Mesh / Iris** — 468 face + iris landmarks from webcam; the
  natural basis for gaze estimation in this project's existing MediaPipe stack.
- **WebGazer.js** — established browser webcam eye-tracking library; useful
  reference/algorithm even for a Python port.

## Takeaways for this project
1. Add an **antisaccade + prosaccade** test: dot appears left/right, patient
   looks toward (pro) or away (anti); compute **latency** and **error rate**.
   → **Done** (v1). `core/gaze/` + `screening_tests/oculomotor_test.py`.
2. Reuse the **MediaPipe** stack (Face Mesh/Iris) rather than adding hardware.
   → **Done** — Face Landmarker (478 landmarks incl. iris), iris-corner ratio.
3. Start with interpretable metrics (latency, error rate), add a DL classifier
   later; expect meaningful accuracy gains from ML. → interpretable metrics
   done; ML classifier is §10.5 below.

---

## 10. Future improvements (post-v1)

The v1 test resolves saccade **direction** robustly (→ error rate, the headline
biomarker) but is limited on **latency precision** and **signal richness** by a
consumer webcam. The improvements below are ordered roughly by leverage-to-
effort. Each names where it touches the current code.

### 10.1 Better gaze signal — highest leverage
The v1 proxy is a single scalar: mean iris-center x relative to the eye corners
(`core/gaze/tracker.py`). It is head-**translation** invariant but not head-
**rotation** invariant, and it throws away the vertical axis and per-eye
disagreement. Concrete upgrades:

- **Head-pose compensation.** MediaPipe Face Landmarker can emit
  `facial_transformation_matrixes` (6-DoF head pose) and `face_blendshapes`
  (incl. `eyeBlinkLeft/Right`, `eyeLookIn/Out/Up/Down`). Rotating the iris
  vector into a head-stabilised frame — or simply gating trials when yaw/pitch
  exceed a threshold — would cut the biggest current noise source (users turn
  their head instead of their eyes). The blink blendshapes are also a cleaner
  blink signal than the current lid-gap ratio.
- **Appearance-based gaze CNN.** Replace the geometric ratio with a learned
  estimator — **MPIIGaze** (Zhang et al. 2015/2017), **ETH-XGaze** (Zhang et
  al., ECCV 2020), or **L2CS-Net** (Abdelrahman et al. 2023) — which regress
  gaze yaw/pitch directly from the eye crop and are far more robust to lighting,
  glasses, and partial occlusion. These give a continuous 2-D gaze angle, not
  just left/right, opening up vertical saccades and pursuit (§10.3). Runs on CPU
  at webcam rates; ONNX-exportable to keep the stdlib-friendly deployment.
- **Per-eye modelling.** Keep the two eyes separate and use their agreement as a
  live confidence signal (disagreement → discard the sample), rather than
  averaging them into one ratio as v1 does.
- **Vertical axis.** Add up/down targets. The current design is horizontal-only
  (the axis a webcam estimates most reliably), but vertical saccades add
  discriminative power and are cheap once a 2-D estimator exists.

### 10.2 Sharper latency — beat the frame-rate ceiling
At 30 fps a frame is 33 ms; a saccade is 30–100 ms. v1 already (a) requests
60 fps + MJPG and (b) stamps the true render frame as t₀ and (c) reports
**Anti − Pro** so the fixed sensor/display offset cancels. Further gains:

- **Sub-frame onset estimation.** Instead of snapping onset to the first
  out-of-deadband frame, fit the deadband-crossing time by linear (or
  sigmoid) interpolation between the two straddling frames — recovers a
  fraction of a frame of resolution essentially for free in
  `core/gaze/detector.py`.
- **ROI / high-fps capture.** Many webcams hit 90–120 fps at reduced resolution
  or with a cropped ROI around the eyes. Detect the face once, then track a
  small eye ROI at high fps.
- **Hardware/driver timestamps.** Use the capture-layer frame timestamp
  (`CAP_PROP_POS_MSEC` / OS timestamp) rather than wall-clock `time.time()` at
  the moment of `read()`, to remove Python-side scheduling jitter from t₀.
- **Distributional latency (LATER model).** Rather than a single mean latency,
  fit the reciprobit (1/latency) distribution (Carpenter's LATER model) to
  separate a shift in decision rate from a change in threshold — and to cleanly
  identify the **express-saccade** population instead of the current hard 90 ms
  cutoff.

### 10.3 New task modes — reuse the engine
The `SaccadeTask` registry (`core/gaze/tasks.py`) and phase state machine were
built to extend the way `TapMode` does. Natural additions (plan §7 phase 5):

- **Smooth pursuit** — eyes track a sinusoidally moving target; count catch-up
  saccades and compute pursuit **gain** (eye velocity ÷ target velocity), which
  falls with impairment. Needs the continuous 2-D estimator from §10.1.
- **Fixation stability** — hold gaze on a static point; measure **BCEA**
  (bivariate contour ellipse area) and **square-wave jerks / saccadic
  intrusions**, which are elevated in AD and especially PSP.
  → **Done (v1)** — added as "Part 3 - Hold Still" (a 12 s central-fixation
  hold after the anti block). `core/gaze/fixation.py` computes **RMS jitter**
  (headline, calibrated horizontal units), **2-D BCEA** at P=0.68 over an iris
  cloud, and an **intrusion rate/min** (excursions beyond the fixation
  deadband). To get a second axis, `tracker.py` now emits an uncalibrated
  vertical iris proxy (`ratio_y`). Still open: BCEA in **degrees** (needs the
  viewing-distance work in §10.6) and a properly *calibrated* vertical axis
  (§10.1) — v1 BCEA is a relative measure, and jitter/intrusions are measured
  above the One-Euro smoothing floor, so they're for within-pipeline
  comparison, not absolute amplitudes.
- **Memory-guided saccades** — a target flashes, then after a delay the user
  saccades to the *remembered* location. Highly sensitive to executive/frontal
  dysfunction; a strong complement to the anti-saccade.
- **Gap vs overlap manipulation** — v1 uses a 200 ms gap. Running interleaved
  gap/overlap conditions quantifies the **gap effect**, an additional
  attention-disengagement readout.

### 10.4 Richer metrics
- **Express-saccade rate** as its own endpoint (see §10.2 LATER), not just an
  exclusion count.
- **Error-correction latency** — time from an anti-saccade error to the
  corrective saccade (v1 flags corrected/uncorrected but doesn't time the
  correction).
- **Main sequence** (peak-velocity vs amplitude, Bahill et al. 1975) — only if
  a high-fps path (§10.2) lands, since it needs velocity; otherwise it stays out
  of scope, as the plan honestly states.
- **Intra-run learning/fatigue slope** — does error rate drift across the 24
  anti trials? (parallels the tapping test's decrement metric).

### 10.5 ML classifier — interpretable metrics → learned features
The research above (ACM 2023, ETRA 2024, Frontiers 2022, PMC11671572) shows DL
on webcam gaze traces classifies AD with meaningful gains over hand-tuned
metrics. Path that fits this project:

1. **Persist the raw gaze trace** — v1 already saves per-trial position series
   in the session JSON (`raw.trials`), so the training corpus accrues from day
   one. Keep this schema stable.
2. **Event-level model first** — **gazeNet** (Zemblys et al. 2019) style
   sequence labelling of fixation/saccade/PSO to replace the hand-written
   detector, improving robustness before any diagnosis model.
3. **Transfer learning** for the classifier (ETRA 2024) rather than training
   from scratch on a small clinical cohort.
4. Keep the interpretable error-rate/latency readout as the primary output; the
   classifier is an *adjunct* score, per the project's "no fake precision" tone.

### 10.6 Validation, calibration & normative data
- **Concurrent validation** against a real eye-tracker (Tobii / EyeLink) on the
  same subjects — the decisive missing piece; report agreement (Bland–Altman)
  on error rate and latency.
- **Test–retest reliability** across sessions and lighting conditions.
- **Normative bands.** v1 bands are anchored to published healthy (~6%) and AD
  (~25%) error rates but are not a local norm; collect asymptomatic-adult data
  to calibrate (mirrors the tapping bands' honest "provisional" note).
- **Auto re-calibration / drift detection** — re-run or nudge calibration when
  the face-box or head pose drifts mid-session (plan §8 open decision).
- **Degrees of visual angle.** v1 sets target eccentricity as a fraction of
  frame width. Estimating viewing distance (from interocular distance in px, or
  the head-pose matrix) would let eccentricity be specified in **degrees**, so
  latency/error don't depend on screen size and seating distance.

### 10.7 Robustness & accessibility
- **Glasses & reflections** — the biggest real-world failure mode for iris
  tracking; the appearance-based models (§10.1) are the main mitigation, plus a
  calibration-time quality gate that warns the user.
- **Low light / exposure** — reuse the CLAHE path already in
  `preprocess_for_mediapipe`; add an explicit "too dark to track" gate before a
  scored run (the UI already has the toast pattern).
- **Task comprehension** — the anti-saccade rule is counter-intuitive for older
  users; v1 has practice trials with feedback, but adaptive extra practice (loop
  until N practice trials are correct) would reduce "didn't understand the task"
  from masquerading as high error rate.
- **Audio-guided variant** — a spoken "look away" cue paired with the visual
  target, for low-vision users (style guide already requires audio+visual
  parity).

### Priority ordering (suggested)
1. **§10.6 concurrent validation** — nothing else is trustworthy without it.
2. **§10.1 head-pose gating + blink blendshapes** — cheap, big noise reduction,
   no new model.
3. **§10.2 sub-frame onset + capture timestamps** — small code change, better
   latency.
4. **§10.1 appearance-based gaze CNN** — unlocks §10.3 pursuit/fixation and
   vertical saccades.
5. **§10.5 ML classifier** — once the raw-trace corpus is large enough.
