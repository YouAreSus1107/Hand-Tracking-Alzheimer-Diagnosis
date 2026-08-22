# Clinical Validation Data — What Exists, What It Proves

Maps to: Roadmap **#9 (clinical pilot)** and the "unvalidated pipeline" gap in
[ROADMAP §1](../docs/ROADMAP.md). Companion to the general dataset index in
[07-datasets-and-tools.md](07-datasets-and-tools.md); this file is specifically
about **validating that our metrics correctly label clinical data**.

_Compiled 2026-07-23. Access terms and figures verified against each source's
data-availability statement on that date — re-check before relying on them, as
mirrors and licenses change._

## The core distinction (read this first)

"Validate the metric system" is two separate claims, and each needs different data:

1. **Method agreement** — do *our* MediaPipe-derived numbers match a trusted
   reference (hardware sensor or expert rating) on the **same input**? Requires
   raw video/signal we can push through our own pipeline.
2. **Discrimination** — do the metrics separate patients from controls in the
   **expected direction and magnitude**? Requires extracted metrics + clinical
   labels, and can validate our **status thresholds / bands** even without raw
   video we can re-process.

Almost none of the public data lets us do (1) end-to-end on *clinical* video —
that is precisely what roadmap #9 (a supervised cohort) exists to supply. But
several sources let us do (2) now, plus range sanity-checks.

**Cross-cutting caveat — PD, not AD.** Nearly all labeled public data is
**Parkinson's disease**, not Alzheimer's/MCI. PD is a sound *pipeline*-validation
proxy (identical kinematic metrics, hardware-validated in the literature — see
[01](01-webcam-hand-motor.md)), but any **cognitive-decline discrimination**
claim stays unproven until we run a real AD/MCI cohort. Do not let PD agreement
be reported as AD screening validity.

---

## 1. Finger tapping — strongest match ✅ (actionable now)

