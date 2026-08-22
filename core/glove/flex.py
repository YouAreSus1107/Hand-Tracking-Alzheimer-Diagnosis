"""Flex-sensor bend estimation. Pure math, no I/O.

The counterpart to :mod:`core.glove.force`, and deliberately more modest than
it, because the underlying data is weaker.

**Why there is no curve here.** ``force.py`` can convert resistance to newtons
because Interlink publishes a typical force curve for the FSR402 with four
anchor points. Bend sensors have no equivalent. Spectra Symbol quotes only a
nominal flat resistance and a nominal range at 90 degrees, both with wide
part-to-part spread, and no transfer function between them. Inventing one would
produce exactly the failure this project keeps guarding against: a modelled
number wearing the costume of a measurement.

**So this reports position within a span, not an angle.** Given a flat and a
fully-bent resistance recorded from the actual sensor on the actual finger,
:func:`bend_fraction` says where in that span the current reading sits, 0 to 1.
That is honest, useful for tracking movement, and needs no datasheet. Degrees
wait for the per-user calibration step (GLOVE_FIRMWARE_PLAN.md gate 9), which
is also where a non-linear correction belongs if measurement shows one is
needed.

**Interpolation is linear in resistance**, not log-log. That is not a claim
about the physics — it is the neutral choice for a normalised readout when the
true shape is unmeasured. ``force.py`` interpolates in log-log space because
the datasheet's own anchors demand it; here there are no anchors to honour.

Unit-tested in ``screening_tests/tests/test_glove.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Provisional span for an unbent/fully-bent Spectra Symbol strip, ohms. These
#: are order-of-magnitude placeholders so the UI has something to show before
#: calibration - NOT specified values. :func:`is_calibrated` reports which span
#: is in use so callers can badge an uncalibrated reading.
NOMINAL_FLAT_OHM = 10_000.0
NOMINAL_BENT_OHM = 110_000.0

#: Minimum ratio between the two ends of a span for it to mean anything. A
#: span narrower than this is noise, not travel, and dividing by it would
#: amplify jitter into a full-scale swing.
MIN_SPAN_RATIO = 1.2

SOURCE = "per-sensor recorded span (no published curve exists for bend sensors)"


@dataclass(frozen=True)
class FlexSpan:
    """The recorded flat and fully-bent resistance for one sensor, in ohms.

    ``calibrated`` is False for the nominal placeholder span, so a reading
    derived from it can be badged rather than presented as measured.
    """

    flat_ohm: float = NOMINAL_FLAT_OHM
    bent_ohm: float = NOMINAL_BENT_OHM
    calibrated: bool = False

    @property
    def usable(self) -> bool:
        """True when the two ends are far enough apart to divide by."""
        lo, hi = self.ordered
        if lo <= 0 or hi <= 0:
            return False
        return hi / lo >= MIN_SPAN_RATIO

    @property
    def ordered(self) -> tuple[float, float]:
        """(smaller, larger) resistance.

        Bending normally *raises* resistance, but the divider can be wired
        either way round and a sensor can be mounted reversed, so the span is
        not assumed to be ascending. Ordering here keeps the arithmetic valid
        either way; :func:`bend_fraction` restores the intended direction.
        """
        a, b = float(self.flat_ohm), float(self.bent_ohm)
        return (a, b) if a <= b else (b, a)


def default_span() -> FlexSpan:
    """The provisional, uncalibrated span."""
    return FlexSpan()


def span_from_ohms(flat_ohm: float | None, bent_ohm: float | None) -> FlexSpan:
    """Build a calibrated span from two recorded resistances.

    Returns the uncalibrated default if either reading is missing or the two
    are too close together to be a real range - the caller gets a usable
    object either way, and :attr:`FlexSpan.calibrated` tells it which it got.
    """
    if flat_ohm is None or bent_ohm is None:
        return default_span()
    span = FlexSpan(flat_ohm=float(flat_ohm), bent_ohm=float(bent_ohm),
                    calibrated=True)
    if not span.usable:
        return default_span()
    return span


def bend_fraction(r_ohm: float | None, span: FlexSpan | None = None) -> float | None:
    """Where the current resistance sits in the span, 0.0 (flat) to 1.0 (bent).

    Clamped to that range: past either end the sensor has left the span it was
    calibrated over, and extrapolating would invent travel that was never
    measured. Returns None for an open sensor or an unusable span.
    """
    if r_ohm is None or r_ohm <= 0:
        return None
    span = span or default_span()
    if not span.usable:
        return None

    flat, bent = float(span.flat_ohm), float(span.bent_ohm)
    if bent == flat:  # pragma: no cover - excluded by span.usable
        return None
    t = (float(r_ohm) - flat) / (bent - flat)
    return max(0.0, min(1.0, t))


def bend_percent(r_ohm: float | None, span: FlexSpan | None = None) -> float | None:
    """:func:`bend_fraction` as 0-100, the unit the dev page shows."""
    frac = bend_fraction(r_ohm, span)
    return None if frac is None else frac * 100.0


def bend_range(r_ohm: float | None, span: FlexSpan | None = None) -> str:
    """Classify a reading against the recorded span.

    ``"open"`` no signal - a disconnected or open sensor ·
    ``"below"`` straighter than the recorded flat end ·
    ``"in"`` inside the span · ``"above"`` bent past the recorded bent end.

    The outer two matter: they mean the reading is clamped, so the fraction has
    stopped tracking movement and the span needs re-recording.
    """
    if r_ohm is None or r_ohm <= 0:
        return "open"
    span = span or default_span()
    if not span.usable:
        return "open"
    lo, hi = span.ordered
    # Direction-aware: "below" always means the flat end, whichever way the
    # span runs.
    flat_is_low = span.flat_ohm <= span.bent_ohm
    if r_ohm < lo:
        return "below" if flat_is_low else "above"
    if r_ohm > hi:
        return "above" if flat_is_low else "below"
    return "in"


def is_calibrated(span: FlexSpan | None = None) -> bool:
    """Whether a reading from this span is measured or merely provisional."""
    span = span or default_span()
    return bool(span.calibrated and span.usable)


def flex_model(span: FlexSpan | None = None) -> dict:
    """The span and its metadata, for transport to the frontend.

    Mirrors :func:`core.glove.force.force_model` so the dev page can treat the
    two sensor kinds symmetrically: server owns the numbers, page only renders.
    """
    span = span or default_span()
    return {
        "flat_ohm": span.flat_ohm,
        "bent_ohm": span.bent_ohm,
        "calibrated": is_calibrated(span),
        "usable": span.usable,
        "source": SOURCE,
    }
