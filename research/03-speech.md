# Speech: DDK, Fluency, Connected Speech

Maps to: planned `speech_tests/` (laptop microphone only).

## Reviews & pipelines

**Systematic review — automatic AD detection from speech/language (JAMIA 2020)**
[Oxford Academic](https://academic.oup.com/jamia/article/27/11/1784/5905567)
Broad review of acoustic + linguistic features and models for AD detection.
→ Authoritative map of which features matter; a reading anchor before building.

**Noninvasive AD detection from spontaneous speech — review (2023)**
[PMC10484224](https://pmc.ncbi.nlm.nih.gov/articles/PMC10484224/)
Surveys spontaneous-speech pipelines; connected speech carries strong signal.
→ Supports adding a picture-description/connected-speech task.

**Novel speech algorithm for cognitive impairment, Spanish cohort (2024)**
[PMC11024431](https://pmc.ncbi.nlm.nih.gov/articles/PMC11024431/)
Multidimensional analysis — rhythmic, acoustic, lexical, morpho-syntactic,
syntactic features — using **librosa**; targets earliest decline.
→ Concrete, language-general feature taxonomy to implement with librosa (which
this project's stack already implies).

**Multimodal AI dementia screening from speech (2025)**
[arXiv:2502.08862](https://arxiv.org/pdf/2502.08862)
Digital speech pipelines identify AD comparably to gold standards from as little
as **~2 minutes of audio**.
→ Very short recordings suffice — fits an unsupervised home battery.

## Semantic / verbal fluency

**Semantic verbal fluency for dementia** (covered across the review above and
awesome-dementia-detection). SVF ("name animals in 60 s") probes semantic access,
among the earliest-affected language domains in AD.
→ High validation-to-effort; needs only transcription + simple NLP.

## Transcription & tooling

**Whisper for dementia speech** — recent work transcribes dementia speech with
**Whisper large-v2**; **WhisperD** adds filler-word ("um"/"uh") detection, which
is itself informative in AD.
→ Use **`faster-whisper`** locally (no cloud, privacy-preserving) for
transcription; retain fillers and pauses rather than discarding them.

**awesome-dementia-detection** (paper list)
[github.com/billzyx/awesome-dementia-detection](https://github.com/billzyx/awesome-dementia-detection)
→ Living bibliography of speech-based dementia detection — the go-to index.

**ADReSS-Challenge repos** (e.g.
[KarolChlasta/ADReSS-Challenge2020](https://github.com/KarolChlasta/ADReSS-Challenge2020),
[wazeerzulfikar/alzheimers-dementia](https://github.com/wazeerzulfikar/alzheimers-dementia))
→ Reference feature-extraction + classifier code trained on the standard AD
speech benchmark; adaptable starting points.

## Takeaways for this project
1. Build order: **DDK (pa-ta-ka)** → **sustained phonation** (jitter/shimmer,
   voice tremor via `parselmouth`) → **semantic fluency** → **connected speech**.
2. Use **local Whisper** for transcription; keep fillers/pauses as features.
3. Extract the **multidimensional feature set** (acoustic + rhythmic + lexical +
   syntactic) from the Spanish-cohort paper as the initial feature spec.
4. ~2 minutes of audio is enough — keep tasks short for home use.
