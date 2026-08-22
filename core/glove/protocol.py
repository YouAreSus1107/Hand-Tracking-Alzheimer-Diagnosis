"""Sensor-glove wire protocol — pure parsing, no I/O.

Implements the frame and banner format specified in
``docs/GLOVE_FIRMWARE_PLAN.md`` §4 and emitted by ``firmware/glove/glove.ino``.

Everything here is deliberately hardware-free and total: no function raises on
malformed input, they return ``None`` instead. A glove on a USB cable produces
truncated lines whenever a read straddles a frame boundary, so "returns None"
is the normal path, not an error path.

Unit-tested in ``screening_tests/tests/test_glove.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Wire-format version this parser understands. The firmware announces its own
# in the boot banner; a mismatch means the column layout may have changed and
# frames must not be trusted.
PROTO_SUPPORTED = 1

_UINT32 = 0xFFFFFFFF

# A sequence jump larger than this is read as a counter reset (the 'Z' command)
# or line corruption rather than that many genuinely dropped frames. At 100 Hz
# this is ~2.8 hours of continuous loss, which never happens in practice.
_MAX_SANE_GAP = 1_000_000


@dataclass(frozen=True)
class GloveBanner:
    """Parsed ``#GLOVE ...`` boot banner.

    ``cols`` is the authoritative column layout — consumers should read channel
    names from here rather than hardcoding them, so adding sensors to the
    firmware's CHANNELS[] table needs no host-side change.
    """

    fw: str = ""
    proto: int = 0
    board: str = ""
    rate: int = 0
    adc_bits: int = 10
    adc_ref_mv: int = 3300
    vdiv_mv: int = 3300
    r_fixed: int = 10000
    imu: str = "none"
    emg: int = 0
    cols: tuple[str, ...] = ()

    @property
    def channels(self) -> tuple[str, ...]:
        """Sensor column names — everything after the seq/t_us housekeeping."""
        return self.cols[2:] if len(self.cols) > 2 else ()

    @property
    def supported(self) -> bool:
        return self.proto == PROTO_SUPPORTED

    @property
    def adc_max(self) -> int:
        return (1 << self.adc_bits) - 1


@dataclass(frozen=True)
class GloveFrame:
    """One sampled timestep. ``values`` holds raw ADC counts, one per channel."""

    seq: int
    t_us: int
    values: tuple[int, ...]


def _to_int(text: str, default: int = 0) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def parse_banner(line: str) -> GloveBanner | None:
    """Parse a ``#GLOVE k=v k=v ...`` banner. Returns None if it isn't one."""
    if not line:
        return None
    line = line.strip()
    if not line.startswith("#GLOVE"):
        return None

    kv: dict[str, str] = {}
    for token in line[len("#GLOVE"):].split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        kv[key] = value

    cols = tuple(c for c in kv.get("cols", "").split(",") if c)
    return GloveBanner(
        fw=kv.get("fw", ""),
        proto=_to_int(kv.get("proto", "0")),
        board=kv.get("board", ""),
        rate=_to_int(kv.get("rate", "0")),
        adc_bits=_to_int(kv.get("adc_bits", "10"), 10) or 10,
        adc_ref_mv=_to_int(kv.get("adc_ref_mv", "3300"), 3300),
        vdiv_mv=_to_int(kv.get("vdiv_mv", "3300"), 3300),
        r_fixed=_to_int(kv.get("r_fixed", "10000"), 10000),
        imu=kv.get("imu", "none"),
        emg=_to_int(kv.get("emg", "0")),
        cols=cols,
    )


