# Speech Tests (DDK + Sustained Phonation) — Design & Build Plan

_Last updated: 2026-07-23. **Status: planned** — not yet built._
_Research basis: [`research/03-speech.md`](../research/03-speech.md)._
_All UI work in this plan follows [`UI_STYLE_GUIDE.md`](UI_STYLE_GUIDE.md)._

This is the design document for the suite's first **speech screening tests** —
two microphone-only, acoustic tasks: **diadochokinesis (DDK, "pa-ta-ka")** and
**sustained phonation ("ahhh")**. It has three parts: **(1)** the research basis
and why these two tasks earn a place first, **(2)** the **metrics and measurement
system** (exactly what is computed and how, honest about consumer-mic limits),
and **(3)** the build plan — task layout, architecture, UI, and a phased roadmap.
It mirrors the structure and engine/UI split proven in
[`OCULOMOTOR_TEST_PLAN.md`](OCULOMOTOR_TEST_PLAN.md) and
[`FINGER_TAPPING_REVISION_PLAN.md`](FINGER_TAPPING_REVISION_PLAN.md).

First release scope (decided): **DDK + sustained phonation only.** Both are
**acoustic-only** — no speech-to-text — so they ship before the transcription-
dependent language tasks. Semantic (verbal) fluency and connected-speech / picture
description need local Whisper + NLP and are deferred to a **separate later plan**
(see §7). This keeps the first release light: `librosa` + `parselmouth`, no ASR
model download.

---

## 1. Purpose & Research Basis

**Why speech.** Speech is the strongest near-term addition to the suite: a laptop
already has a microphone, and the voice carries **two** signals at once —
**motor-articulatory** (how fast and how steadily the speech muscles move) and
**cognitive-linguistic** (word access, sentence planning). The closest prior art,
the **TAS Test** and **TapTalk**, both deliberately pair motor tests with speech
([ROADMAP §4](ROADMAP.md), [research/README.md](../research/README.md)). Adding
speech at zero hardware cost is squarely on the project's laptop-only thesis.

**Why these two tasks first.** DDK and sustained phonation are the only two
speech tasks that need **no transcription**, so they are the cheapest to build
and validate. DDK is also the **direct speech analog of the IIV finger-tapping
test** — rapid repetition scored on rate + rhythm variability + speed decrement —
so it reuses a scoring shape the suite has already proven (`core/tapping/`).

### 1.1 Clinical & measurement evidence (supports building the tests)