**PARK / ParkTest — webcam finger tapping with expert MDS-UPDRS (ROC-HCI, Univ. of Rochester)**
[npj Digital Medicine 2023, PMC10444879](https://pmc.ncbi.nlm.nih.gov/articles/PMC10444879/) ·
tool: [parktest.net](https://parktest.net) ·
data+code: [github.com/ROC-HCI/finger-tapping-severity](https://github.com/ROC-HCI/finger-tapping-severity)
Same modality as our test: **self-recorded webcam** finger tapping, both hands,
rated by 3 neurologists on the **MDS-UPDRS 0–4** scale (inter-rater ICC 0.88).
250 participants (172 PD / 78 control); 489 analyzed videos (244 L / 245 R;
severity distribution ≈ 108/181/141/54/5 for grades 0–4).
- **Raw videos are HIPAA-restricted / not redistributable.** But the **extracted
  per-video features + severity labels + processing/model code are public** on
  the GitHub repo above.
→ **Our best near-term validation target.** We cannot run MediaPipe on their
frames, but we *can* take their per-video features (rate, amplitude decrement,
rhythm variability) against expert severity and confirm our **CV%/decrement
metrics move in the right direction with comparable magnitudes** — a direct test
of our labeling (validation mode 2). See "Suggested first experiment" below.

**PDMotorDB** — [github.com/pddata/PDMotorDB](https://github.com/pddata/PDMotorDB)
368-patient finger-tapping video set. Academic use only; requires a signed
license agreement. → Larger cohort for method-agreement work *if* a DUA is
acceptable and raw video is needed.

**Large granular finger-tapping video set (4,073 videos)** —
[npj Parkinson's 2026](https://www.nature.com/articles/s41531-026-01307-w) /
[arXiv 2506.18925](https://arxiv.org/pdf/2506.18925). MDS-UPDRS-scored,
interpretable per-tap features. → Check its data-availability statement; if
released, the biggest labeled tapping corpus found.

**mPower** — largest open mobile PD study (8,320 participants), incl. a tapping
module. → **Touchscreen tap *timing*, not video** — validates rhythm/CV/decrement
*scoring* only, never landmark extraction. Useful, bounded.

---

## 2. Spiral — usable, but a real modality mismatch ⚠️

All widely-available public spiral sets are **pen-on-paper finished drawings**
(2D ink images, PD-labeled), which is **not** what our test produces.

- **HandPD / NewHandPD** — 736 spiral+meander images, 72 healthy / 296 patient.
  [Official homepage (UNESP)](https://wwwp.fc.unesp.br/~papa/pub/datasets/Handpd/).
- **Kaggle "Parkinson's Drawings"** (Zham et al., Dandenong Neurology) —
  spiral+wave PNGs, 55 subjects (27 PD / 28 HC).
  [kaggle.com/kmader/parkinsons-drawings](https://www.kaggle.com/kmader/parkinsons-drawings).
- **Mendeley spiral images** —
  [data.mendeley.com/datasets/fd5wd6wmdj/1](https://data.mendeley.com/datasets/fd5wd6wmdj/1).

→ **Caveat, do not overclaim.** `spiral_test.py` scores an **air-traced 3D
kinematic path** (velocity CV%, normalized jerk, active ratio) with a real time
axis. These datasets are static finished images with **no temporal signal**, so
they **cannot feed our pipeline** and cannot validate any velocity/jerk metric.
They only sanity-check *path-deviation* scoring conceptually. The honest
assessment: spiral is **under-served by public data**. The better analog — if a
DUA-accessible one can be found — is a **digitizing-tablet** spiral set with
x/y/t(/pressure), because it carries the temporal dynamics our metrics depend on.

---

## 3. Oculomotor — hardest to validate against 🔴

Clinically-labeled saccade/antisaccade data exists, but almost all uses
**infrared eye trackers**, not webcam iris landmarks — a raw-signal mismatch.

- **OpenNeuro** — ds000120 (visually-guided pro/antisaccade), ds000119
  (incentive antisaccade). Open, but research/healthy populations.
- **Zenodo trial-by-trial pro/antisaccade behavioral data** —
  [doi.org/10.5281/zenodo.6757621](https://doi.org/10.5281/zenodo.6757621), with
  reproducible analysis scripts.
- **ONDRI** (Ontario Neurodegenerative initiative, incl. PD) and the Oxford
  multi-disease antisaccade cohort (391 patients, 12 pro/anti parameters) —
  clinically labeled but **on request**, infrared.
  [Brain Communications 2023](https://academic.oup.com/braincomms/article/5/2/fcad049/7067778).
- **EM-COGLOAD** — [osf.io/zjtdq](https://osf.io/zjtdq) — actually **webcam**,
  but 75 *healthy* adults + cognitive load, no clinical labels.
- **Webcam-gaze AD classification proof-of-concept** —
  [ACM IMWUT / HCI 2023](https://dl.acm.org/doi/10.1145/3591126) — check its
  data-availability statement (closest webcam+AD combination found).

→ **What this buys us.** These sets cannot feed our MediaPipe gaze engine, but
their **numbers are the right sanity check** for our deadband + latency-offset
tuning: expected antisaccade latency ≈ 200–300 ms, a positive Anti−Pro latency
gap, and error rates ≈ 20% healthy vs 50–80% AD (see [04](04-oculomotor-gaze.md)).
Full webcam-pipeline oculomotor validation realistically requires our own
supervised collection.

---

## Suggested first experiment (finger tapping, this week)

1. Clone [ROC-HCI/finger-tapping-severity](https://github.com/ROC-HCI/finger-tapping-severity);
   load the released per-video features + MDS-UPDRS severity labels.
2. Map their feature names to our headline + supporting metrics (inter-tap-interval
   CV%, amplitude/speed decrement, rate). Where a metric isn't provided, note it.
3. Check **monotonicity and direction**: do our-style metrics worsen as expert
   severity 0→4 rises, with separation between control (0) and moderate (3)? Use
   Spearman correlation + group boxplots — this validates *labeling direction*,
   not a classifier.
4. Sanity-check our provisional **status bands**: does a "caution/impaired" CV%
   threshold land where severity ≥2 videos cluster? Adjust bands or flag as
   provisional accordingly.
5. Write results into a short `results/validation/` note. **Report as PD method
   agreement, explicitly not AD screening validity** (cross-cutting caveat above).

## Bottom line

| Test | Best public source | Validates | Blocker |
|---|---|---|---|
| Finger tapping | **PARK/ROC-HCI features + labels** | Thresholds & metric direction vs expert MDS-UPDRS | Raw video HIPAA-restricted; PD not AD |
| Spiral | HandPD / Kaggle (images) | Path-deviation concept only | No time axis → can't validate velocity/jerk or feed pipeline |
| Oculomotor | Zenodo / OpenNeuro / ONDRI | Metric *ranges* (latency, error rate) | Infrared not webcam; mostly non-clinical or on-request |

The end-to-end webcam validation the suite really needs still points back to
**roadmap #9** — a small supervised AD/MCI-vs-control cohort. The PARK feature
set is the one thing that de-risks the tapping metrics *before* then.
