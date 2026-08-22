# Open Datasets & Reusable Tools

For validating and training the tests without collecting a cohort from scratch.
Most clinical datasets require a data-use agreement — check terms before use.

> **For metric-validation specifically** (does our pipeline correctly label
> clinical data — roadmap #9), see the dedicated
> [08-clinical-validation-datasets.md](08-clinical-validation-datasets.md): it
> covers exact access terms, the method-agreement vs discrimination distinction,
> per-test modality caveats, and a concrete first experiment. The list below is
> the general index.

## Speech / language
- **DementiaBank / TalkBank (Pitt corpus)** —
  [dementia.talkbank.org](https://dementia.talkbank.org/) — the standard AD
  spontaneous-speech corpus (Cookie Theft descriptions), AD vs control, with
  transcripts. Access via agreement.
- **ADReSS / ADReSSo / ADReSS-M challenges** —
  [ADReSS-M overview (PMC11218814)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11218814/) ·
  [ADReSSo 2021](https://luzs.gitlab.io/adresso-2021/) ·
  [ADReSS-M 2023](https://luzs.gitlab.io/madress-2023/) — balanced, benchmarked
  subsets (e.g. 156 participants, 78 AD / 78 HC) with published baselines. Best
  starting point for a speech classifier.
- **awesome-dementia-detection** —
  [github.com/billzyx/awesome-dementia-detection](https://github.com/billzyx/awesome-dementia-detection)
  — maintained index of datasets + papers.

## Webcam finger tapping (closest to our modality)
- **PARK / ROC-HCI** — webcam finger-tapping, expert **MDS-UPDRS 0–4** labels
  (250 subj, 489 videos). Raw video HIPAA-restricted, but **extracted features +
  labels + code are public**: [github.com/ROC-HCI/finger-tapping-severity](https://github.com/ROC-HCI/finger-tapping-severity).
  Best near-term validation target — details in
  [08](08-clinical-validation-datasets.md).

## Drawing / motor (Parkinson's, transferable methods)
- **HandPD / NewHandPD** — spiral & meander drawing images, PD vs control.
  Official homepage: [wwwp.fc.unesp.br/~papa/pub/datasets/Handpd](https://wwwp.fc.unesp.br/~papa/pub/datasets/Handpd/).
  Also **Kaggle "Parkinson's Drawings"** (Zham et al.):
  [kaggle.com/kmader/parkinsons-drawings](https://www.kaggle.com/kmader/parkinsons-drawings).
  ⚠️ These are **static ink images with no time axis** — they cannot feed our
  air-traced spiral pipeline or validate velocity/jerk metrics (see
  [08 §2](08-clinical-validation-datasets.md)). A digitizing-tablet spiral set
  with x/y/t is the better analog.
- **Spiral/wave PD drawing sets** referenced in the explainable-CNN work in
  [02-drawing-spiral-clock.md](02-drawing-spiral-clock.md).

## Eye tracking
- Clinically-labeled saccade/antisaccade data is mostly **infrared, not webcam**:
  OpenNeuro ds000120/ds000119, [Zenodo pro/antisaccade behavioral data](https://doi.org/10.5281/zenodo.6757621),
  ONDRI / Oxford antisaccade cohort (on request). Webcam-but-non-clinical:
  [EM-COGLOAD (OSF)](https://osf.io/zjtdq). Use for range sanity-checks only —
  see [08 §3](08-clinical-validation-datasets.md).

## Libraries to reuse (all free / open source)
| Purpose | Library |
|---|---|
| Hand/face/iris landmarks | **MediaPipe** (Tasks API — already used) |
| Landmark smoothing | **One-Euro filter** (already in `hand_utils.py`) |
| Audio features | **librosa**, **noisereduce** |
| Voice quality (jitter/shimmer/tremor) | **praat-parselmouth** |
| Local speech-to-text | **faster-whisper** / openai-whisper |
| NLP (fluency, lexical, syntax) | **spaCy**, **NLTK** |
| Cross-platform audio I/O | **sounddevice**, **simpleaudio** |
| Biomechanical model (glove) | **OpenSim** + ARMs Wrist & Hand Model |
| 3D twin render (glove) | **Open3D** / **PyVista** |
| Serial (glove) | **pyserial** |
| Classifiers / stats | **scikit-learn**, **numpy**, **scipy** |

## Takeaways for this project
1. **Prototype speech on ADReSS** before recruiting anyone — it has labels and
   baselines to beat.
2. **Prototype spiral *scoring concepts* on HandPD-style data** (PD labels) —
   but note these are static images: they validate path-deviation ideas only,
   not our velocity/jerk metrics or the air-tracing pipeline
   ([08 §2](08-clinical-validation-datasets.md)).
3. Everything in the library table is free and mostly already in the stack —
   the missing pieces are audio/NLP/eye-tracking packages, not new
   infrastructure.
