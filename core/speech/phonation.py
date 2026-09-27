"""
Sustained phonation — a held "ahhh" → voice-stability biomarkers
(SPEECH_TEST_PLAN.md §3.2). Phase 3 of the speech plan.

Two layers, split the way the DDK engine is:

  measure()          Praat, through praat-parselmouth, on the steady middle of
                     the vowel: jitter, shimmer, HNR, and the F0 contour.
                     Praat is the clinical reference implementation of these
                     measures — reimplementing them would only make the numbers
                     incomparable with the literature.
  vocal_tremor()     pure NumPy: the 2-10 Hz modulation of the F0 contour,
  compute_metrics()  and the gates, bands and confidence. Unit-tested on
                     synthetic contours without Praat.

Why the middle only: jitter and shimmer are cycle-to-cycle perturbation
measures, and the onset and release of a vowel are *meant* to be unstable —
scoring them would measure how someone starts and stops, not how steady the
voice is.
"""

from __future__ import annotations

import math

import numpy as np

from .confidence import phonation_confidence
from .tasks import PhonationTask

# Hard floor, the same as DDK's. It was 15 dB and rejected 1 of Adam's first 2
# live vowels at 14.6 dB — a run whose jitter (0.40%) matched his clean one
# (0.37%). Between here and 30 dB the confidence score falls instead.
MIN_SNR_DB = 12.0
MAX_CLIP_FRAC = 0.05
TREMOR_BAND = (2.0, 10.0)   # vocal tremor band, Hz (plan §3.2)
MIN_TREMOR_S = 2.0          # contour needed for a tremor spectrum
PITCH_STEP_S = 0.01

# Praat's standard perturbation arguments: period floor/ceiling (s) and the
# maximum period factor, plus the maximum amplitude factor for shimmer. These
# are the defaults every jitter/shimmer figure in the literature is quoted at.
_PERIOD_FLOOR, _PERIOD_CEIL, _MAX_PERIOD_FACTOR, _MAX_AMP_FACTOR = \
    0.0001, 0.02, 1.3, 1.6


def available() -> bool:
    import importlib.util
    return importlib.util.find_spec("parselmouth") is not None


