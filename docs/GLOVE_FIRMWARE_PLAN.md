# Sensor-Glove Firmware & Toolchain Plan (Arduino side)

_Last updated: 2026-07-26. **Status: firmware live, host stack landed, force
readout working.** `firmware/glove/glove.ino` **v0.2.0** streams **12-bit**
samples from an **Arduino Nano 33 BLE (confirmed, COM10)** at a measured
**99.978 Hz with zero dropped frames**. `core/glove/` parses, records, and
converts to approximate force via the published FSR402 curve (§5b); the
launcher's **Developer page** shows newtons, grams-force, conductance and peak
force. **Gates 0, 1, 7 and 8 passed**; gate 3 awaits a recorded press span._
_Integration context in [`ROADMAP.md`](ROADMAP.md) §2–§3._

This document covers the two things the design notes leave implicit:

1. **The Arduino code** — what the firmware must do, how it is structured, the
   exact serial frame it emits, and the build order with a verification gate at
   each step.
2. **Everything that must be downloaded** — IDE, board package, Arduino
   libraries, Python packages, OpenSim, and 3D assets — as an actionable
   checklist (§7).

**Out of scope here:** the OpenSim biomechanical model itself (inverse dynamics,
static optimization, the co-contraction index) and the 3D twin renderer. Those
are the design notes Steps 10–11 and deserve their own plan once the glove reliably
streams calibrated data. This document stops at the boundary: *a trustworthy,
timestamped, calibrated stream of angles and forces on the host.*

---

## 1. Design constraints that change the BOM

Three hardware facts materially affect the firmware and the shopping list. Each
is a real constraint, not a preference.

### 1.1 There are not enough analog pins — a multiplexer is required

The Arduino Nano 33 BLE exposes **8 analog inputs (A0–A7)**. The sensing layer
in the design notes needs **11 analog channels** (5 flex + 6 FSR), plus one more if
the optional EMG is fitted. This does not fit.

| Option | Consequence |
|---|---|
| **Add a CD74HC4067 16-channel analog mux** *(recommended)* | ~$3–5. Uses 1 analog pin + 4 digital select pins, leaves 7 analog pins free and room for EMG later. Costs a settling delay per channel (see §3.3). |
| 74HC4051 8-channel mux | Cheaper, but 8 channels + 1 direct pin is only just enough — no headroom. |
| Drop to 3 FSRs (thumb, index, middle) | 5 + 3 = 8 channels, exactly fills A0–A7 with zero spare pins and no EMG path. Loses palm force. |

**Decision: buy the CD74HC4067.** It is the only option that keeps the full
sensor set and the EMG upgrade path. Add it to the BOM (§7.1).

### 1.2 The board is 3.3 V, and most tutorials are 5 V

The Nano 33 BLE runs at **3.3 V logic** and its ADC reference is 3.3 V. Nearly
every flex-sensor and FSR tutorial listed in the design notes §6.2–6.3 assumes a 5 V Uno.
Consequences:

- Divider *ratios* carry over unchanged; the *voltage* at the junction does not.
  Calibration constants from a 5 V tutorial are wrong on this board.
- **Do not feed 5 V into any analog pin.** The nRF52840 is not 5 V tolerant.
- The ADC defaults to **10-bit (0–1023)**, matching the design notes data-flow
  description. It supports 12-bit via `analogReadResolution(12)`; see §3.3 for
  why we still start at 10-bit.

### 1.3 Skip the MPU-6050 — the board already has an IMU

The design notes BOM lists an MPU-6050 breakout *and* selects the Nano 33 BLE
"built-in IMU" in the same table. The onboard IMU is the better choice: no
wiring, no I²C pull-up/level questions on a 3.3 V rail, no extra failure point,
and one fewer part to mount on a glove. **Drop the MPU-6050 (−$4).**

> **Board revision matters for the IMU library.** The original Nano 33 BLE
> carries an **LSM9DS1**; the **Rev2** carries a **BMI270 + BMM150**. They need
> *different* Arduino libraries. Check the silkscreen on the board you actually
> receive before installing a library (§7.2), and have the firmware print which
> IMU it initialized in its boot banner (§4.2) so this can never be ambiguous.

### 1.4 EMG bandwidth does not match the glove's sample rate

If the MyoWare 2.0 is fitted: **raw** surface EMG occupies roughly 20–450 Hz and
needs ≥1 kHz sampling — far above the glove's 100 Hz frame rate. The MyoWare's
**envelope (rectified + smoothed) output** is a slow signal that samples
correctly at 100 Hz.

