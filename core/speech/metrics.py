"""
DDK metrics: syllable onsets → scored biomarkers (SPEECH_TEST_PLAN.md §3.1).
Pure functions, unit-tested against synthetic syllable trains.

The scored shape is deliberately the tapping test's — rate, variability,
decrement — because DDK is the articulatory analogue of IIV tapping. The
helpers are imported from core/tapping/metrics.py rather than copied, so the
two tests cannot drift apart on what "SD" or "slope" means.

Derived per run:
  syllable_rate_hz        syllables per second (1000 / mean interval)
  mean_isi_ms / isi_sd_ms inter-syllable interval mean and SD
  rhythm_cv_pct           SD / mean · 100 — the headline
  npvi                    normalised pairwise variability index — the standard
                          DDK rhythm index; consecutive-interval contrast,
                          insensitive to a slow drift in rate
  decrement_pct_per_s     slope of instantaneous rate (negative = slowing)
  snr_db / clipping_pct   recording quality
  sequence_error_pct      pa-ta-ka order errors — only when the optional
                          phoneme recogniser ran (phonemes.py). EXPERIMENTAL:
                          recorded, not shown, until it is validated on real
                          voices (SPEECH_TEST_PLAN.md §3.1b)
"""

from __future__ import annotations

from core.tapping.metrics import _median, _sd, _slope

from .confidence import confidence, straddles_band
from .onsets import Syllable
from .phonemes import count_agreement_pct, sequence_errors
from .tasks import SpeechTask

MIN_SNR_DB = 12.0           # below this, peaks are indistinguishable from room noise
MAX_CLIP_FRAC = 0.05        # above this, the vowel peaks are flattened
PAUSE_FACTOR = 3.0          # interval > 3× median = a breath, not a syllable


def band(cv_pct: float, task: SpeechTask) -> tuple[str, str]:
    """(status token, plain-language label). Same words as the tapping bands."""
    if cv_pct < task.cv_typical:
        return "success", "Within typical range"
    if cv_pct < task.cv_monitor:
        return "warning", "Mild variability - consider monitoring"
    return "danger", "Elevated variability - recommend follow-up"


def npvi(intervals: list[float | None]) -> float | None:
    """nPVI over consecutive pairs. `None` marks a dropped interval (a pause),
    which breaks the pair either side of it rather than bridging it."""
    terms = []
    for a, b in zip(intervals, intervals[1:]):
        if a is None or b is None or a + b <= 0:
            continue
        terms.append(abs(a - b) / ((a + b) / 2.0))
    if len(terms) < 2:
        return None
    return 100.0 * sum(terms) / len(terms)


