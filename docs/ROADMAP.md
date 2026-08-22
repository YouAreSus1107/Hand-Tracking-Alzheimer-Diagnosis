# Roadmap & Future Plans

_Last updated: 2026-07-23_

This document lays out where the project is going, grounded in what the
published literature has and hasn't achieved. It covers the planned
**wearable-device integration**, the planned **speech and cognitive tests**,
and how the existing webcam pipeline and the device cooperate. The evidence
behind every item is collected in the [`research/`](../research/) folder —
see the [Research-to-Feature Map](#8-research-to-feature-map) at the end.

> **Closest prior art — TAS Test.** The University of Tasmania's **TAS Test** is
> a 20-minute at-home webcam+keyboard+mic motor-cognitive-speech battery,
> CV-validated against wearable sensors, studied in 2,351 adults. It proves this
> project's core concept is real — and means the project's distinct contribution
> must be its **open-source, self-hostable** nature and the **wearable
> co-contraction "digital twin"** that measures an internal signal no camera can
> see. See [`research/README.md`](../research/README.md).

> **Status note:** the wearable device plan is folded into Sections 2–3 below.
> Remaining open items are concrete build details (per-user calibration,
> OpenSim model choice) rather than unknowns.
> The **Arduino firmware, serial protocol, build gates, and the full download
> checklist** are specified in
> [`GLOVE_FIRMWARE_PLAN.md`](GLOVE_FIRMWARE_PLAN.md).

---

## 1. Where This Sits in the Literature

The closest published work is the **TapTalk** validation study (Li et al.,
2024, *Alzheimer's & Dementia: Diagnosis, Assessment & Disease Monitoring*;
[PMC11496774](https://pmc.ncbi.nlm.nih.gov/articles/PMC11496774/)). It uses the
**same core idea as this project** — MediaPipe hand-keypoint detection on
consumer video to measure finger-tapping motor biomarkers — and validated it
against a Polhemus electromagnetic motion sensor (60 Hz) with strong agreement
(~90% of tapping-frequency estimates within ±1 Hz of the hardware reference).

**What is therefore already established** (don't re-invent):
- Webcam/MediaPipe finger tapping can recover tapping frequency, rhythm
  coefficient of variation, intra-individual variance, and speed decrement to
  within ~1 Hz of a hardware gold standard.
- These estimates are robust across ~20 different phone models and both
  iOS/Android.

**What the literature has NOT done — the open space this project can occupy:**

| Gap in the literature | How this project can address it |
|---|---|
| **No clinical population.** TapTalk tested only 31 healthy adults; no AD/PD patients. Nobody has shown these webcam metrics separate patients from controls. | Run the existing IIV + spiral tests on a clinical cohort; report sensitivity/specificity, not just device agreement. |
| **Spiral / visuomotor tracing not covered.** TapTalk is tapping + speech only. | `spiral_test.py` already measures path deviation, velocity CV, and normalized jerk — a motor domain TapTalk omits. |
| **This project's own pipeline is unvalidated.** No hardware reference has been compared against our MediaPipe output. | **This is the wearable's primary scientific role** (Section 2): serve as the on-body ground-truth/complementary sensor. |
| **No unsupervised, longitudinal home use.** All prior testing was supervised, fixed distance, controlled lighting. | Add per-session result persistence + a longitudinal view so repeated home sessions can be compared over time. |
| **Camera-only motor sensing.** No camera + inertial fusion for hand motor screening. | Fuse webcam landmarks with the wearable's inertial data (Section 3) — genuinely novel territory. |
| **No resting/postural tremor test.** Neither TapTalk nor this suite measures tremor at rest. | Add a tremor test; a wrist/finger IMU measures this far better than a camera (Section 4). |

---

## 2. The Wearable: Hand Digital Twin (co-contraction)

The planned wearable is not a simple inertial sensor — it is a **sensor glove + biomechanical model
("digital twin")** whose headline output is **agonist/antagonist
co-contraction**: opposing hand muscles firing against each other.

### 2.1 Why it is complementary, not redundant, to the camera
The device's central claim is that co-contraction is **invisible to a camera**:
it produces *no visible motion and near-zero net force*, so the hand can look
perfectly still on video while opposing muscles fight internally. The webcam
captures visible **kinematics and timing**; the glove-plus-model captures
internal **force and co-contraction** the camera cannot see. They measure
different physical layers.

> **The key fusion insight (from the design notes, §7.4):** the glove is *not* a
> double-check on the camera. When the two channels are combined, the most
> interesting signal may be exactly where they **disagree** — a hand that looks
> normal on camera but shows internal inefficiency (high co-contraction) in the
> twin. That divergence is a candidate biomarker no single modality produces.

### 2.2 Device stack (from the design notes)
| Layer | Detail |
|---|---|
| Sensors | 5× flex (joint angle), 6× FSR (fingertip/palm force), 1× MPU-6050 IMU (wrist orientation/tremor), optional MyoWare 2.0 EMG (forearm muscle activation) |
| MCU | **Arduino Nano 33 BLE** — reads sensors, filters, emits **one comma-separated line of 11+ values per timestep**; has built-in IMU + Bluetooth |
| Transport | USB serial (pyserial) or BLE |
| Host software | Python parse → calibrate raw ADC (0–1023) to newtons/degrees → **OpenSim** inverse dynamics + static optimization → tendon forces, joint torques, muscle activations, **co-contraction index** → 3D twin render (Open3D/PyVista) + CSV log |
| Performance | OpenSim reconstruction is heavy — expect a few fps or offline pre-computation, not instant |

---

## 3. Planned Camera + Wearable Cooperation

Target architecture (an additional lane alongside the current tools):

```
   Webcam ─► MediaPipe landmarks ──┐
                                   ├─► time-aligned session ─► fusion / divergence
   Glove ─► Arduino CSV ─► OpenSim ┘        (shared clock)      analysis + CSV log
            (11+ values)  (co-contraction)
```

### 3.1 Integration points in the existing code
- **Transport reuse.** `core/hand_tracking.py` already broadcasts landmarks
  over UDP (`127.0.0.1:5052`). Add a small **serial→localhost adapter** that
  reads the Arduino's comma-separated line via `pyserial`, calibrates it, and
  republishes onto the same localhost pattern so both channels land in one
  fusion consumer. (The device already plans a `pyserial` read step, so this
  reuses code both sides will write anyway.)
- **Shared timestamp.** The tests already stamp frames in milliseconds
  (`time.time() * 1000`) for MediaPipe VIDEO mode. The glove line has no
  on-device clock guarantee, so **host-stamp glove samples on arrival** and
  align both streams to the host monotonic clock; mark a shared **start signal**
  (e.g. a keypress that zeroes both) at session begin. The camera runs ~30 fps
  and OpenSim only a few fps, so resample/interpolate to a common timeline
  rather than assuming frame-for-frame pairing.
- **Launcher awareness.** `launcher.py`'s status panel checks Python, model,
  OpenCV, MediaPipe. Add a **glove-connected** indicator (serial port present +
  line parsing) and a pairing/calibration action.

### 3.2 Data model
- Persist each session as structured records (CSV/JSON) with **all channels**:
  camera landmarks, glove raw + calibrated values, OpenSim-derived
  co-contraction index, per-test metrics, session id, and timestamp. This is
  currently missing entirely (see PROJECT_OVERVIEW "Known Gaps") and is a
  prerequisite for fusion, divergence analysis, and longitudinal tracking. The
  glove pipeline *also* plans CSV logging (the design notes Step 12) — use **one
  shared schema** so both sides write compatible session files.

### 3.3 Shared test protocol
Both the design notes (§7.2) and the webcam suite converge on the **same two
motor tasks** — **spiral trace** and **alternating finger taps**. Run them
once, capturing camera + glove simultaneously, so a single session yields
visible kinematics *and* internal co-contraction for the same movement. This is
the natural first fusion experiment.

---

## 4. Speech Testing (laptop mic only — no hardware)

Speech is the strongest near-term addition: TapTalk pairs motor with speech, a
laptop already has a microphone, and speech carries both **motor-articulatory**
and **cognitive-linguistic** signals. Proposed `speech_tests/` module, in
build order:

1. **Diadochokinesis (DDK)** — "pa-ta-ka" and "pa-pa-pa" rapid repetition
   (matches TapTalk). Metrics: syllable rate, rhythm coefficient of variation,
   inter-syllable variability, speed decrement. This is the direct speech
   analog of the IIV tapping test and reuses the same "rate + variability +
   decrement" scoring shape. *Libraries: `librosa` (onset detection),
   `noisereduce`.*
2. **Sustained phonation** — hold "ahhh" steady for ~5 s. Metrics: jitter,
   shimmer, harmonics-to-noise ratio, and **vocal tremor frequency** (4–12 Hz),
   which parallels hand tremor. *Library: `praat-parselmouth`.*
3. **Verbal (semantic) fluency** — "name as many animals as you can in 60 s."
   One of the most validated cognitive-decline markers. Metrics: word count,
   semantic clustering, repetitions/errors. *Needs transcription:
   `openai-whisper` or `faster-whisper` (runs locally, no cloud), then NLP.*
4. **Connected speech / picture description** (e.g. Cookie Theft). Metrics:
   speech rate, pause count/duration, articulation rate, lexical richness,
   information-unit density. *Whisper + `spaCy`/NLTK.*

Cross-cutting work: cross-platform audio is **done** (`core/tapping/audio.py`
plays via `winsound` on Windows and `sounddevice` on macOS/Linux); still
needed is a shared mic **recording** helper for the speech tests.

---

## 5. Other Laptop-Only Tests Worth Considering

Advanced tests needing **only a webcam, microphone, keyboard/trackpad, and
screen** — no glove, no extra hardware. Grouped by the faculty they probe.

### 5.1 Motor (webcam)
- **Alternating hand pronation/supination** — rapid palm up/down; classic
  dysdiadochokinesia task, measurable from hand-orientation over time.
- **Finger opposition sequencing** — touch thumb to each fingertip in sequence;
  scores sequencing accuracy and speed (apraxia-sensitive), reusing existing
  landmarks.
- **Postural tremor (camera)** — hold hand out; estimate micro-oscillation
  frequency/amplitude from landmark jitter. *Caveat: 30 fps caps clean tremor
  detection near ~15 Hz — this is precisely where the glove IMU is superior, a
  good camera-vs-glove comparison.*

### 5.2 Oculomotor (webcam — high value, underused)
- **Saccades / antisaccade** — follow or look away from a jumping dot; saccade
  latency and antisaccade error rate are strong early-AD/executive markers.
  **Built** — design in [`OCULOMOTOR_TEST_PLAN.md`](OCULOMOTOR_TEST_PLAN.md),
  shipped as `screening_tests/oculomotor_test.py` + `core/gaze/` (pro/anti-saccade
  first release; anti-saccade error rate as headline metric). Pending: validation
  on live gaze data to tune deadband + latency offsets.
- **Smooth pursuit** — eyes track a moving target; catch-up saccades increase
  with impairment. *Library: MediaPipe Face Mesh / iris landmarks, or WebGazer.*

### 5.3 Cognitive–motor (keyboard, mouse/trackpad, screen)
- **Digital Trail Making Test (A/B)** — connect numbers, then alternating
  numbers/letters; executive function and set-shifting via mouse path + timing.
- **Keystroke dynamics** — timing variability during a short typing task
  (hold/flight times); Van Waes-style keystroke logging, cited in the project's
  analysis doc.
- **Choice reaction time** and **Stroop** (color–word inhibition) — processing
  speed and inhibitory control from key-press latencies.
- **Digital clock-drawing / intersecting-pentagons copy** — draw on a trackpad;
  CV-scored visuospatial + executive test (clock-drawing is a standard screen).
- **Dual-task** — run a motor test (tapping/spiral) while doing serial-7
  subtraction or counting backward, matching TapTalk's dual-task; dual-task cost
  is itself a sensitive marker.

### 5.4 Facial (webcam)
- **Hypomimia / facial expressivity** — reduced facial movement ("masked face")
  during speech or on cue; measurable from Face Mesh landmark dynamics.

**Suggested priority:** speech DDK (§4.1) and semantic fluency (§4.3) first
(highest validation-to-effort ratio, mic-only), then digital Trail Making and
saccade tasks. Each new test should emit results in the shared session schema
(§3.2) from day one.

---

## 6. Feature Roadmap (priority order)

1. **Session persistence** *(no hardware; unblocks everything else)* — shared
   CSV/JSON schema in `results/` with session id + timestamp, used by camera,
   glove, and speech tools alike. **Built** — tapping, spiral, and oculomotor
   all write per-session JSON + a shared `index.csv` via `core/session.py`.
2. **Cross-platform audio** — no longer Windows-locked; prerequisite for speech
   tools off-Windows. **Built** — `core/tapping/audio.py` plays via `winsound`
   on Windows (system-default device) and `sounddevice` (PortAudio) elsewhere.
3. **Longitudinal view** — launcher page charting a patient's metrics across
   sessions (the home-use gap in the literature). **Built (v1)** — see §6.1 for
   what shipped and the future features queued for it.
4. **Speech DDK test** — mic-only, mirrors IIV scoring; first non-motor domain.
5. **Glove serial ingest adapter** — `pyserial` read + calibration +
   host-timestamping onto the shared timeline.
6. **Camera↔glove divergence analysis** — capture spiral/tapping on both
   channels; report where visible kinematics and internal co-contraction
   diverge (the novel fusion signal, the design notes §7.4).
7. **Semantic fluency + connected-speech tests** — local Whisper + NLP.
8. **Oculomotor (saccade/pursuit) and digital Trail Making** tests.
9. **Clinical pilot** — the decisive step: run the suite on an AD/MCI cohort vs.
   controls and report discrimination, not just device/method agreement.

### 6.1 Analysis page — shipped, and future features

**Shipped (v1).** An **Analysis** tab in the launcher, backed by a read-only
`GET /api/sessions` endpoint (`launcher.py` reads the per-session JSON in
`results/`, strips the heavy per-frame `raw` arrays) and rendered client-side in
`launcher_web/app.js`. For each test it charts the headline metric across
sessions as an SVG line chart with provisional status bands, a session-to-session
delta (direction-aware — knows lower is better for CV%/error rate), supporting-
metric sparklines, summary tiles (session count / tests tracked / date range), a
per-test filter, and a **per-test-type toggle** (finger tapping: Big & Fast vs
Paced) that swaps the chart, readout, and supporting tiles. It follows
`docs/UI_STYLE_GUIDE.md` (status = colour + dot + word; provisional bands
labelled as such; hover tooltips per point).

**Future features**, grouped by theme. Each should keep the shared session schema
(§3.2) and the style guide as the contract.

*Presentation & interaction*
- **True time-axis.** Plot against real dates, not equal-spaced session index, so
  gaps between home sessions are visible; add an optional rolling mean / trend
  line and light smoothing (median filter) for noisy series.
- **Session drill-down.** Click a point to open that session's full detail — all
  metrics plus the stored `raw` signal (tap-distance or spiral path) as a
  sparkline — instead of only the CSV-level summary.
- **Multi-metric small multiples.** Show the supporting metrics as a synchronised
  small-multiple grid, not just the headline, so co-movement is visible.
- **Mode overlay.** Optionally overlay Big & Fast vs Paced (or left vs right hand)
  on one chart instead of toggling, for direct comparison.

*Clinical interpretation*
- **Personal baseline & change-from-baseline.** Fix a baseline from the first N
  sessions and plot each later session as change vs baseline; this is the
  home-use readout that matters more than any absolute value.
- **Reliable-change / normative bands.** Replace the provisional bands with
  test–retest-derived reliable-change thresholds and, once a cohort exists,
  normative percentile bands + a percentile rank (ties to the clinical pilot, #9).
- **Left/right asymmetry.** The schema already stores `hand`; surface an
  asymmetry index and per-side trends — asymmetry is itself an early marker.
- **Data-quality gating on the chart.** Surface the per-session quality gates
  (FPS, face-visible ratio, valid-trial count) and dim/flag low-quality sessions
  rather than plotting them as equals.

*Context & sharing*
- **Session annotations.** Let the user tag a session (tired, poor lighting, new
  glasses, medication change) so dips have context; render as chart markers.
- **Clinician export.** Print-friendly PDF / CSV export of the longitudinal view
  using the style guide's **light theme** for reports.

*Integration (depends on other roadmap items)*
- **Cross-test composite.** A normalised multi-domain index (hand motor +
  oculomotor + speech) over time, once those domains accumulate sessions.
- **Glove / fusion channel.** Once the wearable lands (§2–3, #5–6), add a
  co-contraction trend and a **camera↔glove divergence-over-time** view — the
  novel fusion signal (the design notes §7.4) plotted longitudinally.

---

## 7. Guiding Principle

The published work proves the *sensors and methods* are good enough; it does
**not** prove the *screening* works on real patients, and no prior work combines
webcam kinematics with a wearable co-contraction twin. This project's
differentiators are therefore:
**(a) multi-domain testing** (hand motor + speech + oculomotor + cognitive),
**(b) camera–glove fusion and divergence analysis** (visible motion vs. hidden
internal co-contraction), and
**(c) longitudinal, home-capable use** — each an explicit gap in the current
literature. As the design notes stress: the hardware and code are the
straightforward part; the real contribution is **validation** on real people
with ground-truth cognitive status.

---

## 8. Research-to-Feature Map

Every planned capability, the evidence that supports it, and where to read more.
Full notes and links live in [`research/`](../research/).

| Planned feature | Status | Key evidence | Research file |
|---|---|---|---|
| Finger-tapping (IIV) | **built** | TapTalk (±1 Hz vs sensor); TAS Test predicts cognition; tapping meta ~0.85/0.82 | [01](../research/01-webcam-hand-motor.md) |
| Spiral tracing | **built** | Digitized Archimedes spiral review (incl. MCI/AD); explainable spiral CNNs | [02](../research/02-drawing-spiral-clock.md) |
| Session persistence (shared schema) | **built** (tapping + spiral + oculomotor; longitudinal view shipped) | prerequisite for all fusion/longitudinal/clinical work | — |
| Cross-platform audio | **built** (winsound on Windows, `sounddevice` elsewhere) | enables speech tests off-Windows | — |
| Longitudinal view | **built (v1)** (future features in §6.1) | TAS Test at-home unsupervised feasibility | [01](../research/01-webcam-hand-motor.md) |
| Speech DDK (pa-ta-ka) | planned #4 | TapTalk speech; librosa multidimensional speech algorithm | [03](../research/03-speech.md) |
| Glove serial ingest + twin | planned #5 | post-stroke digital-twin template; OpenSim ARMs hand model; NeuroMotion | [06](../research/06-wearable-cocontraction.md) |
| Camera↔glove divergence | planned #6 | co-contraction invisible to camera (the design notes §7.4) | [06](../research/06-wearable-cocontraction.md) |
| Semantic fluency + connected speech | planned #7 | ADReSS benchmarks; ~2-min audio ≈ gold standard; local Whisper | [03](../research/03-speech.md) |
| Oculomotor (antisaccade) | **built** (live-gaze validation pending) | antisaccade error rate SMD 1.59 AD vs ctrl (Opwonya 2022); ~25% AD (Crawford 2005); Antoniades protocol | [04](../research/04-oculomotor-gaze.md), [plan](OCULOMOTOR_TEST_PLAN.md) |
| Keystroke dynamics | candidate | keystroke meta-analysis; neuroQWERTY; MCI vs MoCA-K | [05](../research/05-cognitive-motor.md) |
| Digital Trail-Making / clock drawing | candidate | interpretable dCDT; DCTclock; ViT clock scoring | [02](../research/02-drawing-spiral-clock.md), [05](../research/05-cognitive-motor.md) |
| Clinical pilot (AD/MCI vs control) | planned #9 | the decisive gap across *all* the literature | all |

**Datasets to prototype against before recruiting anyone:** ADReSS (speech),
HandPD-style spiral sets (drawing) — see
[07-datasets-and-tools.md](../research/07-datasets-and-tools.md).