**Use the envelope output** for the co-contraction validation described in
the design notes §7.2. Raw EMG would require a separate high-rate acquisition path and is
explicitly deferred.

---

## 2. Firmware responsibilities (and non-responsibilities)

The firmware is deliberately thin. Every judgment call that might later need
revisiting belongs on the host, where it is versionable, testable, and does not
require a reflash.

**The Arduino does:**
- Sample all channels on a fixed, jitter-bounded schedule.
- Average/oversample each ADC read to suppress quantization and pickup noise.
- Emit one self-describing ASCII frame per timestep, with a sequence number.
- Answer a tiny command set so the host can identify the device and query its
  schema.

**The Arduino does *not*:**
- Convert to newtons or degrees — calibration is per-user and lives on the host
  (the design notes Step 9).
- Smooth aggressively. *This mirrors the rule already enforced in
  `screening_tests/spiral_test.py`: **jitter is signal.** Tremor and
  micro-instability are exactly what the study is looking for, and on-device
  low-pass filtering destroys them irreversibly.* Only per-sample averaging
  within one timestep is allowed (§3.3).
- Buffer history, compute metrics, or write files.
- Talk BLE in v1 (see §6).

---

## 3. Sampling design

### 3.1 Rate

**100 Hz.** Hand tremor of interest sits in the 4–12 Hz band, so Nyquist demands
>24 Hz; 100 Hz leaves generous headroom for edge detection on tap onsets and
matches the MyoWare envelope's usable bandwidth. It is also comfortably within
what an ASCII frame over USB CDC sustains (§4.3).

### 3.2 Scheduling

Use an explicit `micros()`-based scheduler, **never `delay()`**:

```
next_due += FRAME_PERIOD_US;
if ((int32_t)(micros() - next_due) >= 0) { sample(); emit(); }
```

Accumulating `next_due` (rather than resetting it from "now") keeps the schedule
on an absolute grid and prevents slow drift — the same technique
`core/tapping/` already uses for its metronome beats. Track and report any
missed deadline as a dropped frame rather than silently sliding.

### 3.3 Per-channel read

For each of the 11 channels, through the mux:

1. Set the 4 select lines.
2. **Wait for the mux + ADC sample-and-hold to settle** before reading. Start
   with ~5 µs and raise it if adjacent channels visibly bleed into each other —
   channel crosstalk is the classic mux bug and it looks exactly like a real
   sensor reading.
3. Take **4 reads and average** them. This is noise reduction *within* a single
   timestep and does not touch the inter-sample dynamics we care about.

Budget: 11 channels × (settle + 4 reads) is a small fraction of the 10 ms frame
period, leaving ample margin for the IMU read and serial write.

**Now 12-bit (was 10-bit).** The original plan started at 10-bit to match the
original data flow (0–1023) and every tutorial in the design notes §6. Revisited and
changed in fw 0.2.0: across the FSR402's rated 0.2–20 N band the 10 kΩ divider
resolves only **658 counts at 10-bit vs 2631 at 12-bit**, and the compression
lands hardest at the top of the range (5–20 N spans just 108 counts at 10-bit).
`OVERSAMPLE` rose 4 → 8 at the same time, since two extra bits are only worth
having if they sit above the ADC's noise floor. Measured on hardware afterwards:
**99.978 Hz, 0 dropped frames** — the extra reads fit the 10 ms budget.

`ADC_BITS`/`ADC_MAX` are single constants for exactly this reason: before the
change, `1023` was hardcoded in `adcToMillivolts()`, seeded `g_min[]` in
`resetSpans()`, and `adc_bits=10` was a **string literal in the banner**. Any of
those left behind would have silently corrupted every derived resistance and
force. `proto` stays **1** — the frame layout did not change, only the value
scale, which the banner's `adc_bits` already communicates.

---

## 4. Serial protocol

### 4.1 Frame format

One line per timestep, `\n`-terminated ASCII CSV. Prefixed with a tag so the
host can discriminate data from banners, logs, and errors on the same stream:

```
G,<seq>,<t_us>,<f0..f4>,<p0..p5>,<ax,ay,az>,<gx,gy,gz>[,<emg>]
```

