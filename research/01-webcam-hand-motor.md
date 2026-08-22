# Webcam Finger-Tapping & Hand Movement

Maps to: `screening_tests/finger_tapping.py`, `core/hand_tracking.py`.
Revision plan: [`docs/FINGER_TAPPING_REVISION_PLAN.md`](../docs/FINGER_TAPPING_REVISION_PLAN.md) ·
UI spec: [`docs/UI_STYLE_GUIDE.md`](../docs/UI_STYLE_GUIDE.md).

## Papers

**TapTalk — smartphone motor+speech across 20 devices (Li et al., 2024)**
[PMC11496774](https://pmc.ncbi.nlm.nih.gov/articles/PMC11496774/)
MediaPipe hand-keypoint tapping on smartphone video, validated against Polhemus
electromagnetic sensors: ~90.3% of tapping-frequency estimates within ±1 Hz;
rhythm/variance/decrement measures 100% within ±1 Hz; no iPhone vs Android
difference. Only 31 *healthy* adults — no clinical population.
→ **Directly validates our approach.** Same metrics as the IIV test (rate,
rhythm CV, intra-individual variance, decrement). Confirms MediaPipe tapping is
sensor-grade. The open gap it names — clinical cohorts — is ours to fill.

**TAS Test webcam hand movements predict cognition (Li et al., 2024)**
[PMC10809289](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10809289/)
404 cognitively asymptomatic adults did 10-second webcam finger-tapping at home;
hand-motor features improved prediction of episodic memory, executive function,
and working memory. CV features validated against wearable sensors.
→ Shows unsupervised, at-home webcam tapping carries real cognitive signal in
*asymptomatic* people — the exact use case this suite targets.

**TAS Test clinical validation (Alty et al., 2023)**
[Alz & Dementia, doi:10.1002/alz.076403](https://alz-journals.onlinelibrary.wiley.com/doi/10.1002/alz.076403)
Automated hand-motor analysis discriminated subjective cognitive decline, MCI,
and dementia in a cognitive clinic (keyboard tapping; features = frequency,
rhythm, accuracy, dwell time).
→ Evidence that these features separate real patient groups, not just correlate
with test scores — the endpoint our planned clinical pilot should target.

**Reference-source for the IIV metric (Roalf et al., 2018)**
[J Neurol 265:1365–1375](https://pmc.ncbi.nlm.nih.gov/articles/PMC5992087/) · PMC5992087
Light-diode finger tapper in 302 subjects (AD 131, PD 63, MCI 46, HOA 62):
total taps ↓ and inter-tap interval ↑ in AD/MCI; **IIV of the inter-tap interval
elevated across neurodegenerative groups** and discriminates better than tap
count or ITI alone (PD highest).
→ **The primary source for this test's headline `cv_pct`/`iiv_ms` metric.**

**Finger Tapping Test for MCI risk (Suzumura et al., 2022)**
[PMC9716461](https://pmc.ncbi.nlm.nih.gov/articles/PMC9716461/) — *Hong Kong J
Occup Ther*. Magnetic finger-tap device, 173 MCI vs 173 matched controls: best
single discriminator was **alternate-hand tap count** (AUC **0.79**, sens 0.77,
spec 0.67, cut-off 30 taps); average tapping interval and SD-of-ITI also AUC
~0.77–0.79.
→ Justifies prioritizing *alternating/temporal* tapping metrics over amplitude.
(NB: the higher pooled sensitivity/specificity ≈ 0.85 / 0.82 and the 60-s
alternating-tap AUC 0.75–0.89 quoted elsewhere come from the **device reference
doc's** meta-analytic summary, *not* from this single study.)

**Smartphone self-testing of hand & speech — reliability/usability (2025)**
[GeroScience](https://link.springer.com/article/10.1007/s11357-025-02024-7)
Older adults can self-administer hand + speech motor tests reliably; references
MediaPipe pipelines.
→ Usability evidence for unsupervised home use; informs UX of the launcher.

## Metric → source provenance (verified 2026-07-23)

Where each biomarker computed in `core/tapping/metrics.py` comes from. All
citations below were checked against the primary sources this session.

| Metric (`metrics.py`) | What it is | Primary verified source |
|---|---|---|
| `frequency_hz` | taps per second | **TapTalk** (Li 2024, PMC11496774) — MediaPipe tapping frequency validated vs Polhemus, 90.3% within ±1 Hz |
| `mean_iti_ms` | mean inter-tap interval | **Roalf 2018** (PMC5992087) — ITI lengthened in AD/MCI |
| **`iiv_ms` / `cv_pct`** | SD (and CV%) of inter-tap interval — **headline** | **Roalf 2018** (IIV elevated across neurodegenerative groups); **TapTalk** (rhythm-CV/IIV 100% within ±1 Hz) |
| `amplitude_mean` / `amplitude_cv_pct` | valley-to-peak excursion & its variability | **Suzumura** (2016/18/21) — distance/amplitude regularity on magnetic tap devices |
| `decrement_pct_per_s` | slope of tap rate over the trial | **TapTalk** "Big & Fast" speed decrement; Suzumura agility decline |
| `sync_sd_ms` (paced) | SD of tap-to-beat latency | Rhythm-consistency paradigm; **project-specific — no cited normative source** (honestly flagged in `modes.py` `thresholds_note`) |

**Scoring bands provenance:** unlike the oculomotor test (bands anchored to
published error rates), the tapping `cv_typical`/`cv_monitor` bands are **not yet
literature-anchored** — `modes.py` states this outright ("Provisional bands - to
be calibrated against normative data"). This is the honest status; a future task
is to derive bands from a normative cohort (e.g. the Brazilian FTT DB below).

## Repos / tools

- **MediaPipe Hand Landmarker** (already used) — the validated keypoint backbone
  behind TapTalk and similar pipelines.
- **One-Euro filter** (already used in `hand_utils.py`) — standard jitter filter
  for interactive landmark streams; matches the smoothing these systems apply.

## Takeaways for this project
1. Add **alternating/sequential tapping** paradigms (TapTalk "sequence",
   TAS Test), not just single-finger tapping.
2. Report metrics in the **rate / rhythm-CV / IIV / decrement** vocabulary the
   literature uses, so results are comparable.
3. The decisive unmet need everywhere is a **clinical cohort with ground-truth
   cognitive status** — design persistence and export with that study in mind.

---

## Open-source status of the key papers (checked 2026-07-20)

| Work | Code public? | Data public? | Notes |
|---|---|---|---|
| **TapTalk** (Li 2024) | **No** | No — "available on request … not publicly available due to privacy/ethical restrictions" | No GitHub, no code-availability link. |
| **TAS Test** (UTAS) | **No** | No | Closed research platform; CV algorithm not released. |
| **ST-A2J** ([ZhilinGuo](https://github.com/ZhilinGuo/ST-A2J)) | Partial | — | Vision-based PD finger-tapping via 3D hand-pose; sparse repo (1★, no visible license, runnability unclear). Reference only. |
| **Brazilian Finger-Tapping DB** ([Sci Data 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11582313/)) | **Yes** (Python) | **Yes**, CC BY 4.0 (Figshare `10.6084/m9.figshare.26940823.v1`) | 176 healthy adults, **touchscreen** tap timing/coords — *not webcam video*, no ground-truth validation. Useful for tap-timing analysis code + reference distributions. |

**Conclusion:** no drop-in open-source *clinical webcam* tapping program exists.
This project is filling a genuine gap — reinforcing the open-source
differentiator. Reuse the Brazilian DB's tap-timing routines and the ST-A2J
approach as references, not dependencies.

## How TapTalk's tapping test differs from ours

Same **core measurement** (Euclidean index-tip↔thumb-tip distance per frame →
displacement curve → frequency; 60 cm, 30 fps). Differences:

| Aspect | TapTalk | This project (`finger_tapping.py`) |
|---|---|---|
| Paradigm | "**as big and fast as possible**" (max speed) | **metronome-paced** (rhythm/timing) |
| Primary metric | tapping frequency + decrement | **IIV** (inter-tap variability) + **beat-sync** consistency |
| Task variants | 3: Big-and-Fast, **Dual-Task** (tap + count backward), **Sequence** (index→middle→ring) | 1: single index–thumb |
| Tap detection | frequency from displacement curve (peak/spectral) | fixed distance **threshold + debounce** |
| Smoothing | not described | **One-Euro filter + CLAHE** preprocessing |
| Validation | vs Polhemus sensor | none yet |

**Refinements suggested for our test:** (1) add a **max-speed "big and fast"**
task and a **dual-task** and **sequence** variant — cheap wins that match a
validated protocol; (2) consider **peak-detection on the distance curve**
instead of a pure threshold (more robust to amplitude/scale); (3) our
metronome/IIV paradigm and filtering are **strengths TapTalk lacks** — keep
them.

## Cheap ways to validate our measurement (instead of a ~$3k Polhemus)

Ranked by timing accuracy vs. cost/ease. All ship from Amazon/SparkFun/AliExpress
and are beginner-friendly (Arduino + a few parts).

| Method | ~Cost | Validates | Ease | Notes |
|---|---|---|---|---|
| **Metronome ground truth** | free | frequency accuracy | trivial | Tap in time with known BPM; compare measured Hz. First sanity check. |
| **Electrical contact switch** (conductive/copper tape on thumb+finger → Arduino digital pin) | ~$5–15 | **exact tap timing** (sub-ms) → true inter-tap intervals for IIV | easy | Best timing reference for the money; each tap closes a circuit. |
| **MPU-6050 IMU on fingernail** | ~$4 | timing + frequency (≥500 Hz) | easy | Same sensor as the planned glove — doubles as glove-integration groundwork. |
| **High-speed phone video (120/240 fps slow-mo)** | free | temporal resolution reference | easy | Count taps frame-by-frame at 4–8× the webcam's 30 fps. |
| **Audio onset** (tap near mic / on a surface) | free | tap timing | easy | Onset detection gives timing with no hardware. |
| **FSR force sensor** (glove BOM) | ~$7 | force + timing | easy | Slightly noisier timing than a contact switch. |

**Recommended starter kit (~$25–50):** Arduino Nano/Uno (or clone) + copper foil
tape **or** an MPU-6050, breadboard + jumper wires, USB cable. Operation: attach
tape/IMU, run a small sketch that prints tap timestamps over serial, tap while
the webcam test runs, and compare the two timing streams. Pick the **MPU-6050**
if you want the same part to feed the future glove; pick the **contact switch**
for the cleanest pure-timing ground truth.
