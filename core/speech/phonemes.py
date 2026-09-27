"""
Optional phoneme recogniser — a machine-learning cross-check on the DDK
envelope engine (SPEECH_TEST_PLAN.md §3.1a).

The envelope (onsets.py) says *when* each syllable happened; it cannot say
*which* syllable it was. A phoneme recogniser can, which buys one measure the
envelope never could — **sequencing errors** in "pa-ta-ka" (a "ka" where a "ta"
belonged) — plus an independent syllable count to check the envelope's
against. It is never the score: the rhythm CV% headline always comes from the
envelope, which is deterministic and is what the published validation used.

Model: facebook/wav2vec2-xlsr-53-espeak-cv-ft (Apache-2.0), a wav2vec 2.0
model fine-tuned to emit espeak IPA phonemes with CTC. Phonemes rather than
words, and multilingual, so it does not care that "pa-ta-ka" is not an English
word or that the speaker may be a Mandarin speaker. The approach follows
BirgerMoell/pataka-test (Acta Logopaedica 2025); no code is taken from it.

Optional in two senses:
  * torch + transformers are not in requirements.txt — `python install.py
    --speech-ml` installs them and pre-downloads the model (~1.2 GB).
  * the model is loaded with local_files_only, so a test never starts a
    1.2 GB download mid-run; if it is not already cached the recogniser is
    simply unavailable and the test runs on the envelope alone.

Everything below `Recogniser` is pure and unit-tested without torch.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass

import numpy as np

MODEL_ID = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
SAMPLE_RATE = 16000
FRAME_S = 0.02                      # wav2vec 2.0 emits one frame per 20 ms

# Consonant → syllable label. Each DDK syllable begins with a stop, so the
# stop *is* the syllable marker; the vowel after it carries no information
# about which syllable was said. Voiced and flapped variants are folded in —
# a devoiced "ba" in fast speech is still an attempt at "pa".
_PLACE = {
    "p": "pa", "b": "pa", "ɓ": "pa",
    "t": "ta", "d": "ta", "ɾ": "ta", "ʈ": "ta", "ɖ": "ta",
    "k": "ka", "g": "ka", "ɡ": "ka", "q": "ka", "c": "ka",
}
_SKIP = {"<pad>", "<s>", "</s>", "<unk>", "|", " "}


@dataclass(frozen=True)
class Phone:
    label: str
    start_s: float
    end_s: float
    prob: float             # mean max-softmax over the phone's frames


# ── Pure: CTC decoding and scoring ─────────────────────────────────────────

def ctc_segments(ids: list[int], probs: list[float], blank_id: int,
                 id2tok: dict[int, str], frame_s: float = FRAME_S
                 ) -> list[Phone]:
    """Greedy CTC decode with timestamps: collapse runs of the same id, drop
    blanks. A run broken by a blank is two phones (that is how CTC spells a
    doubled symbol), which is exactly right for "pa-pa-pa"."""
    out: list[Phone] = []
    i, n = 0, len(ids)
    while i < n:
        j = i
        while j + 1 < n and ids[j + 1] == ids[i]:
            j += 1
        tok_id = ids[i]
        if tok_id != blank_id:
            tok = id2tok.get(tok_id, "<unk>")
            if tok not in _SKIP:
                seg = probs[i:j + 1]
                out.append(Phone(label=tok, start_s=i * frame_s,
                                 end_s=(j + 1) * frame_s,
                                 prob=float(sum(seg) / len(seg))))
        i = j + 1
    return out


def syllable_of(token: str) -> str | None:
    """"pa"/"ta"/"ka" for a stop consonant token, None for anything else.
    espeak tokens can carry diacritics ("tʰ", "kʲ"), so the base character
    decides."""
    return _PLACE.get(token[:1]) if token else None


def syllables_from_phones(phones: list[Phone], t0: float = 0.0,
                          t1: float = float("inf")) -> list[tuple[str, float]]:
    """(label, time) per recognised syllable inside [t0, t1)."""
    out = []
    for ph in phones:
        lab = syllable_of(ph.label)
        if lab and t0 <= ph.start_s < t1:
            out.append((lab, ph.start_s))
    return out


def sequence_errors(labels: list[str], cycle: tuple[str, ...]) -> dict:
    """Sequencing accuracy against the task's syllable cycle.

    One-syllable cycle ("pa-pa-pa"): every syllable that is not that syllable
    is an error. Longer cycle ("pa-ta-ka"): every *transition* that is not the
    expected successor is an error — so one slip ("pa-ka-ta-ka") costs a
    couple of transitions, not the whole rest of the run, which is what a
    position-by-position comparison would charge.
    """
    if not cycle:
        return {"n": 0, "errors": 0, "error_pct": None}
    if len(cycle) == 1:
        n = len(labels)
        errors = sum(1 for lab in labels if lab != cycle[0])
    else:
        succ = {cycle[i]: cycle[(i + 1) % len(cycle)] for i in range(len(cycle))}
        n = max(0, len(labels) - 1)
        errors = sum(1 for a, b in zip(labels, labels[1:]) if succ.get(a) != b)
    return {"n": n, "errors": errors,
            "error_pct": (100.0 * errors / n) if n else None}


def count_agreement_pct(a: int, b: int) -> float | None:
    """How closely two syllable counts agree, 100 = identical."""
    if max(a, b) == 0:
        return None
    return 100.0 * (1.0 - abs(a - b) / max(a, b))


# ── Availability ───────────────────────────────────────────────────────────

def available() -> tuple[bool, str]:
    """(usable, why not). Cheap: never imports torch."""
    for mod in ("torch", "transformers", "huggingface_hub"):
        if importlib.util.find_spec(mod) is None:
            return False, "not installed (python install.py --speech-ml)"
    try:
        from huggingface_hub import try_to_load_from_cache
        hit = try_to_load_from_cache(MODEL_ID, "config.json")
    except Exception:           # noqa: BLE001 - an odd cache must not crash a test
        hit = None
    if not isinstance(hit, str):
        return False, "model not downloaded (python install.py --speech-ml)"
    return True, ""


def download() -> str:
    """Fetch the model into the Hugging Face cache. Used by install.py only."""
    from huggingface_hub import snapshot_download
    return snapshot_download(MODEL_ID, allow_patterns=[
        "config.json", "vocab.json", "preprocessor_config.json",
        "tokenizer_config.json", "special_tokens_map.json",
        "pytorch_model.bin", "model.safetensors"])


# ── The model ──────────────────────────────────────────────────────────────

class Recogniser:
    """Loads once (a few seconds), then transcribes a clip in ~1-3 s on CPU.

    The tokenizer class for this model wants the `phonemizer` package (and an
    espeak install) just to be constructed, although decoding never uses it —
    so the vocabulary is read straight from vocab.json instead, and the
    feature extraction (zero-mean, unit-variance) is done here.
    """

    def __init__(self):
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2ForCTC

        self._torch = torch
        self.model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID, local_files_only=True)
        self.model.eval()
        with open(hf_hub_download(MODEL_ID, "vocab.json", local_files_only=True),
                  encoding="utf-8") as fh:
            vocab = json.load(fh)
        self.id2tok = {int(v): k for k, v in vocab.items()}
        self.blank_id = int(vocab.get("<pad>", self.model.config.pad_token_id or 0))

    def recognise(self, samples: np.ndarray, sr: int) -> list[Phone]:
        x = np.asarray(samples, dtype=np.float64).ravel()
        if sr != SAMPLE_RATE and x.size:
            n = int(round(x.size * SAMPLE_RATE / sr))
            x = np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x)
        if x.size < SAMPLE_RATE // 10:
            return []
        x = (x - x.mean()) / np.sqrt(x.var() + 1e-7)
        torch = self._torch
        with torch.inference_mode():
            logits = self.model(torch.from_numpy(x.astype(np.float32))[None]).logits[0]
            p = torch.softmax(logits, dim=-1)
            best, ids = p.max(dim=-1)
        return ctc_segments(ids.tolist(), best.tolist(), self.blank_id, self.id2tok)