| Field | Count | Range | Meaning |
|---|---|---|---|
| `G` | 1 | literal | Frame tag — data line |
| `seq` | 1 | `uint32`, wraps | Monotonic frame counter; **gap ⇒ dropped frame** |
| `t_us` | 1 | `uint32` µs, wraps | Device-side timestamp (relative; see §4.4) |
| `f0..f4` | 5 | 0–1023 | Flex, thumb→pinky |
| `p0..p5` | 6 | 0–1023 | FSR: 5 fingertips + 1 palm |
| `ax,ay,az` | 3 | float g | Accelerometer |
| `gx,gy,gz` | 3 | float °/s | Gyroscope |
| `emg` | 0 or 1 | 0–1023 | MyoWare envelope, **only if fitted** |

Non-data lines use distinct tags — `#` for banner/info, `!` for error — so a
parser can skip them safely.

### 4.2 Boot banner

On startup (and on the `?` command), emit a machine-readable banner:

```
#GLOVE fw=1.0.0 proto=1 rate=100 imu=LSM9DS1 emg=0 cols=seq,t_us,f0,f1,...
```

This does real work: it lets the host **auto-detect which COM port is the
glove** instead of guessing, verifies the firmware and host agree on the column
layout before a single sample is trusted, and records which IMU variant the
board actually has (§1.3). Refuse to parse frames until a compatible `proto` is
seen.

### 4.3 Why ASCII, and why baud rate is irrelevant

At 100 Hz with ~18 fields the stream is roughly 8–10 KB/s. The Nano 33 BLE
presents a **native USB CDC** port, so the configured baud rate is ignored and
throughput is USB full-speed — orders of magnitude above what is needed. ASCII
stays human-debuggable in the Serial Monitor; there is no reason to go binary.

> **Native-USB gotcha:** `Serial.write()` can block when the host is not
> draining the port, which would stall the sample loop and corrupt timing. Drop
> the frame instead of blocking — the `seq` gap makes the loss visible to the
> host, whereas a stalled sampler is invisible. Never block the sampler to
> satisfy a slow reader.
>
> **Verified 2026-07-26 — do not gate on `availableForWrite()` alone.**
> `Print::availableForWrite()` is a virtual that **defaults to returning 0** on
> cores that do not override it, and the Nano 33 BLE's USB CDC is one of them.
> A guard of the form `availableForWrite() >= NEEDED` therefore drops *every*
> frame on this board: the banner still prints (it is written unguarded), so
> the board looks alive while emitting no data. Only honour the reading when it
> is non-zero — `if (room > 0 && room < NEEDED) drop;` — which keeps the
> protection on cores that implement it and degrades to a plain write elsewhere.

### 4.4 Timestamps

`t_us` is device-relative and its zero is arbitrary. Per ROADMAP §3.1, the
**host clock is authoritative**: the host stamps each frame on arrival and uses
`t_us` only to measure *intervals* and detect jitter within the device. A `Z`
command (§4.5) zeroes the counter to mark a shared session start alongside the
camera stream.

### 4.5 Command set

Single characters, newline-terminated. Kept minimal on purpose:

| Cmd | Effect |
|---|---|
| `?` | Re-emit the boot banner |
| `S` | Start streaming |
| `X` | Stop streaming (idle, still responsive) |
| `Z` | Zero `seq` and `t_us` — session start marker |

Anything more (rate changes, per-channel gain) is host-side configuration or
does not belong in v1.

---

## 5. Host-side counterpart

Mirrors the engine/UI split already used by `core/gaze/`, `core/spiral/`, and
`core/tapping/` — pure logic separated from I/O so it is unit-testable without
hardware:

```
core/glove/
  protocol.py   # DONE. PURE: parse a line → GloveFrame | None; banner parse;
                #       proto-version check; seq-gap / drop accounting;
                #       adc_to_mv / sensor_ohms mirroring the firmware's
                #       integer math; FrameAccumulator for stream health
  serial_io.py  # DONE. pyserial port open, VID-based auto-detect, background
                #       reader thread, bounded ring buffer, CSV recording
  calibrate.py  # TODO: PURE raw ADC → degrees / newtons; per-user profile
                #       load/save (the design notes Step 9)
  bridge.py     # TODO (optional): republish onto localhost UDP, mirroring
                #       core/hand_tracking.py's 127.0.0.1:5052 pattern
                #       (proposed port 5053) so camera + glove land in one
                #       fusion consumer — ROADMAP §3.1
screening_tests/tests/test_glove.py   # DONE — 23 tests, no hardware needed
```

