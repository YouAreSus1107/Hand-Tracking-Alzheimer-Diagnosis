"""
Waveform → syllables, from the amplitude envelope alone (SPEECH_TEST_PLAN.md
§3.1). Pure NumPy, no I/O: the counterpart of core/tapping/detector.py, and
unit-tested against synthetic syllable trains in screening_tests/tests/
test_speech.py.

Why the envelope and not a model. Energy-based syllable detection is the
method validated against manual DDK scoring (τb ≈ 0.7-0.84, JSLHR 2022), it
is deterministic, and it needs nothing but the microphone. A DDK syllable is a
stop closure (near-silence) followed by a vowel (loud), so the envelope is a
train of well-separated peaks and the job is peak picking with sensible
guards. The optional phoneme recogniser (phonemes.py) is a cross-check on top
of this, never a replacement for it.

The plan named librosa for this. It is not used: its onset detector is tuned
for musical note onsets, and it would pull in numba + scipy for what is a
~60-line envelope. The method is the same energy envelope either way.

Pipeline
  1. frame RMS (25 ms window, 10 ms hop), DC removed per frame, in dBFS
  2. 3-frame moving average (30 ms) to take the ripple off a vowel
  3. peaks: local maxima that clear the noise floor by MIN_SNR_DB, stand
     MIN_PROMINENCE_DB above the valleys either side, and are no closer than
     the task's fastest plausible syllable (the debounce)
  4. each syllable's onset = where the rise from its left valley crosses
     halfway to its peak, interpolated between frames — mid-rise is far less
     sensitive to the noise floor than the foot of the rise
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

WIN_S = 0.025
HOP_S = 0.010
SMOOTH_FRAMES = 3
MIN_SNR_DB = 10.0           # a syllable peak must clear the floor by this
MIN_PROMINENCE_DB = 6.0     # ...and dip at least this far between syllables
DYNAMIC_RANGE_DB = 30.0     # ignore peaks this far below the loudest one
ONSET_FRAC = 0.5            # onset = crossing this fraction of the rise
SPLIT_FRAC = 0.5            # onsets closer than this × the typical gap are
                            # one syllable split in two (merge_split_syllables)
SPLIT_REF_PCT = 75.0        # "typical gap" = this percentile of all gaps
FLOOR_PERCENTILE = 10.0     # envelope percentile used as the noise floor
SILENCE_DB = -100.0         # dBFS assigned to digital silence

CLIP_LEVEL = 0.99           # |sample| at or above this counts as clipped


@dataclass(frozen=True)
class Syllable:
    onset_s: float          # energy onset (mid-rise), seconds from buffer start
    peak_s: float           # vowel peak
    peak_db: float          # envelope level at the peak, dBFS
    prominence_db: float    # peak above the higher of its two valleys


def to_dbfs(rms: np.ndarray | float) -> np.ndarray | float:
    return 20.0 * np.log10(np.maximum(rms, 10 ** (SILENCE_DB / 20.0)))


def rms_dbfs(block: np.ndarray) -> float:
    """Level of one audio block in dBFS. Empty → silence."""
    if block.size == 0:
        return SILENCE_DB
    x = block.astype(np.float64)
    return float(to_dbfs(np.sqrt(np.mean((x - x.mean()) ** 2))))


def peak_dbfs(block: np.ndarray) -> float:
    if block.size == 0:
        return SILENCE_DB
    return float(to_dbfs(float(np.max(np.abs(block)))))


def clipping_fraction(samples: np.ndarray) -> float:
    """Share of samples at full scale. A clipped vowel flattens the envelope
    peak and hides the dip before the next syllable."""
    if samples.size == 0:
        return 0.0
    return float(np.mean(np.abs(samples) >= CLIP_LEVEL))


def envelope(samples: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """(frame centre times in s, smoothed RMS envelope in dBFS)."""
    x = np.asarray(samples, dtype=np.float64).ravel()
    win = max(1, int(round(WIN_S * sr)))
    hop = max(1, int(round(HOP_S * sr)))
    if x.size < win:
        return np.zeros(0), np.zeros(0)
    n = 1 + (x.size - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx]
    frames = frames - frames.mean(axis=1, keepdims=True)
    db = to_dbfs(np.sqrt(np.mean(frames ** 2, axis=1)))
    if SMOOTH_FRAMES > 1 and n >= SMOOTH_FRAMES:
        kernel = np.ones(SMOOTH_FRAMES) / SMOOTH_FRAMES
        pad = SMOOTH_FRAMES // 2
        db = np.convolve(np.pad(db, pad, mode="edge"), kernel, mode="valid")
    times = (np.arange(n) * hop + win / 2) / sr
    return times, db


def noise_floor_db(env_db: np.ndarray) -> float:
    if env_db.size == 0:
        return SILENCE_DB
    return float(np.percentile(env_db, FLOOR_PERCENTILE))


def _prominences(env: np.ndarray, peaks: list[int]) -> list[tuple[float, int, int]]:
    """(prominence, left valley index, right valley index) per peak, measured
    the scipy way: each side's valley is the minimum between the peak and the
    nearest point that is higher than it (or the signal edge)."""
    out = []
    n = env.size
    for p in peaks:
        h = env[p]
        i = p
        while i > 0 and env[i - 1] <= h:
            i -= 1
        left = p - int(np.argmin(env[i:p + 1][::-1]))
        j = p
        while j < n - 1 and env[j + 1] <= h:
            j += 1
        right = p + int(np.argmin(env[p:j + 1]))
        out.append((h - max(env[left], env[right]), left, right))
    return out


def detect_syllables(samples: np.ndarray, sr: int, *, min_gap_s: float,
                     floor_db: float | None = None
                     ) -> tuple[list[Syllable], np.ndarray, np.ndarray, float]:
    """Find syllables in a mono buffer.

    `floor_db` is the ambient level measured during the mic check; when not
    given it is estimated from the recording itself (its quietest decile —
    the closures between syllables). Returns (syllables, envelope times,
    envelope dB, floor used).
    """
    times, env = envelope(samples, sr)
    if env.size < 3:
        return [], times, env, SILENCE_DB
    own = noise_floor_db(env)
    # The recording's own quiet stretches are the better floor when they are
    # louder than the mic-check measurement (a fan switched on, someone talked
    # during the check) — never pick peaks against an optimistic floor.
    floor = own if floor_db is None else max(float(floor_db), own - 3.0)

    cand = [i for i in range(1, env.size - 1)
            if env[i] >= env[i - 1] and env[i] > env[i + 1]]
    if not cand:
        return [], times, env, floor
    top = max(env[i] for i in cand)
    cand = [i for i in cand
            if env[i] >= floor + MIN_SNR_DB and env[i] >= top - DYNAMIC_RANGE_DB]
    prom = dict(zip(cand, _prominences(env, cand)))
    cand = [i for i in cand if prom[i][0] >= MIN_PROMINENCE_DB]

    # Debounce: of two peaks closer than the fastest plausible syllable, the
    # louder one is the vowel and the other is a burst or ripple on it.
    min_gap = max(1, int(round(min_gap_s / HOP_S)))
    kept: list[int] = []
    for i in sorted(cand, key=lambda k: -env[k]):
        if all(abs(i - k) >= min_gap for k in kept):
            kept.append(i)
    kept.sort()

    syllables = []
    for i, p in enumerate(kept):
        # Left valley: the lowest point since the previous kept peak — not the
        # prominence valley, which may reach back past a quieter syllable.
        lo = kept[i - 1] if i else max(0, p - 4 * min_gap)
        valley = lo + int(np.argmin(env[lo:p + 1]))
        level = env[valley] + ONSET_FRAC * (env[p] - env[valley])
        k = p
        while k > valley and env[k - 1] >= level:
            k -= 1
        if k > valley and env[k] != env[k - 1]:
            frac = (level - env[k - 1]) / (env[k] - env[k - 1])
            onset = times[k - 1] + frac * (times[k] - times[k - 1])
        else:
            onset = times[k]
        syllables.append(Syllable(onset_s=float(onset), peak_s=float(times[p]),
                                  peak_db=float(env[p]),
                                  prominence_db=float(prom[p][0])))
    return merge_split_syllables(syllables), times, env, floor


def merge_split_syllables(syllables: list[Syllable],
                          frac: float = SPLIT_FRAC) -> list[Syllable]:
    """Fold a syllable the envelope counted twice back into one.

    An aspirated stop — the "k" of "ka" above all, and every stop in a Mandarin
    accent, where ㄆ ㄊ ㄎ are all aspirated — releases a burst of air that
    can stand as its own quieter peak, a near-silent dip, then the vowel
    100-200 ms later. The fixed debounce cannot catch it: 150 ms is a plausible
    syllable gap for a fast speaker and an impossible one for a slow speaker.
    So the test is relative to the person's own pace, the way the tapping
    detector's envelope is: two onsets closer than `frac` of the typical gap
    are one syllable, and the louder peak — the vowel, which is what every other
    syllable's onset is anchored to — is the one kept.

    The typical gap is the 75th percentile, not the median: with a split on
    every third syllable a quarter of all gaps are the short burst-to-vowel
    ones and another quarter the shortened gap before them, which drags the
    median down until the limit falls below the very gaps it has to catch.

    Found on real runs (2026-09-25): a split "ka" every third syllable turned a
    3% CV run into a 30% one.
    """
    if len(syllables) < 4:
        return syllables
    gaps = [b.onset_s - a.onset_s for a, b in zip(syllables, syllables[1:])]
    limit = frac * float(np.percentile(gaps, SPLIT_REF_PCT))
    out = [syllables[0]]
    for s in syllables[1:]:
        if s.onset_s - out[-1].onset_s < limit:
            if s.peak_db > out[-1].peak_db:
                out[-1] = s
        else:
            out.append(s)
    return out


def snr_db(syllables: list[Syllable], floor_db: float) -> float | None:
    """Median syllable peak over the noise floor."""
    if not syllables:
        return None
    return float(np.median([s.peak_db for s in syllables]) - floor_db)