def parse_frame(line: str, n_values: int | None = None) -> GloveFrame | None:
    """Parse a ``G,seq,t_us,v0,...`` data frame.

    ``n_values`` is the expected channel count from the banner; a frame with a
    different count is rejected rather than silently mapped onto the wrong
    columns. Pass ``None`` to accept whatever arrives (used before the banner
    is known).
    """
    if not line:
        return None
    line = line.strip()
    if not line.startswith("G,"):
        return None

    parts = line.split(",")
    if len(parts) < 3:
        return None
    if n_values is not None and len(parts) != n_values + 3:
        return None

    try:
        seq = int(parts[1])
        t_us = int(parts[2])
        values = tuple(int(p) for p in parts[3:])
    except ValueError:
        return None

    if seq < 0 or t_us < 0:
        return None
    return GloveFrame(seq=seq, t_us=t_us, values=values)


def seq_gap(prev: int, cur: int) -> int:
    """Frames lost between two sequence numbers, wrap-safe.

    The firmware's counter is a uint32 and is also reset to 0 by the 'Z'
    command, so an implausible jump is reported as 0 loss rather than billions.
    """
    delta = (cur - prev) & _UINT32
    if delta == 0 or delta > _MAX_SANE_GAP:
        return 0
    return delta - 1


def us_delta(prev: int, cur: int) -> int:
    """Microseconds between two device timestamps, wrap-safe (uint32, ~71 min)."""
    return (cur - prev) & _UINT32


def adc_to_mv(adc: int, ref_mv: int = 3300, bits: int = 10) -> int:
    """ADC counts → millivolts.

    Uses integer division to match the firmware's ``adcToMillivolts()`` exactly,
    so the page and the board's own ``#DIAG`` output never disagree.
    """
    full = (1 << bits) - 1
    if full <= 0:
        return 0
    return (adc * ref_mv) // full


def sensor_ohms(adc: int, ref_mv: int = 3300, vdiv_mv: int = 3300,
                r_fixed: int = 10000, bits: int = 10) -> int | None:
    """Divider resistance of the sensor leg, in ohms.

    ``R_sensor = R_fixed * (Vsupply - Vout) / Vout``. Returns ``None`` for an
    open sensor (0 mV), and 0 at or above the supply rail. Mirrors the
    firmware's ``sensorOhms()``.
    """
    mv = adc_to_mv(adc, ref_mv, bits)
    if mv <= 0:
        return None
    if mv >= vdiv_mv:
        return 0
    return (r_fixed * (vdiv_mv - mv)) // mv


@dataclass
class FrameAccumulator:
    """Feeds raw serial lines in, yields frames and stream health out.

    Stateful but pure — no I/O — so a recorded capture can be replayed through
    it in a unit test.
    """

    banner: GloveBanner | None = None
    total: int = 0
    dropped: int = 0
    _prev_seq: int | None = field(default=None, repr=False)
    _window: list[tuple[int, int]] = field(default_factory=list, repr=False)

    #: frames retained for the rolling rate estimate
    WINDOW = 200

    def feed(self, line: str) -> GloveFrame | None:
        """Consume one line. Returns a frame, or None for banners/noise."""
        banner = parse_banner(line)
        if banner is not None:
            self.banner = banner
            return None

        n = len(self.banner.channels) if self.banner else None
        frame = parse_frame(line, n)
        if frame is None:
            return None

        if self._prev_seq is not None:
            self.dropped += seq_gap(self._prev_seq, frame.seq)
        self._prev_seq = frame.seq
        self.total += 1

        self._window.append((frame.seq, frame.t_us))
        if len(self._window) > self.WINDOW:
            del self._window[0]
        return frame

    def reset_counters(self) -> None:
        """Clear stream stats — used after a 'Z' zero command."""
        self.total = 0
        self.dropped = 0
        self._prev_seq = None
        self._window.clear()

    @property
    def rate_hz(self) -> float:
        """Measured sample rate from device timestamps, 0.0 until enough data."""
        if len(self._window) < 2:
            return 0.0
        (first_seq, first_us), (last_seq, last_us) = self._window[0], self._window[-1]
        span_us = us_delta(first_us, last_us)
        span_seq = (last_seq - first_seq) & _UINT32
        if span_us <= 0 or span_seq <= 0 or span_seq > _MAX_SANE_GAP:
            return 0.0
        return span_seq / (span_us / 1_000_000.0)
