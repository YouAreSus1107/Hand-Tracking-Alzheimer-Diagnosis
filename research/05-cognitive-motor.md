# Cognitive–Motor: Keystroke, Trail-Making, Reaction Time

Maps to: planned keyboard/mouse-based tests (laptop only).

## Keystroke dynamics

**Keystroke dynamics as digital biomarkers — meta-analysis (Nature Sci Reports 2022)**
[nature.com/s41598-022-11865-7](https://www.nature.com/articles/s41598-022-11865-7)
Systematic review/meta-analysis of keystroke dynamics for fine-motor decline in
neuropsychiatric disorders; supports diagnostic value as a passive biomarker.
→ Best evidence anchor: passive typing timing is a legitimate fine-motor
biomarker.

**neuroQWERTY — at-home natural typing detects early PD (JMIR 2018)**
[jmir.org/2018/3/e89](https://www.jmir.org/2018/3/e89/citations)
Detects early PD motor impairment from natural, uncontrolled at-home typing.
→ Precedent for *passive*, in-the-wild capture — no scripted task needed.

**Smartphone keystroke dynamics vs MoCA-K for MCI (2024)**
[PMC11561447](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11561447/)
Keystroke dynamics distinguish MCI from controls, benchmarked against a standard
neuropsych screen (MoCA-K).
→ Shows keystroke signal reaches *cognitive* (MCI), not just motor, endpoints.

**Key finding across studies:** patients show longer **flight time** (inter-key
delay), fewer taps in fixed windows, and **arrhythmokinesia** (hastening/freezing
of typing rhythm).
→ Compute hold time, flight time, and their variability — the same
rhythm-variability lens as the tapping test, on the keyboard.

## Trail-Making Test (executive function / set-shifting)
A digital TMT-A/B (connect 1-2-3… then 1-A-2-B…) captured via mouse/trackpad
yields completion time plus **path efficiency, pauses, and error taps** — a
richer signal than the paper stopwatch. (General digital-cognitive-test
literature; pairs naturally with the clock-drawing work in
[02](02-drawing-spiral-clock.md).)
→ Low-effort, high-recognition executive-function test using only the mouse.

## Reaction time / Stroop
Simple and choice reaction-time and Stroop (color–word) tasks measure processing
speed and inhibitory control from key-press latencies — cheap to implement and
standard in cognitive test batteries (and present in TAS Test's keyboard tasks).

## Takeaways for this project
1. Add a **keystroke-dynamics** capture: a short typing task (or passive
   logging) → hold/flight times + variability. Reuses the tapping test's
   variability metrics on a new input device.
2. Add a **digital Trail-Making A/B** on the trackpad for executive function.
3. Add **choice reaction time + Stroop** as quick processing-speed/inhibition
   probes.
4. Every test above needs **only keyboard/mouse** — zero new hardware, and each
   slots into the shared session schema.
