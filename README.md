# Hand-Detection-3D

Six short motor tests that run on an ordinary webcam and microphone, aimed at
the fine-motor, eye-movement and speech changes that research links to early
cognitive decline and Parkinson's disease. A local web hub launches the tests,
keeps each person's results, and charts them over time.

<!-- Hero screenshot goes here: assets/screenshots/<file> -->

## Status

This is a research prototype, not a diagnostic or screening device.

- Only the finger tapping test has been checked against outside data (see
  [Validation](#validation)). The other tests' result bands come from the
  papers they are based on and are provisional.
- The tremor test's offline analysis, the walking test and the speech test's
  vowel part are built and unit-tested but have not yet been run live.
- Most runs so far come from a small number of people on a few cameras.

## The tests

| Test | What the person does | Headline measure |
|---|---|---|
| Finger tapping | Tap thumb and index finger together, as big and fast as possible or in time with a metronome | Rhythm variability (CV% of the intervals between taps) |
| Spiral | Trace a spiral in the air with the index fingertip | Movement smoothness (SPARC, 0–100) |
| Eye movement | Look toward a dot, then away from it, then hold still | Anti-saccade error rate, with latency and fixation stability |
| Speech | Say "pa-ta-ka" repeatedly, then hold an "ahh" | Syllable rhythm variability; voice jitter (Praat) |
| Tremor | Rest both hands in the lap, palms up and then down, then hold the arms out | Tremor frequency and size for each hand |
| Walking (seated part) | Stamp each leg in turn, then stand up from a chair five times | Five sit-to-stand time |

Tremor is a supporting check. It flags a tremor that would otherwise inflate
the tapping and spiral scores, and it is how the camera is checked against the
glove. It is not a cognitive marker on its own.

Each run is saved as one JSON file in `results/` plus a row in
`results/index.csv`, tagged with the person it belongs to. Nothing leaves the
machine. Audio and video are never saved, only the measurements and the traces
derived from them.

## Validation

The tapping test has been run, unchanged, on two public datasets.

**Accuracy: [EHWGesture](https://github.com/smilies-polito/EHWGesture).**
These are tapping videos filmed next to a 120 fps motion-capture system, so
the true time of every tap is known. On the held-out volunteers, the test
found 99.7% of taps. Its CV% had a median error of 0.7 points, and 45 of 47
recordings landed in the same result band as the motion-capture reference.

**Clinical: [HUBU-FIS](https://zenodo.org/records/17738775).** This dataset
has 234 phone videos from 75 people with Parkinson's disease and 43 controls,
each hand rated by a neurologist on the UPDRS finger-tapping item. The
analysis plan was written before any result was seen.

| Measure | Result |
|---|---|
| Spearman correlation between CV% and UPDRS grade | 0.47 (95% CI 0.33–0.59) |
| AUC, UPDRS 2–3 vs. 0 | 0.86 (95% CI 0.77–0.94) |
| UPDRS 0 hands graded Typical | 93% |
| UPDRS 2–3 hands flagged | 73% |
| Videos scored | 229 of 234 |

These numbers describe detecting a motor impairment in Parkinson's disease.
They say nothing yet about cognitive decline.

## Setup

Windows, Python 3.9–3.12.

```bash
python install.py                  # creates .venv, installs deps, downloads the models
.venv/Scripts/python launcher.py   # hub at http://127.0.0.1:8770
```

On Windows, `setup.bat` and `run_hub.bat` do the same by double-click.
`python install.py --speech-ml` adds an optional phoneme model for the speech
test (about 1.4 GB).

The camera, the language (English or 繁體中文) and the person being tested are
chosen in the hub, and each test picks them up when it starts. A test can also
be run directly, for example `.venv/Scripts/python screening_tests/finger_tapping.py`,
and it then asks for a camera in the console. In any test, `q` quits and `s`
skips a practice phase.

## Tests for the code

The engines are pure Python and their tests need no camera:

```bash
python screening_tests/tests/test_tapping.py
python screening_tests/tests/test_run_loops.py    # every camera test's run loop, headless (~3 min)
```

`screening_tests/tests/` has one file per engine (tapping, spiral, gaze,
speech, tremor, gait, glove) and a few for shared parts (framing, camera,
translations, profiles, remote sessions).

## The published dashboard

The same dashboard is published as a static site. It cannot run the tests
(they are Python and need the camera), so it connects to the hub on your own
machine instead: start `run_hub.bat`, open the site, and press **Connect**.
The hub pairs with the page through a redirect, and from then on every button
on the site works against your local install. The browser talks to
`127.0.0.1`, so recordings never reach the host. Chrome or Edge only; Safari
blocks a local connection from an https page.

```bash
python tools/build_web.py          # web-build/ plus the setup bundle it offers
firebase deploy --only hosting
```

The download bundle is built from the current commit, so commit first.

## Layout

```
launcher.py            The hub: local web server, standard library only
launcher_web/          Hub frontend (plain JS, no build step)
screening_tests/       One entry script per test, and tests/ for the unit tests
core/
  tapping/ spiral/ gaze/ speech/ tremor/ gait/
                       One pure engine per test: detection, metrics, confidence
  camera.py            Camera choice by name, frame-rate measurement, mirroring
  framing.py           Is the whole hand in the picture?
  session.py           Results schema: results/*.json + index.csv
  profiles.py          The roster of people being tested
  i18n.py              English/Chinese for the test screens
  ui/                  Drawing toolkit for the test screens
  glove/               Sensor-glove host code (serial protocol, force, bend, IMU)
  remote/              Remote sessions on the participant's phone (paused prototype)
participant/           The browser page for remote sessions
firmware/glove/        Arduino sketch for the sensor glove
tools/                 Site build, release bundle, dataset evaluations
model/                 MediaPipe model bundles
assets/                3D hand model, fonts, screenshots
results/               Session output (git-ignored)
```

## How the measurement works

- MediaPipe Tasks API in VIDEO mode: the hand (21 points), face and iris
  (478 points) and body pose models. The models are Google's; this project is
  the measurement layer on top.
- Anything that measures jitter or tremor reads the raw landmarks. The
  smoothing filter is only for what is drawn on screen, because it would erase
  the signal.
- A hand partly out of frame is not trusted, since MediaPipe keeps guessing the
  hidden points. Tapping pauses and the spiral skips those frames.
- Each result carries a confidence score (sample size, tracking quality,
  timing), shown beside the verdict.
- The sensor glove (Arduino Nano 33 BLE, 100 Hz) streams fingertip force, finger
  bend and IMU data. The tremor test compares the glove's gyroscope with the
  camera.

## Sources

Tapping: Namkoong & Roh (2024), *Technology and Health Care* 32(S1):253–264;
Suzumura et al.; Roalf et al. (2018). Spiral: Kachouri et al. (2021),
Schroter et al. (2003), Balasubramanian et al. (2015) for SPARC. Eye movement:
Opwonya et al. (2022), Crawford et al. (2005), and the Antoniades et al. (2013)
protocol. Voice: Praat's standard perturbation measures via
praat-parselmouth.

## Origins

The tracking pipeline began from
[imadeddinedjekoune/Hand-Detection-3D](https://github.com/imadeddinedjekoune/Hand-Detection-3D),
which mirrored a hand onto a rigged model in Unity. This project rewrote the
tracker around the MediaPipe Tasks API and turned it toward motor measurement.
The Unity side is retired.
