"""
Unit tests for the speech (DDK) engine (SPEECH_TEST_PLAN.md §7): syllable
detection and scoring exercised against synthetic syllable trains, plus the
pure half of the optional phoneme recogniser. No microphone, no torch.

A synthetic syllable is a short noise burst (the stop release) followed by a
decaying harmonic vowel, then silence (the next closure) — the envelope shape
real "pa-ta-ka" produces. Known onset times in, known rate and CV% out.

Run:  python -m pytest screening_tests/tests/test_speech.py
 or:  python screening_tests/tests/test_speech.py   (self-runs without pytest)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.speech import onsets as on
from core.speech import phonemes as ph
from core.speech.metrics import compute_metrics, npvi, band
from core.speech.onsets import Syllable
from core.speech.tasks import TASKS, DEFAULT_TASK

SR = 16000
TASK = TASKS[DEFAULT_TASK]
RNG = np.random.default_rng(7)


def _syllable(level: float = 0.3, vowel_s: float = 0.09) -> np.ndarray:
    burst = RNG.normal(0, level * 0.4, int(0.006 * SR))
    t = np.arange(int(vowel_s * SR)) / SR
    vowel = sum(np.sin(2 * np.pi * f * t) / k
                for k, f in enumerate((140, 280, 420, 700), start=1))
    attack = np.minimum(1.0, t / 0.012)
    decay = np.exp(-t / (vowel_s * 0.6))
    vowel = level * vowel / np.max(np.abs(vowel)) * attack * decay
    return np.concatenate([burst, vowel])


def _train(onset_times: list[float], total_s: float, noise: float = 0.001,
           level: float = 0.3) -> np.ndarray:
    x = RNG.normal(0, noise, int(total_s * SR))
    for t in onset_times:
        s = _syllable(level)
        i = int(t * SR)
        x[i:i + s.size] += s[:max(0, x.size - i)]
    return x.astype(np.float32)


def _regular(rate: float, t0: float = 0.3, t1: float = 8.3,
             jitter_sd: float = 0.0) -> list[float]:
    times, t = [], t0
    while t < t1:
        times.append(t)
        t += 1.0 / rate + (RNG.normal(0, jitter_sd) if jitter_sd else 0.0)
    return times


def _detect(x):
    return on.detect_syllables(x, SR, min_gap_s=TASK.min_gap_s)


# ── Envelope / onsets ──────────────────────────────────────────────────────

def test_regular_train_is_counted_exactly():
    truth = _regular(6.0)
    syl, _, _, _ = _detect(_train(truth, 8.6))
    assert len(syl) == len(truth), (len(syl), len(truth))


def test_onsets_land_near_the_true_onsets():
    truth = _regular(5.0)
    syl, _, _, _ = _detect(_train(truth, 8.6))
    offsets = [s.onset_s - t for s, t in zip(syl, truth)]
    # The 25 ms analysis window sees the rise a little early, so a small
    # constant offset is expected; what matters for CV% is that it is the
    # same every time.
    assert all(-0.02 < o < 0.04 for o in offsets), offsets
    assert np.std(offsets) < 0.004, np.std(offsets)


def test_fast_rate_is_still_resolved():
    truth = _regular(8.0)
    syl, _, _, _ = _detect(_train(truth, 8.6))
    assert abs(len(syl) - len(truth)) <= 1, (len(syl), len(truth))


def test_aspirated_ka_is_not_counted_twice():
    """The failure from Adam's 2026-09-25 runs: an aspirated "k" released as
    its own quiet peak ~150 ms before the vowel, every third syllable. Counted
    as two syllables it turned a 3% CV run into a 30% one."""
    truth = _regular(2.7)
    x = _train(truth, 8.6)
    for i, t in enumerate(truth):
        if i % 3 == 2:                                  # the "ka"
            burst = RNG.normal(0, 0.03, int(0.03 * SR))
            j = int((t - 0.15) * SR)
            x[j:j + burst.size] += burst.astype(np.float32)
    syl, _, _, floor = _detect(x)
    assert len(syl) == len(truth), (len(syl), len(truth))
    r = compute_metrics(TASK, syl, 0.0, 8.6, snr_db=on.snr_db(syl, floor),
                        clip_frac=0.0)
    assert r["rhythm_cv_pct"] < 3.0, r["rhythm_cv_pct"]


def test_merge_keeps_the_louder_peak_and_leaves_real_gaps_alone():
    s = [Syllable(t, t + 0.05, -25.0, 20) for t in (0.0, 0.4, 0.8, 1.2, 1.6)]
    burst = Syllable(1.05, 1.07, -42.0, 8)              # 150 ms before a vowel
    merged = on.merge_split_syllables(sorted(s + [burst], key=lambda q: q.onset_s))
    assert [q.onset_s for q in merged] == [0.0, 0.4, 0.8, 1.2, 1.6]
    # A real pause is long, not short: it must survive untouched.
    paused = s + [Syllable(2.6, 2.65, -25.0, 20)]
    assert on.merge_split_syllables(paused) == paused


def test_silence_has_no_syllables():
    x = RNG.normal(0, 0.001, 8 * SR).astype(np.float32)
    syl, _, _, _ = _detect(x)
    assert syl == []


def test_quiet_voice_against_loud_room_finds_nothing():
    syl, _, _, _ = _detect(_train(_regular(6.0), 8.6, noise=0.05, level=0.02))
    assert len(syl) < TASK.min_syllables


def test_clipping_fraction():
    x = np.zeros(1000, np.float32)
    x[:30] = 1.0
    assert abs(on.clipping_fraction(x) - 0.03) < 1e-9


def test_levels_are_in_dbfs():
    tone = np.sin(2 * np.pi * 440 * np.arange(SR) / SR).astype(np.float32)
    assert abs(on.rms_dbfs(tone) - (-3.01)) < 0.1
    assert abs(on.peak_dbfs(tone)) < 0.01
    assert on.rms_dbfs(np.zeros(0)) == on.SILENCE_DB


# ── Metrics ────────────────────────────────────────────────────────────────

def _score(truth, total=8.6, **kw):
    x = _train(truth, total, **kw)
    syl, _, _, floor = _detect(x)
    return compute_metrics(TASK, syl, 0.0, total, snr_db=on.snr_db(syl, floor),
                           clip_frac=on.clipping_fraction(x))


def test_steady_speech_scores_low_cv_and_the_right_rate():
    r = _score(_regular(6.0))
    assert r["scoreable"], r["reason"]
    assert abs(r["syllable_rate_hz"] - 6.0) < 0.1, r["syllable_rate_hz"]
    assert r["rhythm_cv_pct"] < 3.0, r["rhythm_cv_pct"]
    assert r["status"] == "success"


def test_jittered_speech_scores_higher_cv():
    steady = _score(_regular(6.0))["rhythm_cv_pct"]
    shaky = _score(_regular(6.0, jitter_sd=0.035))
    assert shaky["scoreable"], shaky["reason"]
    assert shaky["rhythm_cv_pct"] > steady + 10, (steady, shaky["rhythm_cv_pct"])


def test_a_breath_pause_is_excluded_not_scored():
    truth = _regular(6.0, t1=4.0) + _regular(6.0, t0=4.8, t1=8.3)
    r = _score(truth)
    assert r["scoreable"], r["reason"]
    assert r["rhythm_cv_pct"] < 5.0, r["rhythm_cv_pct"]
    kept = [t for t in truth if t >= TASK.trim_s]
    assert r["n_intervals"] == len(kept) - 2, r    # n-1 intervals, one pause dropped


def test_slowing_down_shows_as_negative_decrement():
    times, t, gap = [], 0.3, 1 / 7.0
    while t < 8.3:
        times.append(t)
        t += gap
        gap *= 1.012
    r = _score(times)
    assert r["scoreable"], r["reason"]
    assert r["decrement_pct_per_s"] < -2.0, r["decrement_pct_per_s"]


def test_too_few_syllables_is_unscoreable_with_a_reason():
    r = _score([0.5, 1.0, 1.5, 2.0])
    assert not r["scoreable"]
    assert r["reason"].startswith("Only 4 syllables detected")


def test_silence_is_unscoreable_with_a_reason():
    x = RNG.normal(0, 0.001, 8 * SR).astype(np.float32)
    r = compute_metrics(TASK, [], 0.0, 8.0, snr_db=None, clip_frac=0.0)
    assert not r["scoreable"] and r["reason"].startswith("No speech")
    assert on.clipping_fraction(x) == 0.0


def test_heavy_clipping_is_unscoreable():
    syl = [Syllable(0.2 + i * 0.15, 0.25 + i * 0.15, -10, 20) for i in range(40)]
    r = compute_metrics(TASK, syl, 0.0, 8.0, snr_db=30, clip_frac=0.1)
    assert not r["scoreable"] and "clipping" in r["reason"]


def test_low_snr_is_unscoreable():
    syl = [Syllable(0.2 + i * 0.15, 0.25 + i * 0.15, -10, 20) for i in range(40)]
    r = compute_metrics(TASK, syl, 0.0, 8.0, snr_db=8.0, clip_frac=0.0)
    assert not r["scoreable"] and "noisy" in r["reason"]


def test_npvi_known_values():
    assert npvi([100, 100, 100]) == 0.0
    # |100-200| / 150 = 0.667 each pair → 66.7
    assert abs(npvi([100, 200, 100]) - 66.667) < 0.01
    # a dropped interval breaks the pairs either side of it
    assert npvi([100, None, 100]) is None


def test_bands_follow_the_task():
    assert band(TASK.cv_typical - 1, TASK)[0] == "success"
    assert band(TASK.cv_typical + 1, TASK)[0] == "warning"
    assert band(TASK.cv_monitor + 1, TASK)[0] == "danger"


def test_confidence_drops_with_noise():
    base = _score(_regular(6.0))
    syl = [Syllable(0.3 + i / 6, 0.32 + i / 6, -10, 20) for i in range(48)]
    noisy = compute_metrics(TASK, syl, 0.0, 8.6, snr_db=14.0, clip_frac=0.0)
    assert noisy["scoreable"]
    assert noisy["confidence_pct"] < base["confidence_pct"]
    assert any("noise" in r for r in noisy["confidence_reasons"])


# ── Phoneme recogniser: the pure half ──────────────────────────────────────

ID2TOK = {0: "<pad>", 1: "p", 2: "a", 3: "t", 4: "k", 5: "|", 6: "tʰ"}


def test_ctc_collapses_runs_and_drops_blanks():
    ids = [0, 1, 1, 0, 2, 2, 2, 0, 1, 0, 2]
    phones = ph.ctc_segments(ids, [0.9] * len(ids), 0, ID2TOK)
    assert [p.label for p in phones] == ["p", "a", "p", "a"]
    assert abs(phones[0].start_s - 0.02) < 1e-9 and abs(phones[0].end_s - 0.06) < 1e-9


def test_repeated_symbol_across_a_blank_is_two_phones():
    phones = ph.ctc_segments([1, 0, 1], [1.0] * 3, 0, ID2TOK)
    assert [p.label for p in phones] == ["p", "p"]


def test_word_delimiter_is_skipped():
    phones = ph.ctc_segments([1, 5, 2], [1.0] * 3, 0, ID2TOK)
    assert [p.label for p in phones] == ["p", "a"]


def test_consonants_map_to_syllables_including_diacritics():
    assert ph.syllable_of("p") == "pa"
    assert ph.syllable_of("tʰ") == "ta"
    assert ph.syllable_of("ɡ") == "ka"       # IPA script g, U+0261
    assert ph.syllable_of("a") is None
    assert ph.syllable_of("") is None


def test_sequence_errors_count_transitions_for_pataka():
    good = ["pa", "ta", "ka"] * 5
    assert ph.sequence_errors(good, ("pa", "ta", "ka"))["errors"] == 0
    slip = ["pa", "ta", "ka", "pa", "ka", "ta", "ka", "pa", "ta", "ka"]
    r = ph.sequence_errors(slip, ("pa", "ta", "ka"))
    # pa→ka and ka→ta are wrong; everything after the slip realigns
    assert r["errors"] == 2 and r["n"] == 9, r


def test_sequence_errors_for_a_single_syllable_task():
    r = ph.sequence_errors(["pa", "pa", "ta", "pa"], ("pa",))
    assert r["errors"] == 1 and r["n"] == 4


def test_ml_readings_are_merged_into_the_metrics():
    truth = _regular(6.0)
    x = _train(truth, 8.6)
    syl, _, _, floor = _detect(x)
    labels = [("pa", "ta", "ka")[i % 3] for i in range(len(truth))]
    labels[20] = "pa"                                  # one slip
    ml = {"syllables": list(zip(labels, truth))}
    r = compute_metrics(TASK, syl, 0.0, 8.6, snr_db=on.snr_db(syl, floor),
                        clip_frac=0.0, ml=ml)
    assert r["scoreable"]
    assert r["ml_syllables"] == len(truth)
    assert r["count_agreement_pct"] == 100.0
    assert 0 < r["sequence_error_pct"] < 10, r["sequence_error_pct"]


def test_count_agreement():
    assert ph.count_agreement_pct(40, 40) == 100.0
    assert ph.count_agreement_pct(30, 40) == 75.0
    assert ph.count_agreement_pct(0, 0) is None


def test_availability_check_never_raises():
    ok, why = ph.available()
    assert isinstance(ok, bool) and (ok or why)


# ── Sustained phonation ────────────────────────────────────────────────────

from core.speech import phonation as phon
from core.speech.tasks import PHONATION

PHON_SR = 44100


def _contour(seconds=4.0, f0=150.0, wobble_pct=0.0, wobble_hz=5.0, drift=0.0):
    t = np.arange(int(seconds / phon.PITCH_STEP_S)) * phon.PITCH_STEP_S
    return list(f0 * (1 + wobble_pct / 100 * np.sin(2 * np.pi * wobble_hz * t))
                + drift * t)


def _vowel(seconds=6.0, f0=140.0, period_sd=0.0, level=0.3, seed=3):
    """A vowel built cycle by cycle, so the period sequence — and therefore
    jitter — is known. Local jitter of i.i.d. period noise with relative SD σ
    is E|ε_i − ε_i+1| = 2σ/√π ≈ 1.13σ."""
    rng = np.random.default_rng(seed)
    out, total = [], 0
    while total < seconds * PHON_SR:
        n = int(round(PHON_SR / f0 * (1 + rng.normal(0, period_sd))))
        t = np.arange(n) / n
        cyc = sum(np.sin(2 * np.pi * k * t) / k for k in range(1, 12))
        out.append(cyc)
        total += n
    x = np.concatenate(out)[:int(seconds * PHON_SR)]
    return (level * x / np.max(np.abs(x))).astype(np.float32)


def test_tremor_finds_a_known_wobble():
    hz, amp = phon.vocal_tremor(_contour(wobble_pct=3.0, wobble_hz=5.0))
    assert abs(hz - 5.0) < 0.5, hz
    assert abs(amp - 3.0 / np.sqrt(2)) < 0.3, amp


def test_tremor_ignores_a_slow_drift():
    hz, amp = phon.vocal_tremor(_contour(drift=4.0))
    assert amp < 0.1, amp


def test_tremor_needs_enough_contour():
    assert phon.vocal_tremor(_contour(seconds=1.0)) == (None, None)


def test_tremor_uses_the_longest_voiced_run():
    f = _contour(seconds=5.0, wobble_pct=3.0, wobble_hz=6.0)
    f[100:110] = [0.0] * 10                   # a 0.1 s voice break at 1 s
    hz, amp = phon.vocal_tremor(f)
    assert abs(hz - 6.0) < 0.6, hz


def _meas(jitter=0.5, voiced_frames=400, frames=450):
    return {"jitter_pct": jitter, "shimmer_pct": 3.0, "hnr_db": 20.0,
            "f0_hz": [150.0] * voiced_frames + [0.0] * (frames - voiced_frames)}


def test_phonation_scores_a_clean_vowel():
    r = phon.compute_metrics(PHONATION, _meas(), snr_db=35, clip_frac=0.0)
    assert r["scoreable"], r["reason"]
    assert r["status"] == "success" and r["confidence_pct"] > 75


def test_phonation_bands_follow_the_task():
    t = PHONATION
    assert phon.band(t.jitter_typical - 0.1, t)[0] == "success"
    assert phon.band(t.jitter_typical + 0.1, t)[0] == "warning"
    assert phon.band(t.jitter_monitor + 0.1, t)[0] == "danger"


def test_phonation_gates():
    no_voice = phon.compute_metrics(PHONATION, _meas(voiced_frames=0),
                                    snr_db=35, clip_frac=0.0)
    assert not no_voice["scoreable"] and no_voice["reason"].startswith("No steady")
    clipped = phon.compute_metrics(PHONATION, _meas(), snr_db=35, clip_frac=0.1)
    assert not clipped["scoreable"] and "clipping" in clipped["reason"]
    noisy = phon.compute_metrics(PHONATION, _meas(), snr_db=10, clip_frac=0.0)
    assert not noisy["scoreable"] and "noisy" in noisy["reason"]
    short = phon.compute_metrics(PHONATION, _meas(voiced_frames=150),
                                 snr_db=35, clip_frac=0.0)
    assert not short["scoreable"]
    assert short["reason"].startswith("Only 1.5 s of steady voice"), short["reason"]


def test_phonation_confidence_falls_with_voice_breaks():
    clean = phon.compute_metrics(PHONATION, _meas(), snr_db=35, clip_frac=0.0)
    broken = phon.compute_metrics(PHONATION, _meas(voiced_frames=300),
                                  snr_db=35, clip_frac=0.0)
    assert broken["confidence_pct"] < clean["confidence_pct"]


def test_praat_measures_known_jitter():
    """End to end through Praat. Skipped where parselmouth is not installed."""
    if not phon.available():
        print("        (skipped: praat-parselmouth not installed)")
        return
    steady = phon.measure(_vowel(), PHON_SR, PHONATION)
    shaky = phon.measure(_vowel(period_sd=0.02), PHON_SR, PHONATION)
    assert steady["jitter_pct"] < 0.3, steady["jitter_pct"]
    assert 1.5 < shaky["jitter_pct"] < 3.2, shaky["jitter_pct"]
    f0 = [f for f in steady["f0_hz"] if f > 0]
    assert abs(np.mean(f0) - 140.0) < 3.0, np.mean(f0)
    r = phon.compute_metrics(PHONATION, shaky, snr_db=40, clip_frac=0.0)
    assert r["scoreable"] and r["status"] == "danger", r


# ── Registry ───────────────────────────────────────────────────────────────

def test_tasks_are_self_consistent():
    for key, task in TASKS.items():
        assert task.key == key
        assert task.cv_typical < task.cv_monitor
        assert task.trim_s < task.duration_s
        assert task.min_effort_hz < task.max_rate_hz
        assert task.cycle and task.instructions


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:                 # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
