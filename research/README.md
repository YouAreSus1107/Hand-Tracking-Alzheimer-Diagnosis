# Research Basis

_Compiled 2026-07-20. Curated literature and code behind each current and
planned capability of this project._

Each file below covers one domain: a short list of the most relevant
papers/repos, a one-to-two-line conclusion for each, and a **"How it helps this
project"** note. Conclusions are distilled from published abstracts, reviews,
and project pages — treat exact figures as approximate and verify against the
primary source before citing in any formal write-up.

## Index

| File | Domain | Maps to |
|---|---|---|
| [01-webcam-hand-motor.md](01-webcam-hand-motor.md) | Webcam finger-tapping & hand movement | `finger_tapping.py`, `hand_tracking.py` |
| [02-drawing-spiral-clock.md](02-drawing-spiral-clock.md) | Spiral / clock / drawing tests | `spiral_test.py`, planned clock test |
| [03-speech.md](03-speech.md) | Speech: DDK, fluency, connected speech | planned `speech_tests/` |
| [04-oculomotor-gaze.md](04-oculomotor-gaze.md) | Webcam eye tracking, saccades | planned oculomotor test |
| [05-cognitive-motor.md](05-cognitive-motor.md) | Keystroke, trail-making, reaction time | planned cognitive-motor tests |
| [06-wearable-cocontraction.md](06-wearable-cocontraction.md) | Sensor glove, OpenSim, co-contraction | the Hand Digital Twin device |
| [07-datasets-and-tools.md](07-datasets-and-tools.md) | Open datasets & libraries to reuse | validation & training |
| [08-clinical-validation-datasets.md](08-clinical-validation-datasets.md) | Clinically-labeled data to validate our metrics | Roadmap #9 clinical pilot |

## The single most important finding: TAS Test

**TAS Test** (University of Tasmania / Wicking Dementia Centre) is the closest
existing work to this project's *whole* vision, and every plan here should be
read against it.

- A **20-minute online, at-home, unsupervised** battery of **motor + cognitive
  + speech** tests, run on an ordinary **laptop webcam, keyboard, mouse, and
  microphone** — no wearable required.
- Hand-movement features are extracted by **computer vision** and were
  **validated against wearable sensors**.
- Studied in **2,351 adults aged 50–89**; hand-movement features improved
  prediction of episodic memory, executive function, and working memory, and a
  clinical-validation study discriminated subjective cognitive decline, MCI, and
  dementia.
- Aim: detect preclinical Alzheimer's **10–20 years before symptoms** and
  estimate 5-year risk.

**What this means for the project:**
1. **The core concept is validated, not speculative** — a laptop-only
   motor-cognitive-speech screen is a real, published research direction. That
   de-risks the whole roadmap.
2. **This project is not first**, so its contribution must be sharpened. Two
   honest differentiators remain open:
   - **Open-source & self-hostable.** TAS Test is a closed research platform;
     an open, inspectable, locally-run suite (this project) has independent
     value for reproducibility and other researchers.
   - **The wearable co-contraction "digital twin"** measures an *internal*
     signal (agonist/antagonist co-contraction) that TAS Test and every
     camera-only system physically cannot see — this is the genuinely novel
     axis (see [06](06-wearable-cocontraction.md)).
3. **Adopt their validated task set.** TAS Test and TapTalk both converge on
   finger tapping + speech + simple cognitive tasks. Building those (already
   underway here) follows a proven template rather than guessing.

Sources: [TAS Test protocol (BMC Neurology 2022)](https://bmcneurol.biomedcentral.com/articles/10.1186/s12883-022-02772-5) ·
[Clinical validation (Alz & Dementia 2023)](https://alz-journals.onlinelibrary.wiley.com/doi/abs/10.1002/alz.082129) ·
[Feasibility in 2,300 adults (2025)](https://www.sciencedirect.com/science/article/pii/S2274580725000251) ·
[UTAS overview](https://www.utas.edu.au/wicking/research/tas-test-the-future-in-our-hands-screening-for-preclinical-alzheimers)
