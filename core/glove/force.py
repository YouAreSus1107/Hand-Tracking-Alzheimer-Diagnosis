"""FSR402 resistance → force estimation. Pure math, no I/O.

Turns the divider resistance computed by :mod:`core.glove.protocol` into an
approximate force, using the **published** Interlink FSR402 typical force curve
rather than a home-grown guess.

Source of the curve — Interlink FSR402 datasheet Figure 1 (Force Curve), the
same four points transcribed in Adafruit's *Using an FSR* guide:

    0.2 N -> 30 kOhm      1 N -> 6 kOhm
     10 N ->  1 kOhm    100 N -> 250 Ohm

  https://cdn.sparkfun.com/assets/8/a/1/2/0/2010-10-26-DataSheet-FSR402-Layout2.pdf
  https://learn.adafruit.com/force-sensitive-resistor-fsr/using-an-fsr

**Why piecewise log-log and not one power law.** The datasheet describes the
sensor as following "an inverse power law" only at intermediate forces, and it
shows: fitting a single global ``R = a * F**-b`` to the four points above gives
``R = 7138 * F**-0.765`` with residuals of roughly +/-20%. Interpolating
linearly in log-log space instead is *exact* at every published anchor and still
behaves as a local power law between them, which is what the curve actually is.

**Accuracy.** The curve is a *typical* part. Interlink specs force repeatability
at +/-2% for a single part and +/-6% part-to-part within a batch, so treat the
output as indicative to roughly +/-10%, not as a calibrated load cell. Outside
the rated 0.2-20 N band the manufacturer specifies nothing, which is why
:func:`force_range` exists — callers are expected to badge those readings rather
than print a confident number.

A future per-sensor calibration layer (GLOVE_FIRMWARE_PLAN.md, `calibrate.py`)
can override :data:`FSR402_CURVE` with measured points; nothing else changes,
because every function here derives from that table.
"""

from __future__ import annotations

import math

#: Published typical curve as (force in newtons, resistance in ohms), ascending
#: force. This table is the single source of truth for the whole module.
FSR402_CURVE: tuple[tuple[float, float], ...] = (
    (0.2, 30000.0),
    (1.0, 6000.0),
    (10.0, 1000.0),
    (100.0, 250.0),
)

#: Datasheet "force sensitivity range" — the band the part is specified over.
RATED_MIN_N = 0.2
RATED_MAX_N = 20.0

#: Datasheet force repeatability, percent.
SINGLE_PART_PCT = 2
PART_TO_PART_PCT = 6

SOURCE = "Interlink FSR402 datasheet typical force curve"

#: Standard gravity, for the kilogram-force conversion people actually intuit.
G0 = 9.80665


def conductance_us(r_ohm: float | None) -> float | None:
    """Conductance in microsiemens. Exact — needs no calibration.

    Conductance is roughly proportional to force over much of the FSR's range,
    which is why it is worth showing alongside the force estimate: it is a
    measured quantity, whereas force is a modelled one.
    """
    if r_ohm is None or r_ohm <= 0:
        return None
    return 1_000_000.0 / r_ohm


def force_newtons(r_ohm: float | None) -> float | None:
    """Approximate force in newtons for a sensor resistance.

    Linear interpolation in log(force)/log(resistance) space across
    :data:`FSR402_CURVE`; the outer segments extrapolate at their own slope.
    Returns ``None`` for an open (unpressed) sensor.
    """
    if r_ohm is None:
        return None
    if r_ohm <= 0:
        # 0 means at/past the supply rail (see protocol.sensor_ohms). Clamp to
        # the top anchor instead of dividing by zero; force_range reports
        # "above" so the caller still knows not to trust the figure.
        return FSR402_CURVE[-1][0] if r_ohm == 0 else None

    pts = FSR402_CURVE
    last = len(pts) - 2          # index of the final segment

    # Resistance descends as force ascends, so the table is walked by
    # resistance. Outside the anchors we clamp to an end segment, which
    # extrapolates along that segment's slope.
    if r_ohm >= pts[0][1]:
        seg = 0                                  # lighter than the first anchor
    elif r_ohm <= pts[-1][1]:
        seg = last                               # harder than the last anchor
    else:
        seg = last
        for i in range(last + 1):
            if pts[i + 1][1] <= r_ohm <= pts[i][1]:
                seg = i
                break

    lr = math.log(r_ohm)
    f0, r0 = pts[seg]
    f1, r1 = pts[seg + 1]
    lf0, lf1 = math.log(f0), math.log(f1)
    lr0, lr1 = math.log(r0), math.log(r1)
    if lr1 == lr0:  # pragma: no cover - the published table has no duplicates
        return f0
    t = (lr - lr0) / (lr1 - lr0)
    return math.exp(lf0 + t * (lf1 - lf0))


def grams_force(newtons: float | None) -> float | None:
    """Newtons → grams-force, the unit a kitchen scale would show."""
    if newtons is None:
        return None
    return newtons / G0 * 1000.0


def force_range(newtons: float | None) -> str:
    """Classify a force against the datasheet's specified band.

    ``"open"`` no contact · ``"below"`` under the 0.2 N actuation force ·
    ``"rated"`` inside 0.2-20 N · ``"above"`` past 20 N, where the part is
    unspecified and the number should be shown as an upper bound, not a
    measurement.
    """
    if newtons is None:
        return "open"
    if newtons < RATED_MIN_N:
        return "below"
    if newtons > RATED_MAX_N:
        return "above"
    return "rated"


def force_model() -> dict:
    """The curve and its metadata, for transport to the frontend.

    The dev page interpolates these points client-side rather than carrying its
    own copy of the table, so this module stays the only place the curve is
    written down.
    """
    return {
        "points": [[f, r] for f, r in FSR402_CURVE],
        "rated_min_n": RATED_MIN_N,
        "rated_max_n": RATED_MAX_N,
        "tolerance_pct": PART_TO_PART_PCT,
        "source": SOURCE,
    }