**First consumer: the launcher's Developer page.** `launcher.py` holds one
`GloveReader` and exposes `/api/glove/*` + `/api/dev/*`; `launcher_web/dev.js`
renders the toolchain pills, firmware compile/upload buttons, a live canvas
scope, per-channel ADC/mV/Ω readouts with min–max spans, stream health, board
commands and a serial console. Channel names come from the banner's `cols`, so
growing from one FSR to eleven channels plus the mux needs **no frontend
change**. pyserial is imported lazily, so the hub still runs without it.

`protocol.py` must be **hardware-free and fully unit-tested**: feed it recorded
lines, truncated lines, banner lines, garbage, and out-of-order sequence numbers
and assert it never raises and never silently accepts a malformed frame. This
matches how `core/gaze/` is tested in `screening_tests/tests/test_gaze.py`.

Sessions persist through the **existing** `core/session.py` schema (JSON in
`results/` + `results/index.csv`) rather than the separate CSV path in the design notes
Step 12 — ROADMAP §3.2 requires one shared schema for camera and glove.

---

## 5b. Force estimation (`core/glove/force.py`)

The dev page reports **approximate force**, not raw counts. The conversion chain
is `ADC → millivolts → sensor resistance → conductance → newtons`, and the last
step uses the **published Interlink FSR402 typical force curve** rather than a
home-made guess:

| Force | Resistance |
|---|---|
| 0.2 N | 30 kΩ |
| 1 N | 6 kΩ |
| 10 N | 1 kΩ |
| 100 N | 250 Ω |