def _num(v) -> float | None:
    """Praat answers 'undefined' as NaN; the results schema wants None."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def measure(samples: np.ndarray, sr: int, task: PhonationTask) -> dict:
    """Praat measures on the scored segment of one recording.

    Returns {"jitter_pct", "shimmer_pct", "hnr_db", "f0_times", "f0_hz",
    "seg_start_s", "seg_end_s"} — f0_hz is 0 where Praat found no voicing.
    """
    import parselmouth
    from parselmouth.praat import call

    x = np.asarray(samples, dtype=np.float64).ravel()
    total = x.size / sr
    a = task.skip_start_s
    b = max(a, total - task.skip_end_s)
    out = {"jitter_pct": None, "shimmer_pct": None, "hnr_db": None,
           "f0_times": [], "f0_hz": [], "seg_start_s": a, "seg_end_s": b}
    if b - a < 0.5:
        return out
    seg = parselmouth.Sound(x[int(a * sr):int(b * sr)], sampling_frequency=sr)

    pitch = seg.to_pitch_ac(time_step=PITCH_STEP_S,
                            pitch_floor=task.f0_floor_hz,
                            pitch_ceiling=task.f0_ceiling_hz)
    out["f0_times"] = [float(t) + a for t in pitch.xs()]
    out["f0_hz"] = [float(f) for f in pitch.selected_array["frequency"]]
    if not any(f > 0 for f in out["f0_hz"]):
        return out

    pp = call(seg, "To PointProcess (periodic, cc)",
              task.f0_floor_hz, task.f0_ceiling_hz)
    jit = _num(call(pp, "Get jitter (local)", 0, 0,
                    _PERIOD_FLOOR, _PERIOD_CEIL, _MAX_PERIOD_FACTOR))
    shim = _num(call([seg, pp], "Get shimmer (local)", 0, 0,
                     _PERIOD_FLOOR, _PERIOD_CEIL, _MAX_PERIOD_FACTOR,
                     _MAX_AMP_FACTOR))
    harm = call(seg, "To Harmonicity (cc)", PITCH_STEP_S, task.f0_floor_hz,
                0.1, 1.0)
    out["jitter_pct"] = jit * 100.0 if jit is not None else None
    out["shimmer_pct"] = shim * 100.0 if shim is not None else None
    out["hnr_db"] = _num(call(harm, "Get mean", 0, 0))
    return out


def vocal_tremor(f0_hz: list[float], step_s: float = PITCH_STEP_S
                 ) -> tuple[float | None, float | None]:
    """(dominant tremor frequency Hz, tremor amplitude as % of mean F0) from an
    F0 contour sampled every `step_s`, 0 = unvoiced.

    Uses the longest voiced run (a gap would put a step into the spectrum),
    removes the linear trend (a slow pitch drift is not tremor), and reads the
    strongest peak in the 2-10 Hz band. Amplitude is the RMS of the in-band
    component, so a pure sinusoidal wobble of ±A% reads as A/√2 %.
    """
    f = np.asarray(f0_hz, dtype=np.float64)
    best, cur = (0, 0), None
    for i, v in enumerate(np.append(f, 0.0)):
        if v > 0 and cur is None:
            cur = i
        elif v <= 0 and cur is not None:
            if i - cur > best[1] - best[0]:
                best = (cur, i)
            cur = None
    run = f[best[0]:best[1]]
    if run.size * step_s < MIN_TREMOR_S:
        return None, None
    mean = float(run.mean())
    t = np.arange(run.size)
    y = run - np.polyval(np.polyfit(t, run, 1), t)
    spec = np.fft.rfft(y * np.hanning(y.size))
    freqs = np.fft.rfftfreq(y.size, step_s)
    band = (freqs >= TREMOR_BAND[0]) & (freqs <= TREMOR_BAND[1])
    if not band.any():
        return None, None
    peak_hz = float(freqs[band][np.argmax(np.abs(spec[band]))])
    # In-band RMS straight from the unwindowed spectrum (Parseval).
    raw = np.fft.rfft(y)
    inband = np.zeros_like(raw)
    inband[band] = raw[band]
    rms = float(np.sqrt(np.mean(np.fft.irfft(inband, n=y.size) ** 2)))
    return peak_hz, 100.0 * rms / mean if mean > 0 else None


def band(jitter_pct: float, task: PhonationTask) -> tuple[str, str]:
    if jitter_pct < task.jitter_typical:
        return "success", "Within typical range"
    if jitter_pct < task.jitter_monitor:
        return "warning", "Mildly elevated - consider monitoring"
    return "danger", "Elevated - recommend follow-up"


def compute_metrics(task: PhonationTask, meas: dict, *, snr_db: float | None,
                    clip_frac: float) -> dict:
    """Score one sustained vowel. Always returns a dict; `scoreable` is False
    with a human-readable `reason` when no honest score can be formed."""
    f0 = [v for v in meas.get("f0_hz", []) if v > 0]
    n_frames = len(meas.get("f0_hz", []))
    voiced_s = len(f0) * PITCH_STEP_S
    out: dict = {
        "scoreable": False, "reason": None,
        "duration_s": task.duration_s,
        "jitter_pct": meas.get("jitter_pct"),
        "shimmer_pct": meas.get("shimmer_pct"),
        "hnr_db": meas.get("hnr_db"),
        "f0_mean_hz": float(np.mean(f0)) if f0 else None,
        "f0_sd_hz": float(np.std(f0, ddof=1)) if len(f0) > 1 else None,
        "voiced_s": round(voiced_s, 2),
        "voiced_pct": 100.0 * len(f0) / n_frames if n_frames else None,
        "vocal_tremor_hz": None, "vocal_tremor_pct": None,
        "snr_db": snr_db, "clipping_pct": 100.0 * clip_frac,
        "confidence_pct": None, "confidence_level": None,
        "confidence_reasons": [], "status": None, "label": None,
    }
    out["vocal_tremor_hz"], out["vocal_tremor_pct"] = \
        vocal_tremor(meas.get("f0_hz", []))

    if clip_frac > MAX_CLIP_FRAC:
        out["reason"] = ("The microphone was overloaded (clipping) - move back "
                         "from it a little and try again.")
        return out
    if not f0:
        out["reason"] = ("No steady voice was detected - check that the right "
                         "microphone is selected and hold the sound a little "
                         "louder.")
        return out
    if snr_db is not None and snr_db < MIN_SNR_DB:
        out["reason"] = ("The recording was too noisy to measure the voice "
                         "reliably - move somewhere quieter and try again.")
        return out
    if voiced_s < task.min_voiced_s:
        out["reason"] = (f"Only {voiced_s:.1f} s of steady voice was recorded - "
                         f"at least {task.min_voiced_s:.1f} s is needed. Hold "
                         f"the sound for the whole countdown.")
        return out
    if out["jitter_pct"] is None:
        out["reason"] = ("The voice was too irregular to measure - hold one "
                         "steady, comfortable pitch and try again.")
        return out

    q = phonation_confidence(snr_db=snr_db, clip_frac=clip_frac,
                             voiced_frac=(out["voiced_pct"] or 0) / 100.0,
                             voiced_s=voiced_s)
    out.update(confidence_pct=q["confidence_pct"],
               confidence_level=q["confidence_level"],
               confidence_reasons=q["reasons"])
    out["status"], out["label"] = band(out["jitter_pct"], task)
    out["scoreable"] = True
    return out
