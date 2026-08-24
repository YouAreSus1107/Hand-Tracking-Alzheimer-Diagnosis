"""Onboard-IMU maths for the sensor glove. Pure, stdlib-only, no I/O.

The counterpart to :mod:`core.glove.force` and :mod:`core.glove.flex`, for the
Nano 33 BLE's built-in accelerometer and gyroscope (GLOVE_FIRMWARE_PLAN.md §5d).
The firmware emits six integer columns in milli-units; everything here turns
those into physical units and into the one derived readout the IMU exists for:
**hand tremor**, the 3.5-12 Hz component of the acceleration magnitude.

Why this module carries the tremor maths rather than the frontend: the same
numbers have to be computed identically for the live page, for a recorded
session, and eventually for camera/glove fusion (ROADMAP §3). One
implementation, unit-tested without hardware, is the only way those three can
agree.

**Stdlib only, deliberately.** ``core/spiral/metrics.py`` does the equivalent
spectral work with numpy, but this module is imported by ``launcher.py``'s
Developer page, which must keep running on an install that has never touched
the camera stack. The DFT below is evaluated at the handful of bins the band
actually covers, so the cost is trivial at these window sizes.
"""

from __future__ import annotations

import math

#: Tremor analysis band, Hz. The same band as
#: ``core.spiral.metrics.TREMOR_BAND`` — restated rather than imported, because
#: that module needs numpy and this one must not. **If one moves, move both.**
#: The lower edge sits above voluntary hand motion; the upper edge covers
#: physiological and pathological hand tremor.
TREMOR_BAND = (3.5, 12.0)

#: Shortest window that can support a claim about a 3.5 Hz component. Two
#: seconds is seven cycles at the band's lower edge — below that the estimate
#: is dominated by the window, not the signal.
MIN_WINDOW_S = 2.0

#: How far the acceleration magnitude may sit from 1 g and still be treated as
#: "the hand is still, so this vector is gravity". Tilt is only meaningful
#: under that assumption; during real movement the vector is gravity plus
#: whatever the hand is doing, and reporting an angle from it is a guess.
STATIC_TOL_G = 0.15

#: Standard gravity is 1.0 in the accelerometer's own units, by definition.
ONE_G = 1.0


def to_units(raw: int | None, scale: int) -> float | None:
    """One raw milli-unit column → g (accelerometer) or °/s (gyroscope).

    ``scale`` comes from the banner's ``imu_scale``; never hardcode it, because
    a firmware that changes the transport scale would otherwise silently
    rescale every reading by a factor of a thousand.
    """
    if raw is None or not scale:
        return None
    return raw / float(scale)


def magnitude(x: float | None, y: float | None, z: float | None) -> float | None:
    """Length of a 3-vector, or None if any axis is missing."""
    if x is None or y is None or z is None:
        return None
    return math.sqrt(x * x + y * y + z * z)


def tilt(ax: float, ay: float, az: float) -> dict:
    """Board orientation from the gravity vector.

    Returns pitch/roll in degrees plus ``static``: whether the magnitude is
    close enough to 1 g for the vector to be gravity alone. **Angles are
    reported for the board's own axes, not the wearer's hand** — how the board
    is mounted on the glove decides what "pitch" means anatomically, and that
    mapping belongs to calibration, not here.

    This is also the gate-5 check in one readout: resting flat, one axis reads
    about ±1 g and the others about 0, and flipping the board flips the sign.
    """
    mag = magnitude(ax, ay, az) or 0.0
    static = abs(mag - ONE_G) <= STATIC_TOL_G
    # atan2 with the horizontal component keeps pitch well-defined through
    # vertical, where a plain ratio would blow up.
    pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az))) if mag else 0.0
    roll = math.degrees(math.atan2(ay, az)) if mag else 0.0
    return {"pitch_deg": pitch, "roll_deg": roll, "magnitude_g": mag,
            "static": static}


def rms(samples) -> float | None:
    """RMS of a signal about its own mean — "how much is this moving"."""
    n = len(samples)
    if n < 2:
        return None
    mean = sum(samples) / n
    return math.sqrt(sum((v - mean) ** 2 for v in samples) / n)


def band_power(samples, fs: float, band=TREMOR_BAND) -> dict | None:
    """Power in ``band`` as a fraction of total, plus the peak frequency.

    Mirrors what ``core/spiral/metrics.compute_tremor`` reports for the camera,
    so a glove tremor reading and a camera tremor reading mean the same thing
    and can be compared directly.

    Returns None — never a number — when the window is too short, the sample
    rate cannot resolve the band, or the signal is flat. A tremor figure
    computed from one second of data would be an artefact of the window.

    Method: detrend, Hann window, then evaluate the DFT only at the bins inside
    the band. Total power comes from Parseval (``N·Σy² − |Y₀|²``, DC excluded)
    rather than summing every bin, which is what keeps this cheap.
    """
    n = len(samples)
    if fs <= 0 or n < 4 or n / fs < MIN_WINDOW_S:
        return None

    lo, hi = band
    nyq = fs / 2.0
    if lo >= nyq:
        return None                      # rate cannot resolve the band at all
    hi = min(hi, nyq * 0.95)
    if hi <= lo:
        return None

    mean = sum(samples) / n
    # Hann window: without it, the window edges leak broadband energy that
    # lands inside the tremor band and inflates the fraction.
    y = [(samples[i] - mean) * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)))
         for i in range(n)]
    sumsq = sum(v * v for v in y)
    if sumsq <= 0:
        return None                      # perfectly flat: nothing to report
    y0 = sum(y)
    total = n * sumsq - y0 * y0          # Parseval, DC bin removed
    if total <= 0:
        return None

    k_lo = max(1, math.ceil(lo * n / fs))
    k_hi = min(n // 2, math.floor(hi * n / fs))
    if k_hi < k_lo:
        return None

    in_band = 0.0
    peak_k, peak_p = k_lo, -1.0
    for k in range(k_lo, k_hi + 1):
        w = 2 * math.pi * k / n
        re = im = 0.0
        for i in range(n):
            re += y[i] * math.cos(w * i)
            im -= y[i] * math.sin(w * i)
        p = re * re + im * im
        # Every bin below Nyquist has a negative-frequency twin; the Nyquist
        # bin itself does not.
        in_band += p if (k == n // 2 and n % 2 == 0) else 2 * p
        if p > peak_p:
            peak_p, peak_k = p, k

    return {
        "band_frac": min(1.0, in_band / total),
        "peak_hz": peak_k * fs / n,
        "band": [lo, hi],
        "n": n,
        "fs": fs,
        "window_s": n / fs,
        "rms": rms(samples),
    }


def held_fraction(triples) -> float | None:
    """Share of samples that repeat the previous one exactly.

    The IMU's own output rate is not locked to the frame grid, so the firmware
    reuses the last reading when nothing new has arrived. A held sample is a
    repeated sample, and repeats flatten exactly the high-frequency content the
    tremor readout is measuring — so this is measured from the data rather than
    trusted from a counter, and reported alongside any spectral figure.

    Three axes agreeing bit-for-bit on consecutive samples effectively does not
    happen for a live sensor, so duplicates are holds rather than stillness.
    """
    n = len(triples)
    if n < 2:
        return None
    held = sum(1 for i in range(1, n) if triples[i] == triples[i - 1])
    return held / (n - 1)
