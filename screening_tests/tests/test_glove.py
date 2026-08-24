"""
Unit tests for the glove wire protocol (GLOVE_FIRMWARE_PLAN.md §4 + gate 7):
pure parsing exercised against recorded and synthetic serial lines — no board,
no pyserial.

Run:  python -m pytest screening_tests/tests/test_glove.py
 or:  python screening_tests/tests/test_glove.py   (self-runs without pytest)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.glove.force import (FSR402_CURVE, PART_TO_PART_PCT, RATED_MAX_N,
                              RATED_MIN_N, conductance_us, force_model,
                              force_newtons, force_range, grams_force)
from core.glove.flex import (MIN_SPAN_RATIO, NOMINAL_BENT_OHM,
                             NOMINAL_FLAT_OHM, FlexSpan, bend_fraction,
                             bend_percent, bend_range, default_span,
                             flex_model, is_calibrated, span_from_ohms)
from core.glove.imu import (MIN_WINDOW_S, TREMOR_BAND, band_power,
                            held_fraction, magnitude, rms, tilt, to_units)
from core.glove.protocol import (IMU_COLS, KIND_ACCEL, KIND_FLEX, KIND_FSR,
                                 KIND_GYRO, KIND_UNKNOWN, PROTO_SUPPORTED,
                                 ChannelMeta, FrameAccumulator, adc_to_mv,
                                 kind_from_name, parse_banner, parse_frame,
                                 sensor_ohms, seq_gap, us_delta)

# Captured verbatim from the Nano 33 BLE on COM10, 2026-07-26.
REAL_BANNER = ("#GLOVE fw=0.1.0 proto=1 board=nano33ble rate=100 adc_bits=10 "
               "adc_ref_mv=3300 vdiv_mv=3300 r_fixed=10000 imu=none emg=0 "
               "cols=seq,t_us,p0")

# Firmware 0.3.0: FSR on A0 + flex on A1, each with its own low-side resistor.
TWO_CHANNEL_BANNER = (
    "#GLOVE fw=0.3.0 proto=1 board=nano33ble rate=100 adc_bits=12 "
    "adc_ref_mv=3300 vdiv_mv=3300 r_fixed=10000 imu=none emg=0 "
    "cols=seq,t_us,p0,f0 chan=p0:fsr:10000,f0:flex:47000")


# Firmware 0.5.0: two FSRs plus the onboard IMU's six motion columns (gate 5).
IMU_BANNER = (
    "#GLOVE fw=0.5.0 proto=1 board=nano33ble rate=100 adc_bits=12 "
    "adc_ref_mv=3300 vdiv_mv=3300 r_fixed=10000 imu=BMI270_BMM150 "
    "imu_scale=1000 emg=0 cols=seq,t_us,p0,p1,ax,ay,az,gx,gy,gz "
    "chan=p0:fsr:10000,p1:fsr:10000,ax:accel,ay:accel,az:accel,"
    "gx:gyro,gy:gyro,gz:gyro")


def _sine(hz, amp, n, fs, offset=0.0):
    import math
    return [offset + amp * math.sin(2 * math.pi * hz * i / fs) for i in range(n)]


def test_banner_parses_all_fields():
    b = parse_banner(REAL_BANNER)
    assert b is not None
    assert b.fw == "0.1.0"
    assert b.proto == PROTO_SUPPORTED and b.supported
    assert b.board == "nano33ble"
    assert b.rate == 100
    assert b.adc_ref_mv == 3300 and b.vdiv_mv == 3300 and b.r_fixed == 10000
    assert b.cols == ("seq", "t_us", "p0")
    assert b.channels == ("p0",)
    assert b.adc_max == 1023


def test_banner_rejects_non_banner_lines():
    for line in ("", "G,1,1703,7", "#DIAG p0 adc=2", "#ZERO", "garbage"):
        assert parse_banner(line) is None


def test_banner_proto_mismatch_is_unsupported():
    b = parse_banner(REAL_BANNER.replace("proto=1", "proto=99"))
    assert b is not None and not b.supported


def test_frame_parses_real_line():
    f = parse_frame("G,1,1703,7", 1)
    assert f is not None
    assert (f.seq, f.t_us, f.values) == (1, 1703, (7,))


def test_frame_rejects_wrong_channel_count():
    # Guarding this stops values being silently mapped onto the wrong columns.
    assert parse_frame("G,1,1703,7,9", 1) is None
    assert parse_frame("G,1,1703", 1) is None
    assert parse_frame("G,1,1703,7,9", 2) is not None


def test_frame_accepts_any_count_before_banner_known():
    f = parse_frame("G,5,100,1,2,3", None)
    assert f is not None and f.values == (1, 2, 3)


def test_frame_never_raises_on_junk():
    junk = ["", "   ", "G,", "G,a,b,c", "G,1,1703,xx", "#GLOVE fw=1",
            "G,1,-5,7", "\x00\xff garbage", "G,1"]
    for line in junk:
        assert parse_frame(line, 1) is None


def test_frame_tolerates_truncation_mid_line():
    # A read straddling a frame boundary is the normal case, not an error.
    assert parse_frame("G,12,3456", 1) is None
    assert parse_frame("G,12,3456,88", 1) is not None


def test_seq_gap_counts_losses():
    assert seq_gap(10, 11) == 0        # consecutive
    assert seq_gap(10, 14) == 3        # three lost
    assert seq_gap(10, 10) == 0        # duplicate


def test_seq_gap_survives_uint32_wrap():
    assert seq_gap(0xFFFFFFFF, 0) == 0
    assert seq_gap(0xFFFFFFFE, 1) == 2


def test_seq_gap_treats_reset_as_no_loss():
    # The 'Z' command zeroes the counter; that is not 4 billion dropped frames.
    assert seq_gap(5000, 0) == 0


def test_us_delta_survives_wrap():
    assert us_delta(100, 400) == 300
    assert us_delta(0xFFFFFF00, 0x00000100) == 512


def test_adc_to_mv_matches_firmware_integer_math():
    # Values printed by the board's own #DIAG output.
    assert adc_to_mv(2, 3300, 10) == 6
    assert adc_to_mv(13, 3300, 10) == 41
    assert adc_to_mv(0, 3300, 10) == 0
    assert adc_to_mv(1023, 3300, 10) == 3300


def test_sensor_ohms_matches_firmware():
    assert sensor_ohms(2, 3300, 3300, 10000, 10) == 5490000
    assert sensor_ohms(13, 3300, 3300, 10000, 10) == 794878


def test_sensor_ohms_edges():
    assert sensor_ohms(0, 3300, 3300, 10000, 10) is None     # open sensor
    assert sensor_ohms(1023, 3300, 3300, 10000, 10) == 0     # at the rail


def test_sensor_ohms_falls_as_force_rises():
    # Physical sanity: harder press -> higher ADC -> lower resistance.
    readings = [sensor_ohms(a) for a in (50, 200, 512, 900)]
    assert all(r is not None for r in readings)
    assert readings == sorted(readings, reverse=True)


def test_accumulator_reads_banner_then_frames():
    acc = FrameAccumulator()
    assert acc.feed(REAL_BANNER) is None
    assert acc.banner is not None and acc.banner.channels == ("p0",)
    f = acc.feed("G,1,1703,7")
    assert f is not None and f.values == (7,)
    assert acc.total == 1 and acc.dropped == 0


def test_accumulator_counts_dropped_frames():
    acc = FrameAccumulator()
    acc.feed(REAL_BANNER)
    for seq in (1, 2, 5, 6):          # 3 and 4 lost
        acc.feed(f"G,{seq},{seq * 10000},{seq}")
    assert acc.total == 4
    assert acc.dropped == 2


def test_accumulator_ignores_noise_lines():
    acc = FrameAccumulator()
    acc.feed(REAL_BANNER)
    for line in ("#DIAG p0 adc=2 mv=6", "#ZERO", "", "junk"):
        assert acc.feed(line) is None
    assert acc.total == 0 and acc.dropped == 0


def test_accumulator_measures_rate():
    acc = FrameAccumulator()
    acc.feed(REAL_BANNER)
    for i in range(1, 201):           # exactly 100 Hz -> 10000 us apart
        acc.feed(f"G,{i},{i * 10000},{i % 1024}")
    assert abs(acc.rate_hz - 100.0) < 0.01


def test_accumulator_rate_matches_measured_hardware():
    # The real capture: seq 1..295 spanning 2931819 -> 2941910 us per frame.
    acc = FrameAccumulator()
    acc.feed(REAL_BANNER)
    for i in range(1, 101):
        acc.feed(f"G,{i},{1703 + (i - 1) * 10009},5")
    assert 99.0 < acc.rate_hz < 101.0


def test_accumulator_reset_clears_counters():
    acc = FrameAccumulator()
    acc.feed(REAL_BANNER)
    acc.feed("G,1,1000,5")
    acc.feed("G,9,2000,5")
    assert acc.dropped > 0
    acc.reset_counters()
    assert acc.total == 0 and acc.dropped == 0 and acc.rate_hz == 0.0
    # Banner survives a counter reset — the board did not reboot.
    assert acc.banner is not None


def test_accumulator_rate_is_zero_before_data():
    assert FrameAccumulator().rate_hz == 0.0


# ── force estimation (Interlink FSR402 published curve) ──────────────────

def test_force_is_exact_at_every_published_anchor():
    # The whole point of interpolating in log-log space rather than fitting one
    # global power law: the datasheet's own points come back unchanged.
    for newtons, ohms in FSR402_CURVE:
        got = force_newtons(ohms)
        assert abs(got - newtons) < 1e-9, f"{ohms} ohm -> {got}, want {newtons}"


def test_force_beats_a_single_power_law_fit():
    # A global least-squares fit R = 7138 * F**-0.7654 misses the published
    # anchors by up to ~20%; this is the regression guard for that choice.
    import math
    worst_fit = 0.0
    worst_ours = 0.0
    for newtons, ohms in FSR402_CURVE:
        fit_r = 7138.0 * newtons ** -0.7654
        worst_fit = max(worst_fit, abs(fit_r - ohms) / ohms)
        worst_ours = max(worst_ours, abs(force_newtons(ohms) - newtons) / newtons)
    assert worst_fit > 0.15, "the power-law fit should be visibly bad"
    assert worst_ours < 1e-9, "piecewise interpolation must be exact"


def test_force_rises_monotonically_as_resistance_falls():
    forces = [force_newtons(r) for r in (30000, 10000, 6000, 3000, 1000, 500, 250)]
    assert all(a < b for a, b in zip(forces, forces[1:])), forces


def test_force_interpolates_between_anchors():
    # 2 kOhm sits between the 1 N and 10 N anchors, so must land between them.
    f = force_newtons(2000)
    assert 1.0 < f < 10.0


def test_force_extrapolates_past_the_ends():
    assert force_newtons(1_000_000) < RATED_MIN_N   # barely touched
    assert force_newtons(150) > 100.0               # crushed


def test_force_open_and_invalid_inputs():
    assert force_newtons(None) is None
    assert force_newtons(-5) is None
    # 0 ohm means at/past the rail (protocol.sensor_ohms), not a crash.
    assert force_newtons(0) == FSR402_CURVE[-1][0]


def test_force_range_classifies_against_the_datasheet_band():
    assert force_range(None) == "open"
    assert force_range(0.05) == "below"            # under 0.2 N actuation
    assert force_range(RATED_MIN_N) == "rated"
    assert force_range(5.0) == "rated"
    assert force_range(RATED_MAX_N) == "rated"
    assert force_range(RATED_MAX_N + 0.1) == "above"


def test_hard_press_is_flagged_not_silently_reported():
    # 250 ohm reads 100 N off the curve, but the part is only rated to 20 N.
    # The UI must be able to badge that rather than print a confident number.
    assert force_range(force_newtons(250)) == "above"


def test_grams_force_conversion():
    assert grams_force(None) is None
    assert abs(grams_force(9.80665) - 1000.0) < 1e-6   # 1 kgf
    assert abs(grams_force(1.0) - 101.97) < 0.01


def test_conductance_is_reciprocal_resistance():
    assert conductance_us(1_000_000) == 1.0
    assert conductance_us(1000) == 1000.0
    assert conductance_us(None) is None
    assert conductance_us(0) is None


def test_force_model_payload_is_transportable():
    m = force_model()
    assert m["points"] == [[f, r] for f, r in FSR402_CURVE]
    assert m["rated_min_n"] == RATED_MIN_N and m["rated_max_n"] == RATED_MAX_N
    assert m["tolerance_pct"] == PART_TO_PART_PCT
    assert "FSR402" in m["source"]


def test_full_chain_adc_to_force_at_12_bit():
    # 12-bit ADC, 10k pulldown, 3.3 V: an ADC count all the way through to a
    # force, the way the dev page does it.
    r = sensor_ohms(3723, 3300, 3300, 10000, 12)
    assert r is not None and 900 < r < 1100        # ~1 kOhm
    f = force_newtons(r)
    assert 8.0 < f < 12.0                          # ~10 N per the curve
    assert force_range(f) == "rated"


# ── per-channel banner metadata (firmware 0.3.0) ────────────────────────────


def test_banner_parses_per_channel_kind_and_resistor():
    b = parse_banner(TWO_CHANNEL_BANNER)
    assert b is not None
    assert b.channels == ("p0", "f0")
    metas = b.channel_meta
    assert [m.name for m in metas] == ["p0", "f0"]
    assert metas[0].kind == KIND_FSR and metas[0].r_fixed == 10000
    assert metas[1].kind == KIND_FLEX and metas[1].r_fixed == 47000
    # The added field must not disturb the layout contract.
    assert b.proto == PROTO_SUPPORTED and b.supported
    assert b.adc_max == 4095


def test_banner_parses_two_force_channels():
    # fw 0.4.0 bench layout: force sensors on the EVEN analog pins, p<n> on
    # A(2n). The host must carry both channels with the right kind and
    # resistor, since the whole point of the layout is that adding a sensor is
    # a firmware table edit with no host change.
    b = parse_banner(
        "#GLOVE fw=0.4.0 proto=1 board=nano33ble rate=100 adc_bits=12 "
        "adc_ref_mv=3300 vdiv_mv=3300 r_fixed=10000 imu=none emg=0 "
        "cols=seq,t_us,p0,p1 chan=p0:fsr:10000,p1:fsr:10000")
    assert b is not None and b.supported
    assert b.channels == ("p0", "p1")
    metas = b.channel_meta
    assert len(metas) == 2
    assert all(m.kind == KIND_FSR and m.r_fixed == 10000 for m in metas)
    # A frame must carry exactly one value per declared channel, or the host
    # would map readings onto the wrong sensor.
    assert parse_frame("G,7,1703,120,2048", n_values=len(b.channels)) is not None
    assert parse_frame("G,7,1703,120", n_values=len(b.channels)) is None


def test_banner_without_chan_field_falls_back_to_naming_convention():
    # Firmware 0.2.0 and earlier emit no chan= at all. Every channel must still
    # come back with a kind and a resistor, or the dev page shifts its readouts.
    b = parse_banner(REAL_BANNER)
    metas = b.channel_meta
    assert len(metas) == len(b.channels)
    assert metas[0].kind == KIND_FSR          # "p0" -> pressure
    assert metas[0].r_fixed == b.r_fixed      # global fallback


def test_channel_meta_covers_channels_the_chan_field_missed():
    # A chan= naming only some channels must not drop the rest - one entry per
    # column, always, in column order.
    b = parse_banner(TWO_CHANNEL_BANNER.replace(
        "chan=p0:fsr:10000,f0:flex:47000", "chan=p0:fsr:10000"))
    metas = b.channel_meta
    assert [m.name for m in metas] == ["p0", "f0"]
    assert metas[1].kind == KIND_FLEX         # guessed from the name
    assert metas[1].r_fixed == 10000          # global fallback


def test_banner_chan_field_never_raises_on_junk():
    junk = ("chan=", "chan=,,,", "chan=:::", "chan=p0", "chan=p0:",
            "chan=p0:fsr", "chan=p0:fsr:", "chan=p0:fsr:abc",
            "chan=p0:fsr:0", "chan=p0:fsr:-5", "chan=p0:bogus:10000",
            "chan=p0:fsr:10000,,f0:flex:47000")
    for bad in junk:
        b = parse_banner(TWO_CHANNEL_BANNER.replace(
            "chan=p0:fsr:10000,f0:flex:47000", bad))
        assert b is not None, bad
        metas = b.channel_meta
        assert len(metas) == len(b.channels), bad
        for m in metas:
            # A bad resistor must never reach the divider maths as <= 0.
            assert m.r_fixed > 0, bad
            assert m.kind in (KIND_FSR, KIND_FLEX, KIND_UNKNOWN), bad


def test_banner_chan_rejects_an_unknown_kind():
    b = parse_banner(TWO_CHANNEL_BANNER.replace("f0:flex:47000",
                                                "f0:magnetic:47000"))
    meta = b.meta_for(1)
    # Unknown kinds stop at resistance rather than being guessed into a curve.
    assert meta.kind == KIND_UNKNOWN and meta.r_fixed == 47000


def test_meta_for_out_of_range_is_none():
    b = parse_banner(TWO_CHANNEL_BANNER)
    assert b.meta_for(0) is not None and b.meta_for(1) is not None
    assert b.meta_for(2) is None and b.meta_for(-1) is None


def test_kind_from_name_follows_the_plan_convention():
    assert kind_from_name("f0") == KIND_FLEX
    assert kind_from_name("f4") == KIND_FLEX
    assert kind_from_name("p0") == KIND_FSR
    assert kind_from_name("p5") == KIND_FSR
    # ax/gz became IMU columns in fw 0.5.0 and are covered by
    # test_kind_from_name_separates_imu_columns_from_sensors; everything else
    # with no declared kind must still fall through to unknown.
    for name in ("", "emg", "x1", "a", "g"):
        assert kind_from_name(name) == KIND_UNKNOWN, name


def test_per_channel_resistor_changes_the_resistance():
    # The whole point of the per-channel field: the same counts on different
    # resistors are different resistances. Sharing one value silently
    # mis-scales whichever sensor did not own it.
    b = parse_banner(TWO_CHANNEL_BANNER)
    fsr, flex = b.meta_for(0), b.meta_for(1)
    counts = 2048
    r_fsr = sensor_ohms(counts, 3300, 3300, fsr.r_fixed, 12)
    r_flex = sensor_ohms(counts, 3300, 3300, flex.r_fixed, 12)
    assert r_fsr is not None and r_flex is not None
    assert r_flex > r_fsr * 4          # 47k vs 10k


# ── flex / bend estimation ──────────────────────────────────────────────────


def test_default_flex_span_is_flagged_uncalibrated():
    # The nominal span exists so the UI has something to draw, and must never
    # pass itself off as measured.
    span = default_span()
    assert span.flat_ohm == NOMINAL_FLAT_OHM
    assert span.bent_ohm == NOMINAL_BENT_OHM
    assert span.usable
    assert not is_calibrated(span)


def test_bend_fraction_runs_flat_to_bent():
    span = FlexSpan(flat_ohm=10_000, bent_ohm=110_000, calibrated=True)
    assert bend_fraction(10_000, span) == 0.0
    assert bend_fraction(110_000, span) == 1.0
    mid = bend_fraction(60_000, span)
    assert 0.49 < mid < 0.51
    assert bend_percent(60_000, span) == mid * 100.0


def test_bend_fraction_clamps_outside_the_recorded_span():
    # Past either end the sensor has left the range it was calibrated over.
    # Extrapolating would invent travel that was never measured.
    span = FlexSpan(flat_ohm=10_000, bent_ohm=110_000, calibrated=True)
    assert bend_fraction(500, span) == 0.0
    assert bend_fraction(10_000_000, span) == 1.0


def test_bend_range_flags_a_clamped_reading():
    span = FlexSpan(flat_ohm=10_000, bent_ohm=110_000, calibrated=True)
    assert bend_range(9_000, span) == "below"
    assert bend_range(50_000, span) == "in"
    assert bend_range(200_000, span) == "above"
    assert bend_range(None, span) == "open"
    assert bend_range(0, span) == "open"


def test_bend_handles_a_reversed_span():
    # A sensor can be mounted or wired so that bending lowers resistance.
    # "below" must keep meaning the flat end either way.
    span = FlexSpan(flat_ohm=110_000, bent_ohm=10_000, calibrated=True)
    assert bend_fraction(110_000, span) == 0.0
    assert bend_fraction(10_000, span) == 1.0
    assert bend_range(200_000, span) == "below"
    assert bend_range(5_000, span) == "above"


def test_bend_rejects_a_span_too_narrow_to_be_travel():
    narrow = FlexSpan(flat_ohm=10_000, bent_ohm=10_100, calibrated=True)
    assert not narrow.usable
    assert bend_fraction(10_050, narrow) is None
    assert bend_range(10_050, narrow) == "open"
    assert not is_calibrated(narrow)
    # span_from_ohms refuses to build one, handing back the default instead.
    assert span_from_ohms(10_000, 10_100) == default_span()
    assert span_from_ohms(10_000, 10_000 * MIN_SPAN_RATIO * 2).calibrated


def test_bend_open_and_invalid_inputs():
    span = FlexSpan(flat_ohm=10_000, bent_ohm=110_000, calibrated=True)
    for bad in (None, 0, -1):
        assert bend_fraction(bad, span) is None
        assert bend_percent(bad, span) is None
    assert span_from_ohms(None, 110_000) == default_span()
    assert span_from_ohms(10_000, None) == default_span()
    for bad_span in (FlexSpan(flat_ohm=0, bent_ohm=110_000),
                     FlexSpan(flat_ohm=10_000, bent_ohm=-5)):
        assert not bad_span.usable
        assert bend_fraction(50_000, bad_span) is None


def test_flex_model_payload_is_transportable():
    m = flex_model(FlexSpan(flat_ohm=12_000, bent_ohm=90_000, calibrated=True))
    assert m["flat_ohm"] == 12_000 and m["bent_ohm"] == 90_000
    assert m["calibrated"] is True and m["usable"] is True
    assert "no published curve" in m["source"]
    # The dev page derives a span from live readings and needs the same
    # "travel or noise?" threshold, so it must travel with the payload.
    assert m["min_span_ratio"] == MIN_SPAN_RATIO
    # The default span ships as explicitly uncalibrated.
    assert flex_model(default_span())["calibrated"] is False


def test_flex_channel_carries_the_signal_that_stops_the_force_curve():
    # Guards the exact bug this change exists to prevent: the FSR402 curve
    # applied to a bending finger. force_newtons() will happily return a
    # number for any resistance - the channel's kind is what stops the caller
    # from asking, so assert that signal is present and correct.
    b = parse_banner(TWO_CHANNEL_BANNER)
    flex = b.meta_for(1)
    assert flex.kind == KIND_FLEX and flex.kind != KIND_FSR
    ohm = sensor_ohms(2048, 3300, 3300, flex.r_fixed, 12)
    assert force_newtons(ohm) is not None
    assert isinstance(flex, ChannelMeta)


# -- onboard IMU (gate 5) ---------------------------------------------------

def test_imu_banner_declares_columns_scale_and_kinds():
    b = parse_banner(IMU_BANNER)
    assert b is not None and b.supported
    assert b.imu == "BMI270_BMM150" and b.imu_present
    assert b.imu_scale == 1000
    assert b.channels == ("p0", "p1") + IMU_COLS
    metas = {m.name: m for m in b.channel_meta}
    assert metas["ax"].kind == KIND_ACCEL and metas["gz"].kind == KIND_GYRO
    assert metas["p0"].kind == KIND_FSR
    # One entry per column, in order, or the page indexes off the end.
    assert len(b.channel_meta) == len(b.channels)


def test_imu_channels_are_never_divider_sensors():
    # The guard this branch exists for, the motion counterpart of the
    # flex/force split: an accelerometer has no low-side resistor, and any
    # resistance computed for one is a number with no meaning.
    b = parse_banner(IMU_BANNER)
    for name in IMU_COLS:
        meta = next(m for m in b.channel_meta if m.name == name)
        assert meta.is_imu
    assert not next(m for m in b.channel_meta if m.name == "p0").is_imu


def test_imu_absent_is_reported_as_absent():
    # Firmware whose IMU.begin() failed writes imu=none AND omits the columns,
    # so six flat zeroes can never masquerade as a still hand.
    b = parse_banner(TWO_CHANNEL_BANNER)
    assert not b.imu_present
    assert b.imu_index() == {}


def test_imu_index_refuses_a_partial_column_set():
    partial = IMU_BANNER.replace(",gy,gz", "")
    b = parse_banner(partial)
    # Better to report nothing than to guess an offset and read a flex strip
    # as an accelerometer.
    assert b.imu_index() == {}


def test_imu_index_is_by_name_not_by_position():
    b = parse_banner(IMU_BANNER)
    idx = b.imu_index()
    assert idx["ax"] == 2 and idx["gz"] == 7


def test_kind_from_name_separates_imu_columns_from_sensors():
    assert kind_from_name("ax") == KIND_ACCEL
    assert kind_from_name("gy") == KIND_GYRO
    # The single-letter fallback must not start claiming kinds for names the
    # firmware never emits.
    assert kind_from_name("f0") == KIND_FLEX
    assert kind_from_name("p3") == KIND_FSR
    assert kind_from_name("a") == KIND_UNKNOWN
    assert kind_from_name("gyro") == KIND_UNKNOWN


def test_frame_accepts_signed_imu_values():
    b = parse_banner(IMU_BANNER)
    line = "G,42,1000000,2048,900,-16,-30,1012,-1500,20,-7"
    f = parse_frame(line, len(b.channels))
    assert f is not None
    assert f.values[2] == -16 and f.values[5] == -1500
    assert to_units(f.values[4], b.imu_scale) == 1.012


def test_to_units_uses_the_banner_scale():
    assert to_units(1000, 1000) == 1.0
    assert to_units(-2500, 1000) == -2.5
    assert to_units(1000, 0) is None


def test_tilt_reads_gravity_and_flips_sign():
    # Gate 5 in one assertion: flat on a desk reads about 1 g on one axis, and
    # flipping the board flips it.
    flat = tilt(0.0, 0.0, 1.0)
    assert flat["static"] and abs(flat["magnitude_g"] - 1.0) < 1e-9
    assert abs(flat["pitch_deg"]) < 1e-6 and abs(flat["roll_deg"]) < 1e-6
    flipped = tilt(0.0, 0.0, -1.0)
    assert abs(abs(flipped["roll_deg"]) - 180.0) < 1e-6
    on_edge = tilt(1.0, 0.0, 0.0)
    assert abs(on_edge["pitch_deg"] + 90.0) < 1e-6


def test_tilt_refuses_to_claim_an_angle_while_moving():
    # 2 g means the hand is accelerating, so the vector is not gravity alone
    # and an angle read off it would be a guess.
    assert tilt(0.0, 0.0, 2.0)["static"] is False
    assert tilt(0.0, 0.0, 1.0)["static"] is True


def test_magnitude_and_rms():
    assert magnitude(3.0, 4.0, 0.0) == 5.0
    assert magnitude(1.0, None, 0.0) is None
    assert rms([1.0, 1.0, 1.0]) == 0.0     # gravity alone is not movement
    assert rms([1.0]) is None


def test_band_power_finds_a_planted_tremor():
    fs, n = 100.0, 300
    sig = _sine(6.0, 0.05, n, fs, offset=1.0)   # 6 Hz wobble riding on gravity
    out = band_power(sig, fs)
    assert out is not None
    assert abs(out["peak_hz"] - 6.0) < 0.5
    assert out["band_frac"] > 0.9
    assert out["band"] == list(TREMOR_BAND)


def test_band_power_ignores_slow_voluntary_motion():
    # A 1 Hz sweep is someone moving their hand, not tremor. Four times the
    # amplitude of the test above, and it must still not land in the band.
    out = band_power(_sine(1.0, 0.2, 300, 100.0, offset=1.0), 100.0)
    assert out is not None and out["band_frac"] < 0.05


def test_band_power_refuses_windows_that_cannot_support_a_claim():
    fs = 100.0
    short = _sine(6.0, 0.05, int(MIN_WINDOW_S * fs) - 10, fs)
    assert band_power(short, fs) is None
    # A rate that cannot resolve the band must return None, never a number:
    # the camera path makes the same refusal in core/spiral/metrics.py.
    assert band_power(_sine(2.0, 0.05, 300, 6.0), 6.0) is None
    assert band_power([1.0] * 300, 100.0) is None    # perfectly flat


def test_band_power_clamps_the_upper_edge_to_nyquist():
    # 20 Hz sampling can only resolve to 10 Hz, below the band's 12 Hz top.
    out = band_power(_sine(5.0, 0.05, 200, 20.0), 20.0)
    assert out is not None and out["band"][1] <= 10.0


def test_held_fraction_counts_repeated_imu_samples():
    fresh = [(1, 2, 3), (1, 2, 4), (1, 2, 5), (1, 2, 6)]
    assert held_fraction(fresh) == 0.0
    held = [(1, 2, 3), (1, 2, 3), (1, 2, 4), (1, 2, 4)]
    assert abs(held_fraction(held) - 2 / 3) < 1e-9
    assert held_fraction([(1, 2, 3)]) is None


def test_derived_routes_motion_away_from_the_divider_maths():
    # End to end through the reader: an accelerometer column must come back as
    # g, with no resistance, no force and no bend anywhere in the payload.
    import tempfile
    from core.glove.serial_io import GloveReader
    reader = GloveReader(tempfile.gettempdir())
    reader._acc.feed(IMU_BANNER)
    out = reader.derived(-2000, "ax")
    assert out["kind"] == KIND_ACCEL
    assert out["value"] == -2.0 and out["unit"] == "g"
    assert out["ohm"] is None and out["newtons"] is None and out["bend_pct"] is None
    # And a force channel on the same board still gets its curve.
    fsr = reader.derived(2048, "p0")
    assert fsr["kind"] == KIND_FSR and fsr["ohm"] is not None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