**Cohen et al. (2025) — meta-analysis of temporal speech measures.** *"Speech
pause and speech rate for evaluating Alzheimer's and mild cognitive impairment: a
meta-analysis,"* **Journal of the International Neuropsychological Society**
32(1). [Cambridge Core](https://www.cambridge.org/core/journals/journal-of-the-international-neuropsychological-society/article/abs/speech-pause-and-speech-rate-for-evaluating-alzheimers-and-mild-cognitive-impairment-a-metaanalysis/26ADD29A52BE763FF3A87C6F6F8EFEDB).
Pooling 13 studies, **speech rate** separated AD from controls with a **moderate**
effect (**SMD ≈ 0.66**; MCI ≈ 0.27) and **pausing** with a **large** effect
(**SMD ≈ 1.20**; MCI ≈ 0.62). → Establishes that *temporal* speech measures carry
real AD signal. Note the honest caveat: pauses are the strongest, but pausing is
a **connected-speech** measure (deferred to the ASR tasks); **rate and timing
regularity** are what DDK captures directly.

**Li et al. (2024) — TapTalk validation (the measurement precedent).** *"Smartphone
automated motor and speech analysis … validation of TapTalk across 20 different
devices,"* **Alzheimer's & Dementia: DADM.**
[PMC11496774](https://pmc.ncbi.nlm.nih.gov/articles/PMC11496774/) ·
[doi:10.1002/dad2.70025](https://doi.org/10.1002/dad2.70025).
TapTalk pairs finger tapping with speech; audio syllable-rate estimates from an
ordinary phone microphone landed **within ±1 Hz of the gold-standard measure in
98.3%** of recordings, across 20 phone models. → **Validates the measurement
system**: recovering DDK syllable rate/rhythm from a Python audio pipeline is the
same approach TapTalk proved on consumer hardware. This is the direct precedent
for building the DDK test, and it uses the **same core idea** (MediaPipe + audio)
as this project's tapping test.

**Automated DDK scoring validity (JSLHR 2022).** *"Validating Automatic
Diadochokinesis Analysis Methods Across Dysarthria Severity …,"* **Journal of
Speech, Language, and Hearing Research.**
[PMC9150739](https://pmc.ncbi.nlm.nih.gov/articles/PMC9150739/).
**Amplitude-based** (absolute-energy) syllable-onset detection correlated with
manual DDK scoring at **τb ≈ 0.7–0.84** for DDK rate; rhythm was quantified with
the **normalized pairwise variability index (nPVI)** of syllable and inter-syllable
durations. → Justifies both the **onset-detection method** (energy envelope) and
the **nPVI rhythm metric** this test adopts.

**Voice acoustics in mild AD (2025).** *"The effect of mild-stage Alzheimer's
disease on the acoustic parameters of voice,"* **Egyptian Journal of
Otolaryngology.** [doi:10.1186/s43163-025-00765-y](https://doi.org/10.1186/s43163-025-00765-y).
**Jitter and shimmer were significantly higher** in mild-AD voices than in
cognitively-normal controls. → Supports the sustained-phonation endpoints. State
plainly: the AD **voice-acoustic** literature is **thinner and more mixed** than
the pause/rate evidence, so phonation bands are labelled provisional (§6).

**Vocal tremor.** A sustained vowel exposes involuntary **2–10 Hz** quasi-
sinusoidal modulation of F0/amplitude (vocal tremor), which parallels hand tremor
— a cheap additional endpoint from the same recording.

### 1.2 Honesty note (must appear in the doc and the results screen)

The **strongest** AD speech markers — connected-speech **pausing** (SMD ≈ 1.2)
and **semantic fluency** — require transcription and are **out of this release's
scope**. DDK and sustained phonation are the **motor-articulatory foundation** of
the speech domain; the cognitive-linguistic markers follow in a later plan (§7).
This test is **screening, not diagnosis.**

---

## 2. Task Design

Two tasks, one shared speech engine (parallels the `TapMode` registry in
`core/tapping/modes.py` and the `SaccadeTask` registry in `core/gaze/tasks.py`):

| Task | Prompt | Duration | Role | Headline metric |
|---|---|---|---|---|
| **DDK** | Repeat "**pa-ta-ka**" (and/or "pa-pa-pa") as fast **and** as steady as you can. | ~6–8 s | Articulatory speed + timing; the speech analog of IIV tapping. | **Syllable-rate CV%** (rhythm) |
| **Sustained phonation** | Take a breath and hold "**ahhh**" steady at a comfortable pitch. | ~5 s | Voice quality + stability; exposes tremor. | **Jitter %** (+ shimmer / HNR / tremor) |

### 2.1 Trial structure

```
 mic check + ambient-noise gate     countdown ring     record window      analyse
 (level meter, coaching)      ──►    3 · 2 · 1 · go ──► "go" tone .. "stop" ──► score
                                                        tone (fixed len)
```

- **DDK:** trim the first ~1 s of ramp-up before scoring (same rationale as the
  tapping test's `trim_taps`), so warm-up syllables don't inflate variability.
- **Phonation:** score the steady **middle segment** of the vowel, discarding the
  onset and release, where jitter/shimmer are unreliable.
- The **mic check** runs first — it is the microphone analog of the oculomotor
  3-point calibration and the tapping screen-calibration gate.

---

## 3. Metrics & Measurement System

### 3.1 DDK — from waveform to syllables

Record mono PCM at **44.1 kHz**. Detect syllable onsets from the amplitude
envelope with `librosa.onset.onset_detect` (energy / amplitude-based — the method
validated at τb ≈ 0.7–0.84 vs manual scoring, JSLHR 2022). Inter-syllable
intervals then feed the same **"rate + variability + decrement"** triple the
tapping test computes:

| Metric | Definition | Notes / literature anchor |
|---|---|---|
| **Syllable rate (syll/s)** | valid onsets ÷ scored window | measurement validated to **±1 Hz** on consumer mics (TapTalk, Li 2024) |
| **Rhythm CV %** | SD ÷ mean of inter-syllable intervals · 100 | **headline** — scale-invariant, mirrors tapping `cv_pct` |
| **nPVI** | normalized pairwise variability index of interval durations | the standard DDK rhythm index (JSLHR 2022) |
| **Speed decrement %/s** | least-squares slope of instantaneous rate over the trial | fatigue; mirrors tapping `decrement_pct_per_s` |
| valid-syllable count, SNR | data-quality gates | drive scoreable/unscorable |

**Reuse, don't re-invent.** The scored shape is identical to
`core/tapping/metrics.py` `compute_metrics` (rate → CV → decrement, plus the
honest `scoreable = False` + human-readable `reason` when a score can't be
formed). Port the pure helpers `_sd`, `_slope`, and `band` rather than rewriting
them.

### 3.2 Sustained phonation — Praat acoustics via `parselmouth`

`praat-parselmouth` runs Praat's algorithms on the steady middle segment:

| Metric | Definition | Notes / literature anchor |
|---|---|---|
| **Jitter (local) %** | cycle-to-cycle F0 perturbation | **headline** — significantly ↑ in mild AD (Egyptian JO 2025) |
| Shimmer (local) % | cycle-to-cycle amplitude perturbation | ↑ in mild AD |
| HNR (dB) | harmonics-to-noise ratio | voice quality / breathiness |
| Vocal-tremor freq (Hz) | dominant **2–10 Hz** modulation of the F0 / amplitude contour (FFT of the contour) | parallels hand tremor |
| F0 mean / SD, phonation duration | supporting | pitch stability, maximum phonation time |

### 3.3 Measurement honesty (state plainly)

- **Consumer mics are sufficient** for these acoustics — jitter, shimmer, and
  syllable rate need no special hardware; TapTalk proved rate recovery on ordinary
  phones. The real limits are **ambient noise** and **clipping / automatic gain
  control**, both mitigated by the level + noise gate (§5) and an SNR check.
- **DDK-specific AD effect sizes** are less established than in Parkinson's / ALS
  motor speech. DDK earns its place here as the **articulatory-timing analog of
  tapping**, with AD support coming through the general **speech-rate / timing**
  evidence (Cohen 2025), not a DDK-specific AD trial.
- **Phonation acoustics** have a **thinner** AD evidence base than the pause /
  fluency literature — its bands are explicitly provisional (§6).

Every metric is persisted; the results card surfaces the headline plus a compact
table, each with a plain-language line (style-guide tone).

---

## 4. Architecture

Reuse the `finger_tapping.py` / `oculomotor_test.py` engine/UI split — **pure
logic in a `core/` package, run-loop + rendering in the screening script.**

**New files (this feature):**

| File | Role | Parallels |
|---|---|---|
| `core/speech/recorder.py` | **Shared mic capture + level/noise helper** via `sounddevice` — the recording helper the roadmap flags as still-missing. Streams input level for the meter; returns the recorded buffer. | `core/camera.py` (source select/open) |
| `core/speech/onsets.py` | waveform → syllable-onset times (`librosa`), pure. | `core/tapping/detector.py` |
| `core/speech/metrics.py` | onsets → DDK metrics; vowel → phonation metrics. Pure, unit-testable. | `core/tapping/metrics.py` |
| `core/speech/tasks.py` | `SpeechTask` registry (`ddk`, `phonation`) — prompts, durations, scoring bands. | `core/tapping/modes.py` `TapMode` |
| `screening_tests/ddk_test.py` | run loop + rendering only (state machine + `App`). | `screening_tests/finger_tapping.py` |
| `screening_tests/phonation_test.py` | run loop + rendering only. | same |
| `screening_tests/tests/test_speech.py` | pure-metric unit tests vs synthetic audio. | `screening_tests/tests/test_gaze.py` |

**Reused as-is:**
- `core/ui/` — `Canvas`, components, `theme`, `anim` for **every** screen.
- `core/session.py` — `save_session(test="ddk"/"phonation", mode=…, hand=None, …)`.
  Extend `_INDEX_FIELDS` with speech columns (`syllable_rate`, `rhythm_cv_pct`,
  `npvi`, `ddk_decrement_pct_per_s`, `jitter_pct`, `shimmer_pct`, `hnr_db`,
  `tremor_hz`); the one-time `index.csv` header migration (`_migrate_index`)
  already absorbs added columns, and the full metrics dict lands in the per-session
  JSON regardless.
- `core/tapping/audio.py` — `AudioWorker` + `build_tone` for the go / stop cue
  tones (the same worker the tapping metronome uses).
- `core/tapping/metrics.py` — port `_sd` / `_slope` / `band` for DDK scoring.
- `launcher.py` — add `TOOLS["ddk"]` and `TOOLS["phonation"]` entries, dashboard
  cards + detail pages, and a `status_payload` check for `librosa` / `parselmouth`
  import + a microphone being present (mirrors the existing OpenCV/MediaPipe/model
  checks).

**Not used:** `core/camera.py` and MediaPipe — these tests have no camera lane.

---

## 5. UI Screens

State machine adapted from the tapping / oculomotor tests, rendered entirely
through `core/ui` per `UI_STYLE_GUIDE.md`:
**IDLE → INSTRUCTION → MIC CHECK → COUNTDOWN → RECORDING → COMPLETE.**

- **Idle / start:** calm hero card, one-line purpose, single primary CTA, medical-
  disclaimer ribbon.
- **Instruction:** short animated schematic of the task ("pa-ta-ka" rhythm marks,
  or a steady "ahhh" waveform) over large accessible type — not a wall of text.
- **Mic check:** a live **input-level meter** with an **ambient-noise gate** and a
  coaching toast ("too quiet — move closer" / "too loud — clipping" / "background
  noise detected"). The microphone analog of calibration; it sets the SNR floor.
- **Countdown:** style-guide eased ring + scale-pop number, then a **"go" tone**.
- **Recording:** a live **waveform / level meter** and a countdown ring; a "stop"
  tone ends the fixed window. **The live waveform is essential signal, not
  decoration**, so it is **exempt from `REDUCED_MOTION`** (which still governs UI
  flourishes like ring pulses) — the same exemption the oculomotor jumping dot has.
- **Complete:** results card — big headline (DDK **rhythm CV%** or phonation
  **jitter %**), a **color + icon** status badge (never color alone), a compact
  metric table, the provisional reference bands, the screening-length note, and
  the saved path. Values count up (style-guide motion).

---

## 6. Scoring Bands & Honesty

Provisional, **non-diagnostic** bands for each headline metric — DDK **rhythm
CV%** and phonation **jitter %** — each carried on the `SpeechTask` (as the
tapping modes carry `cv_typical` / `cv_monitor` + a `thresholds_note`). Exact
cut-points are set at build time from the cited literature and refined against
local normative data. The results screen states: **screening, not diagnosis**;
short-form (shorter than clinical protocols); performance depends on the
microphone, room noise, and effort. Phonation bands carry an extra "thinner
evidence base" note (§3.3). All per the style guide's tone and accessibility
rules (min type sizes for the 50–89 target group, WCAG-AA contrast,
icon + label + color status).

---

## 7. Phased Roadmap

1. **Shared mic recorder + gate** (`core/speech/recorder.py`): `sounddevice`
   capture, live level stream, ambient-noise / SNR gate, mic-source select. The
   reusable substrate all speech tests need.
2. **DDK:** onset detection (`core/speech/onsets.py`) + metrics
   (`core/speech/metrics.py`), pure and unit-tested against **synthetic syllable
   trains** (known rate → known CV), mirroring `test_gaze.py`; then the run loop
   (`screening_tests/ddk_test.py`) + full UI flow. Headline **rhythm CV%**.
3. **Sustained phonation:** `parselmouth` jitter / shimmer / HNR / tremor in
   `core/speech/metrics.py` + `screening_tests/phonation_test.py` + UI. Headline
   **jitter %**.
4. **Persistence + launcher:** `save_session(test="ddk"/"phonation", …)`,
   `_INDEX_FIELDS` extended, `TOOLS` entries, dashboard cards + detail pages, and
   `librosa` / `parselmouth` / mic status checks.
5. **(Later — separate plan.)** Semantic (verbal) fluency and connected-speech /
   picture description via **local Whisper** (`faster-whisper`) + NLP (`spaCy`).
   These carry the strongest AD signal (pausing SMD ≈ 1.2; semantic fluency) but
   need transcription, so they are a distinct release with their own plan.

**Not yet built.** This document is the design; no code exists yet. New runtime
dependencies to add when building: **`librosa`**, **`praat-parselmouth`**,
**`soundfile`** (append to `requirements.txt` and `install.py`'s dependency list);
`sounddevice` and `numpy` are already present.

---

## 8. Open Decisions

- **DDK utterance:** "**pa-ta-ka**" (trisyllabic — articulatory *sequencing*) vs
  "**pa-pa-pa**" (monosyllabic — pure *rate*). Ship one, or both as selectable
  `SpeechTask` modes?
- **Recording length:** fixed windows (DDK ~6–8 s, phonation ~5 s) vs user-stopped.
- **Phonation headline:** **jitter** alone, or a small composite dysphonia score
  (jitter + shimmer + HNR)?
- **DDK scoring reuse:** call `core/tapping/metrics.py` `compute_metrics` directly
  with a syllable-interval series, or a thin speech-specific fork that adds nPVI?
- **Noise gating:** the SNR floor threshold, and whether to **hard-block** a scored
  run below it (mirroring the tapping test's face/hand-visibility gate) or only warn.