def compute_metrics(task: SpeechTask, syllables: list[Syllable],
                    t_start: float, t_end: float, *,
                    snr_db: float | None, clip_frac: float,
                    ml: dict | None = None) -> dict:
    """Score one recording. Always returns a dict; `scoreable` is False with a
    human-readable `reason` when no honest score can be formed.

    `syllables` carry times on the same clock as t_start/t_end. `ml`, when the
    recogniser ran, is {"syllables": [(label, t), ...]} over the same window.
    """
    onsets = [s.onset_s for s in syllables if t_start <= s.onset_s < t_end]
    out: dict = {
        "scoreable": False, "reason": None,
        "syllables": len(onsets), "duration_s": round(t_end - t_start, 2),
        "syllable_rate_hz": None, "mean_isi_ms": None, "isi_sd_ms": None,
        "rhythm_cv_pct": None, "npvi": None, "decrement_pct_per_s": None,
        "n_intervals": None, "cv_ci_low_pct": None, "cv_ci_high_pct": None,
        "confidence_pct": None, "confidence_level": None, "band_edge": None,
        "snr_db": snr_db, "clipping_pct": 100.0 * clip_frac,
        "status": None, "label": None, "confidence_reasons": [],
        "sequence_error_pct": None, "sequence_transitions": None,
        "ml_syllables": None, "count_agreement_pct": None,
    }

    # The recogniser's readings are reported even when the rhythm cannot be
    # scored: a sequencing error rate does not need a clean envelope.
    if ml is not None:
        labels = [lab for lab, t in ml.get("syllables", [])
                  if t_start + task.trim_s <= t < t_end]
        seq = sequence_errors(labels, task.cycle)
        out["sequence_error_pct"] = seq["error_pct"]
        out["sequence_transitions"] = seq["n"]
        ml_all = [t for _, t in ml.get("syllables", []) if t_start <= t < t_end]
        out["ml_syllables"] = len(ml_all)
        out["count_agreement_pct"] = count_agreement_pct(len(ml_all), len(onsets))

    if clip_frac > MAX_CLIP_FRAC:
        out["reason"] = ("The microphone was overloaded (clipping) - move back "
                         "from it a little and try again.")
        return out
    if not onsets:
        out["reason"] = ("No speech was detected - check that the right "
                         "microphone is selected and speak a little louder.")
        return out
    if snr_db is not None and snr_db < MIN_SNR_DB:
        out["reason"] = ("The recording was too noisy to find syllables "
                         "reliably - move somewhere quieter and try again.")
        return out
    if len(onsets) < task.min_syllables:
        out["reason"] = (f"Only {len(onsets)} syllables detected - at least "
                         f"{task.min_syllables} are needed for a reliable score.")
        return out

    # Ramp-up trim, only when enough syllables remain (plan §2.1).
    trimmed = [t for t in onsets if t >= t_start + task.trim_s]
    if len(trimmed) >= task.min_syllables:
        onsets = trimmed

    isi_all = [(b - a) * 1000.0 for a, b in zip(onsets, onsets[1:])]
    cutoff = PAUSE_FACTOR * _median(isi_all)
    kept = [v if v <= cutoff else None for v in isi_all]
    isi = [v for v in kept if v is not None]
    if len(isi) < task.min_syllables - 1:
        out["reason"] = ("Speech was too irregular to score - long pauses "
                         "interrupted the repetition. Try to keep going "
                         "without stopping.")
        return out

    mean_isi = sum(isi) / len(isi)
    sd = _sd(isi)
    rate = 1000.0 / mean_isi
    if rate < task.min_effort_hz:
        out["reason"] = (f"Speech was too slow to score a rhythm "
                         f"({rate:.1f} syllables/s). Keep repeating without "
                         f"pausing between syllables.")
        return out
    cv = sd / mean_isi * 100.0
    out.update(syllable_rate_hz=rate, mean_isi_ms=mean_isi, isi_sd_ms=sd,
               rhythm_cv_pct=cv, npvi=npvi(kept), n_intervals=len(isi))

    rejected_frac = (len(isi_all) - len(isi)) / len(isi_all)
    q = confidence(n_intervals=len(isi), cv_pct=cv,
                   band_width_pct=task.cv_band_width, snr_db=snr_db,
                   clip_frac=clip_frac, rejected_frac=rejected_frac)
    out.update(confidence_pct=q["confidence_pct"],
               confidence_level=q["confidence_level"],
               cv_ci_low_pct=q["cv_ci_low_pct"],
               cv_ci_high_pct=q["cv_ci_high_pct"],
               confidence_reasons=q["reasons"])
    out["band_edge"] = int(straddles_band(q["cv_ci_low_pct"], q["cv_ci_high_pct"],
                                          task.cv_typical, task.cv_monitor))

    mids, rates = [], []
    for (a, b), v in zip(zip(onsets, onsets[1:]), kept):
        if v is not None:
            mids.append((a + b) / 2.0 - t_start)
            rates.append(1000.0 / v)
    sl = _slope(mids, rates)
    if sl is not None and rates:
        mean_rate = sum(rates) / len(rates)
        if mean_rate > 0:
            out["decrement_pct_per_s"] = sl / mean_rate * 100.0

    out["status"], out["label"] = band(cv, task)
    out["scoreable"] = True
    return out
