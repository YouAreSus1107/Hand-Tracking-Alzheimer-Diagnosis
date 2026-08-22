# Drawing Tests: Spiral, Clock, Wave

Maps to: `screening_tests/spiral_test.py`, planned digital clock-drawing test.

## Spiral drawing

**Digitized Archimedes Spiral Drawing Test — scoping review (Wang et al., 2025)**
[Movement Disorders Clinical Practice](https://movementdisorders.onlinelibrary.wiley.com/doi/10.1002/mdc3.70278)
Reviews clinical uses and measurement properties of the digitized spiral test
across MS, ataxia, dystonia, cerebellar disease, **MCI, and Alzheimer's**.
→ Confirms spiral tracing is an established, quantifiable test beyond Parkinson's
— including cognitive conditions. Validates `spiral_test.py`'s direction and
supplies the standard metric set to align to.

**Spiral + wave drawing with explainable CNN for PD (2024/2025)**
[Springer chapter](https://link.springer.com/chapter/10.1007/978-3-031-87330-0_6) ·
[PDF](https://pdfs.semanticscholar.org/e858/c7bf8c30fd773ac0d1c418a3fb205b1e2c1d.pdf)
Explainable deep learning classifies PD from spiral/wave drawings; saliency maps
show *which* drawing regions drive the decision.
→ A path beyond hand-crafted metrics (deviation, jerk, velocity CV): train an
explainable classifier on drawing images/trajectories. Explainability matters
for a clinical tool.

**Tapping + Archimedean spiral for tremor differential (trial, NCT06378619)**
[ClinicalTrials.gov](https://clinicaltrials.gov/study/NCT06378619)
Combines tapping and spiral with ML for differential diagnosis of tremor.
→ Precedent for *combining* this suite's tapping and spiral tests into one
multi-task classifier rather than scoring them separately.

## Clock drawing

**Interpretable ML for the digital Clock Drawing Test (Souillard-Mandar et al.)**
[arXiv:1606.07163](https://arxiv.org/abs/1606.07163)
Features from pen-stroke data + interpretable ML outperform traditional clinician
scoring while staying explainable.
→ Blueprint for a trackpad/stylus clock test: capture the *drawing process*
(timing, hesitations), not just the final image.

**DCTclock — automated AI clock analysis**
[Frontiers Digital Health 2021](https://www.frontiersin.org/journals/digital-health/articles/10.3389/fdgth.2021.750661/full)
Time-stamped drawing + ML, validated on 1,833 unimpaired/impaired individuals.
→ Shows the process-capture approach scales and validates; a commercial-grade
reference target.

**Vision transformer scores clock drawings as well as expert coders (2025)**
[Sci Reports](https://www.nature.com/articles/s41598-025-34064-6)
A ViT produces CDT scores matching expert humans.
→ If capturing pen strokes is hard, a photo of a hand-drawn clock + ViT is a
viable lower-friction alternative.

**Qualitative CDT scoring with U-Net/CNN + mobile sensors (2021)**
[Sensors, PMC8348723](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8348723/)
CNN/U-Net scoring from mobile sensor + image data.
→ Practical mobile/webcam-friendly pipeline for automatic scoring.

## Takeaways for this project
1. Keep the current smoothness metrics (deviation, jerk, velocity CV) — they're
   literature-standard — and add an **explainable-classifier** track later.
2. A **digital clock-drawing test** (trackpad drawing → process features → ML) is
   a well-supported, high-value addition; capture *timing/process*, not just the
   picture.
3. Consider a **combined tapping+spiral classifier** (per NCT06378619) once
   session persistence exists.