Sources: [FSR402 datasheet Fig. 1](https://cdn.sparkfun.com/assets/8/a/1/2/0/2010-10-26-DataSheet-FSR402-Layout2.pdf),
transcribed in [Adafruit *Using an FSR*](https://learn.adafruit.com/force-sensitive-resistor-fsr/using-an-fsr);
see also the [Interlink FSR Integration Guide](https://www.pololu.com/file/0J749/FSR400-Series-Integration-Guide-13.pdf).

**Piecewise log-log interpolation, not a single power law.** The datasheet says
the part follows an inverse power law only *"at slightly higher and then
intermediate forces"*, and the numbers agree: a global least-squares fit gives
`R = 7138 · F^-0.765` with **±20% residuals against the datasheet's own four
points**. Interpolating linearly in log-log space is exact at every anchor and
still behaves as a local power law between them. `test_glove.py` guards this
choice — it asserts the fit is visibly bad and the interpolation is exact.

**Honesty rules baked in.** Interlink specs force repeatability at ±2%
single-part / ±6% part-to-part, so readings are badged `datasheet ±6%`. Outside
the rated band nothing is specified, so `force_range()` returns `below` /
`rated` / `above` and the UI badges a hard press as *"beyond rated 20 N — upper
bound only"* rather than printing a confident 160 N. Conductance (µS) is shown
alongside because it is *measured*, whereas force is *modelled*.

**The pulldown resistor was deliberately left at 10 kΩ.** Lowering it to 3.3 kΩ
(the floor before the FSR exceeds Interlink's ~1 mA guidance) would raise the
1 kΩ→250 Ω span from 273 to 664 counts at 12-bit — but that span is **13–80 N**,
outside the rated range, and it would cost low-force resolution (100 kΩ drops
from 93 to 32 counts). Bad trade for a fine-motor instrument. Revisit only if a
task genuinely needs >20 N.

Per-sensor calibration is deferred, not designed out: every function derives
from `FSR402_CURVE`, so `calibrate.py` can replace that table with measured
points and nothing else changes.

---

## 6. Build order, with a verification gate at each step

Refines the design notes §5 Steps 1–9 for the mux'd, 3.3 V, no-MPU design. **Do not
proceed past a failed gate.**

| # | Step | Gate — what proves it works |
|---|---|---|
| 0 | Blink + banner on a bare board | Board enumerates as a COM port; banner prints in Serial Monitor. Proves toolchain and driver before any sensor exists. |
| 1 | Simulate the divider ([§7.5](#75-simulators-browser-no-install)) | You can predict the junction voltage at 3.3 V for min and max sensor resistance, on paper, before spending money. |
| 2 | One flex sensor, direct to A0 | Reading swings smoothly over a wide span as you bend. **Record the actual min/max** — it feeds calibration. |
| 3 | One FSR, direct to A1 | Reading responds monotonically to pressure. Note that FSRs are strongly non-linear; that is expected. |
| 4 | Add the CD74HC4067, move both sensors onto it | Both read correctly through the mux, **and channel 0 does not change when only channel 1 is pressed.** This is the crosstalk gate — §3.3. |
| 5 | Onboard IMU | Accel reads ≈1 g on the down axis and swaps sign when the board is flipped. Banner reports the correct IMU variant. |
| 6 | All 11 channels + full frame | Frame is well-formed at a steady 100 Hz; `seq` advances with **no gaps** over a 60-second run. |
| 7 | `core/glove/protocol.py` + unit tests | **PASSED** — 23 tests green with no hardware attached (`python screening_tests/tests/test_glove.py`). |
| 8 | `serial_io.py` end-to-end | **PASSED** — auto-detects COM10 by USB VID `0x2341`, streams at 99.99 Hz with 0 dropped frames and 0 parse failures, records 100 rows/s to CSV. |
| 9 | Per-user calibration | FSR → newtons against known weights; flex → degrees against known angles. Round-trip error documented, not assumed. |

Steps 0–6 are firmware; 7–9 are host Python. the design notes Steps 10–12 (OpenSim, the
twin render, co-contraction) begin only after gate 9 — as the design notes §5 itself
warns, *"steps 10–11 are where the real engineering time lives."*

**BLE is deliberately deferred.** USB serial removes a whole class of pairing,
throughput, and latency problems while the sensor and calibration work is being
debugged. Revisit only once the wired path is stable; the frame format is
transport-agnostic and carries over unchanged.

---

## 7. What must be downloaded — checklist

Everything below is free. Sizes are approximate order-of-magnitude and worth
re-checking at install time; version numbers move.

### 7.1 Hardware to order first (not a download, but blocks everything)

Deltas from the design notes §4.1 BOM, per §1:

| Change | Part | ~Cost |
|---|---|---|
| **Add** | CD74HC4067 16-channel analog mux breakout (SparkFun/Adafruit/Amazon) | +$3–5 |
| **Remove** | MPU-6050 breakout — onboard IMU replaces it | −$4 |

Net effect on the design notes budget: roughly unchanged (≈$119 core / ≈$159 with
EMG).

### 7.2 Arduino toolchain

| Item | Source | Notes |
|---|---|---|
| **Arduino IDE 2.x** | arduino.cc/en/software | ~200 MB. IDE 2.x preferred over 1.8.x for this board. |
| **Board package: "Arduino Mbed OS Nano Boards"** | IDE → Boards Manager | ~140 MB — the largest single download here; it pulls a full ARM toolchain. **Already installed** (`arduino:mbed_nano@4.6.0`) in `%LOCALAPPDATA%\Arduino15`, which the IDE shares — so the IDE will find it and skip this download. |
| **IMU library — pick ONE by board revision (§1.3)** | IDE → Library Manager | `Arduino_LSM9DS1` for the original Nano 33 BLE; `Arduino_BMI270_BMM150` for **Rev2**. Installing the wrong one produces a board that compiles and silently reports no motion. |
| `ArduinoBLE` | IDE → Library Manager | **Only when BLE work starts (§6).** Not needed for v1. |
| USB driver | — | Windows 10/11 normally enumerates the native USB CDC port with no driver install. If the port never appears, **double-tap the reset button** to force the bootloader, then re-check Device Manager. |

No mux library is needed — a 4-channel `digitalWrite` select is a few lines of
code and a library only obscures the settle-time tuning that §3.3 requires.

### 7.3 Python host packages

Into the existing `.venv` (see `install.py`):

| Package | Purpose | Action |
|---|---|---|
| `pyserial` | Read the serial stream | **Add to `requirements.txt`** — the only hard new dependency for gates 7–9. |
| `numpy` | Calibration math, resampling | Add explicitly; currently arrives only as a transitive dependency of OpenCV/MediaPipe. |
| `open3d` **or** `pyvista` | 3D twin render (the design notes Step 6) | **Defer** — large (hundreds of MB) and not needed until after gate 9. Open3D's Python-version support lags; verify against the venv's Python before committing to it. |

`install.py` is stdlib-only and already handles venv creation, `requirements.txt`
installation, and model-bundle downloads. Adding `pyserial` + `numpy` to
`requirements.txt` is sufficient — no change to `install.py` itself.

### 7.4 OpenSim (needed only for the design notes Steps 10–11 — download later)

> **Plan for a separate environment.** OpenSim's Python bindings are
> distributed through conda (`opensim-org` channel), are 64-bit only, and are
> **pinned to specific Python versions** that will likely not match this repo's
> `.venv`. Attempting to force them into the existing venv is the predictable
> way to break a working MediaPipe install. Expect a dedicated conda environment
> and a file/IPC boundary between it and the camera suite — **verify the current
> supported Python version on the OpenSim site before installing anything.**

| Item | Source | Notes |
|---|---|---|
| OpenSim 4.x (GUI + SDK) | simtk.org/projects/opensim | ~1 GB. Requires a free SimTK account. |
| OpenSim Python bindings | conda, `opensim-org` channel | Version-pinned to Python; see the warning above. |
| Miniconda/Miniforge | conda.io / conda-forge | Only if no conda is present. |
| Validated OpenSim **hand** model | SimTK (the design notes §6.9) | Confirm the model covers MCP/PIP/DIP muscle attachments and check its licence for research use. |

### 7.5 Assets

| Item | Source | Notes |
|---|---|---|
| Free hand mesh `.obj` | Sketchfab — filter **free + downloadable** | Check the licence. Prefer a clean, watertight, reasonably low-poly mesh; a scanned high-poly model is painful to rig and slow to recolor per frame. |

### 7.6 Simulators (browser, no install)

For gate 1: **Falstad CircuitJS** or **Tinkercad Circuits**. Both run in a
browser with nothing to download. Tinkercad additionally simulates an Arduino,
so the divider *and* the `analogRead` sketch can be exercised before any
hardware arrives.

### 7.7 Repository hygiene

`.gitignore` additions when this work lands:

- Any large downloaded mesh or OpenSim model bundles (consistent with how
  `model/face_landmarker.task` is fetched by `install.py` rather than committed).
- Per-user calibration profiles — they contain personal measurements and are
  device- and user-specific.
- `results/` is already ignored and covers glove session logs.

---

## 8. Risks specific to the firmware layer

These sit alongside — and are separate from — the scientific risks in the design notes
§7.3.

| Risk | Why it bites | Mitigation |
|---|---|---|
| **Mux channel crosstalk** | Insufficient settle time makes one channel bleed into the next. Produces plausible-looking data that is quietly wrong. | Gate 4's explicit isolation test; tune settle time empirically, never assume the datasheet minimum. |
| **Flex sensors fatigue and drift** | The Spectra Symbol strips degrade with repeated bending; a calibration from last month may not hold. | Re-run gate 9 calibration per session; log calibration constants into the session record so drift is reconstructable after the fact. |
| **Blocking serial writes stall the sampler** | Native USB CDC blocks when unread — silently corrupting the timeline that every temporal metric depends on. | The `availableForWrite` guard plus drop-and-report in §4.3; `seq` gaps make loss auditable. |
| **Glove fit changes sensor geometry** | Re-donning the glove shifts sensors relative to joints; the same bend then reads differently. | Treat "one wearing" as the calibration unit. Mark donning events in the session record. |
| **Silent IMU library mismatch** | Wrong library for the board revision compiles cleanly and reports no motion. | Boot banner declares the initialized IMU (§4.2); host refuses frames if it does not match the expected profile. |
| **3.3 V vs 5 V tutorial mismatch** | Copy-pasted constants from a 5 V Uno guide yield a confidently wrong calibration. | §1.2; derive all constants from the board's own measurements at gates 2–3, never from a tutorial. |

---

## 9. Open questions

1. **Palm FSR placement.** the design notes allocates 6 FSRs as 5 fingertips + palm, but
   does not specify where on the palm — thenar eminence and mid-palm measure
   different things during a spiral trace.
2. **Which hand.** The camera tests report true handedness. Build one glove for
   the dominant hand first, or plan a mirrored pair? Affects sensor indexing in
   the frame format.
3. **EMG electrode siting.** the design notes §7.2 wants EMG to validate predicted
   activations, which requires an agonist/antagonist *pair* (e.g. flexor and
   extensor digitorum) — one MyoWare gives only one side of the co-contraction
   it is meant to verify. A second unit may be unavoidable for that validation
   to mean anything.
4. **Session synchronization signal.** ROADMAP §3.1 proposes a keypress zeroing
   both clocks. A physical event visible to *both* sensors (a sharp tap the
   camera sees and the IMU registers) would give a far more defensible
   alignment. Worth deciding before the first joint recording.
