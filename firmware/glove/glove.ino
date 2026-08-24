/*
 * glove.ino - analog acquisition for the sensor-glove digital twin
 *
 * Implements the analog front end and serial protocol specified in
 * docs/GLOVE_FIRMWARE_PLAN.md (sections 3 and 4).
 *
 * Current hardware (build gate 3): two FSR402 pads, p0 on A0 and p1 on A2,
 * each wired as its own divider against the 3V3 rail:
 *     3V3 --- SENSOR --- Ax --- rFixed --- GND
 * Both currently use 10k, but rFixed stays per-channel in CHANNELS[] rather
 * than one global: a divider is most sensitive where rFixed is near the
 * sensor's own resistance, and flex strips (when they return, on the odd pins)
 * sit in a very different resistance band from an FSR. Adding the remaining
 * sensors, and the CD74HC4067 mux, is a table edit rather than a rewrite.
 *
 * The onboard IMU (gate 5) rides in the same frame as six extra columns. It is
 * NOT an analog channel: it never touches the divider maths, and its columns
 * are declared in the banner with kinds `accel`/`gyro` so the host cannot apply
 * a resistance curve to an acceleration.
 *
 * Firmware emits RAW counts only - ADC counts for the analog channels, and
 * integer milli-units for the IMU. Conversion to newtons and degrees is a
 * per-user host-side step (plan section 2) so recalibration never needs a
 * reflash. The one exception is the 'D' diagnostic mode, which prints derived
 * millivolts/ohms for bench work and never touches the data frames.
 */

/* ---------- board differences ------------------------------------------- */
/*
 * ADC_FULLSCALE_MV is the ADC *reference* (what a reading of ADC_MAX means).
 * VDIV_SUPPLY_MV is the rail feeding the top of the divider.
 * On a Nano 33 BLE these are both 3.3 V. On a classic 5 V Nano the reference
 * is 5 V while the divider is fed from the 3V3 pin, so they differ - which is
 * exactly why they are two separate constants.
 */
#if defined(ARDUINO_ARCH_MBED) || defined(ARDUINO_ARCH_NRF52840)
  #define GLOVE_BOARD        "nano33ble"
  #define ADC_FULLSCALE_MV   3300
  #define HAS_ADC_RESOLUTION 1
  #define ADC_BITS           12
#elif defined(ARDUINO_ARCH_AVR)
  #define GLOVE_BOARD        "nano-avr"
  #define ADC_FULLSCALE_MV   5000   /* default AVCC reference - see notes */
  #define HAS_ADC_RESOLUTION 0
  #define ADC_BITS           10     /* AVR has no analogReadResolution() */
#else
  #warning "Unrecognised board - assuming a 3.3 V ADC reference."
  #define GLOVE_BOARD        "unknown"
  #define ADC_FULLSCALE_MV   3300
  #define HAS_ADC_RESOLUTION 0
  #define ADC_BITS           10
#endif

/*
 * Full-scale count. Every place that converts counts to volts MUST use this,
 * never a literal 1023 - a mismatch here silently corrupts every derived
 * resistance and force downstream.
 */
#define ADC_MAX ((1L << ADC_BITS) - 1L)

/* ---------- IMU ---------------------------------------------------------- */
/*
 * PICK THE LINE THAT MATCHES THE SILKSCREEN ON YOUR BOARD, then re-flash.
 * The original Nano 33 BLE carries an LSM9DS1; the Rev2 carries a BMI270 +
 * BMM150, and they need different Arduino libraries (plan section 1.3).
 * Install the one you pick from the Developer page's toolchain buttons.
 *
 * WHY THIS IS AN EXPLICIT SWITCH AND NOT __has_include. That was tried first
 * and is silently broken: arduino-cli (and the IDE, which uses it) discovers
 * which libraries a sketch needs by compiling and resolving the *missing
 * header errors*. __has_include swallows the error, so the resolver never
 * learns about the dependency and the library is never added to the build.
 * Measured 2026-08-23: byte-for-byte identical binaries with and without
 * Arduino_LSM9DS1 installed, and zero mentions of it in a verbose build. An
 * auto-detecting sketch would therefore have shipped imu=none forever while
 * looking like it had auto-detected. A plain #include fails loudly instead,
 * naming the header it cannot find.
 *
 * GLOVE_IMU_NONE is a legitimate build: no motion columns, no IMU library
 * needed, everything else unchanged.
 */
#define GLOVE_IMU_LSM9DS1     /* original Nano 33 BLE  */
//#define GLOVE_IMU_BMI270    /* Nano 33 BLE Rev2      */
//#define GLOVE_IMU_NONE      /* build without motion  */

#if defined(GLOVE_IMU_BMI270)
  #include <Arduino_BMI270_BMM150.h>
  #define HAS_IMU 1
  #define IMU_LIB_NAME "BMI270_BMM150"
#elif defined(GLOVE_IMU_LSM9DS1)
  #include <Arduino_LSM9DS1.h>
  #define HAS_IMU 1
  #define IMU_LIB_NAME "LSM9DS1"
#else
  #define HAS_IMU 0
  #define IMU_LIB_NAME "none"
#endif

#include <math.h>   /* lroundf, for the IMU's float -> milli-unit step */

/*
 * Transport scale for the IMU columns: values are emitted as integers in
 * milli-units (milli-g, milli-degrees/second) so the frame stays all-integer
 * and the host parser needs no float path. The banner publishes this as
 * `imu_scale=` - do not hardcode 1000 on the host.
 *
 * This is a TRANSPORT unit, not a resolution claim. An LSM9DS1 at +/-2000 dps
 * resolves about 70 mdps per LSB; emitting mdps does not invent precision, it
 * just avoids a decimal point on the wire.
 */
static const int32_t IMU_SCALE = 1000;

/* Column names, in frame order. Kinds are published in the banner's chan=
 * field so the host routes them away from the divider maths. */
static const char *IMU_COLS[6] = { "ax", "ay", "az", "gx", "gy", "gz" };

/* ---------- configuration ------------------------------------------------ */

#define FW_VERSION      "0.5.0"
/*
 * Frame layout is unchanged from proto 1 by the move to 12-bit: only the value
 * scale moved, and the banner's adc_bits already tells the host about that. So
 * this stays 1 rather than forcing a host-side version bump.
 */
#define PROTO_VERSION   1

static const uint16_t SAMPLE_RATE_HZ  = 100;
static const uint32_t FRAME_PERIOD_US = 1000000UL / SAMPLE_RATE_HZ;

/* Divider supply. You wired the FSR to the 3V3 pin. */
static const uint16_t VDIV_SUPPLY_MV = 3300;

/*
 * Legacy banner value only. Each channel carries its own rFixed (see
 * CHANNELS[] below); this is what the banner's `r_fixed=` field reports so a
 * host predating the per-channel `chan=` field still gets a sane number for
 * the force channels rather than nothing at all.
 */
static const uint32_t R_FIXED_DEFAULT_OHMS = 10000;

/* Reads averaged per channel per timestep - noise reduction within one
 * sample, which does not touch the inter-sample dynamics we care about.
 * Raised to 8 with the move to 12-bit: the extra two bits are only worth
 * having if they sit above the ADC's noise floor.
 *
 * Raised again to 16 at gate 2. At the top of the FSR's range the force curve
 * is steep enough that a single count is worth roughly a newton, so ADC noise
 * reads as large force swings; averaging more reads per timestep is the one
 * noise reduction plan section 2 allows, because it stays *within* a timestep
 * and so cannot touch the inter-sample dynamics (tremor) we are measuring.
 * BUDGET: this is affordable at 2 channels. 11 channels x 16 reads will not
 * fit the 10 ms frame period - bring this back down when the mux lands and
 * re-check the measured rate at gate 6.
 */
static const uint8_t OVERSAMPLE = 16;

/* Mux settle time. Raise this if adjacent channels bleed into each other. */
static const uint8_t MUX_SETTLE_US = 5;

/* CD74HC4067 select lines - unused until a channel sets muxCh >= 0. */
static const uint8_t MUX_SEL_PINS[4] = { 2, 3, 4, 5 };

struct AnalogChannel {
  const char *name;   /* protocol column name */
  const char *kind;   /* "fsr" | "flex" - which curve the host should apply */
  uint8_t     pin;    /* analog pin (mux common pin if muxCh >= 0) */
  int8_t      muxCh;  /* -1 = wired directly, else CD74HC4067 channel */
  uint32_t    rFixed; /* this channel's own low-side resistor, ohms */
};

/*
 * Column order here IS the frame's column order, and is published in the boot
 * banner so the host can verify the layout before trusting a single sample.
 * Naming follows the plan: f0..f4 = flex thumb->pinky, p0..p5 = FSR.
 *
 * `kind` matters as much as the resistor value: the host applies a *published
 * FSR402 force curve* to force channels, and that curve is meaningless for a
 * flex strip. Mislabel a channel here and the dev page will print confident
 * newtons for a bending finger.
 *
 * PIN CONVENTION: force sensors live on the EVEN analog pins, so p<n> is on
 * A(2n) - p0/A0, p1/A2, p2/A4, p3/A6. Odd pins are reserved for flex strips.
 * Adding the next FSR is one line here plus a flash; nothing on the host or
 * the dev page changes, because both read the layout from the boot banner.
 *
 * ONLY DECLARE PINS THAT ARE PHYSICALLY FITTED. An unconnected analog pin
 * floats and produces convincing-looking garbage rather than an obvious zero.
 *
 * rFixed MUST MATCH THE RESISTOR PHYSICALLY ON THE BOARD, per channel. This is
 * the most expensive lesson in this file: the flex channel once said 47k while
 * the bench build used 10k, which made every computed resistance 4.7x too high
 * (a healthy 34k strip read as 160k) and looked exactly like a broken sensor
 * for a whole debugging session. The firmware cannot detect this - the divider
 * maths cannot tell a wrong constant from a wrong sensor, and both produce a
 * plausible number. If you swap a physical resistor, change it here in the
 * same breath.
 *
 * 10k on an FSR402 centres on a moderate press, deliberately kept: plan 5b
 * weighed lowering it and rejected it, because the resolution gained sits
 * above the part's rated 20 N and costs light-touch resolution.
 */
static const AnalogChannel CHANNELS[] = {
  { "p0", "fsr", A0, -1, 10000 },
  { "p1", "fsr", A2, -1, 10000 },
};
static const uint8_t N_CHANNELS = sizeof(CHANNELS) / sizeof(CHANNELS[0]);

/* ---------- state -------------------------------------------------------- */

static uint32_t g_seq       = 0;
static uint32_t g_epochUs   = 0;    /* micros() at the last 'Z' */
static uint32_t g_nextDueUs = 0;
static uint32_t g_missed    = 0;    /* frames skipped: deadline or full TX buffer */
static bool     g_streaming = true;
static bool     g_diag      = false;

static uint16_t g_sample[sizeof(CHANNELS) / sizeof(CHANNELS[0])];
static uint16_t g_min[sizeof(CHANNELS) / sizeof(CHANNELS[0])];
static uint16_t g_max[sizeof(CHANNELS) / sizeof(CHANNELS[0])];

/*
 * IMU state. g_imuOk is decided at runtime by IMU.begin(): a library that is
 * installed but cannot talk to the chip must NOT publish six columns of
 * zeroes, because a flat zero trace is indistinguishable from a still hand.
 * When it is false the columns are not declared and not emitted, and the
 * banner says imu=none - the same rule the analog table follows, where only
 * physically fitted pins are declared.
 */
static bool    g_imuOk   = false;
static int32_t g_imu[6]  = {0, 0, 0, 0, 0, 0};   /* ax..az mg, gx..gz mdps */
static uint32_t g_imuHeld = 0;   /* frames that reused the previous sample */

/* ---------- acquisition -------------------------------------------------- */

static void selectMux(int8_t ch) {
  for (uint8_t i = 0; i < 4; i++) {
    digitalWrite(MUX_SEL_PINS[i], (ch >> i) & 0x01);
  }
  delayMicroseconds(MUX_SETTLE_US);
}

/* Takes plain scalars rather than the struct: Arduino auto-generates function
 * prototypes and can place them above the struct declaration. */
static uint16_t readChannel(uint8_t pin, int8_t muxCh) {
  if (muxCh >= 0) selectMux(muxCh);

  /* Discard the first conversion after an input change: the sample-and-hold
   * still carries charge from the previous channel. This is the crosstalk
   * that gate 4 tests for. */
  (void)analogRead(pin);

  /* uint32 deliberately: at 12-bit, 16 x 4095 = 65520 clears uint16 by only
   * 15 counts, which is too tight to leave as a trap for the next edit. */
  uint32_t sum = 0;
  for (uint8_t i = 0; i < OVERSAMPLE; i++) sum += analogRead(pin);
  return (uint16_t)(sum / OVERSAMPLE);
}

static void sampleAll() {
  for (uint8_t i = 0; i < N_CHANNELS; i++) {
    g_sample[i] = readChannel(CHANNELS[i].pin, CHANNELS[i].muxCh);
    if (g_sample[i] < g_min[i]) g_min[i] = g_sample[i];
    if (g_sample[i] > g_max[i]) g_max[i] = g_sample[i];
  }
}

/*
 * The IMU runs on its own internal output-data rate (~104-119 Hz on the
 * LSM9DS1, ~100 Hz on the BMI270) which is NOT locked to our 100 Hz frame
 * grid. Some frames therefore find no new sample waiting.
 *
 * Never block waiting for one - that would stall the sampler and corrupt the
 * timeline every temporal metric depends on. Reuse the previous value and
 * count it. A held sample is a repeated sample, and repeated samples flatten
 * exactly the high-frequency content this sensor is fitted to measure, so the
 * count is reported in the 'D' diagnostics and the host also detects holds
 * directly by looking for identical consecutive triples.
 */
static void sampleImu() {
#if HAS_IMU
  if (!g_imuOk) return;
  bool fresh = false;
  float x, y, z;
  if (IMU.accelerationAvailable()) {
    IMU.readAcceleration(x, y, z);
    g_imu[0] = (int32_t)lroundf(x * IMU_SCALE);
    g_imu[1] = (int32_t)lroundf(y * IMU_SCALE);
    g_imu[2] = (int32_t)lroundf(z * IMU_SCALE);
    fresh = true;
  }
  if (IMU.gyroscopeAvailable()) {
    IMU.readGyroscope(x, y, z);
    g_imu[3] = (int32_t)lroundf(x * IMU_SCALE);
    g_imu[4] = (int32_t)lroundf(y * IMU_SCALE);
    g_imu[5] = (int32_t)lroundf(z * IMU_SCALE);
    fresh = true;
  }
  if (!fresh) g_imuHeld++;
#endif
}

/* ---------- derived values (diagnostics only) ---------------------------- */

static uint16_t adcToMillivolts(uint16_t adc) {
  return (uint16_t)(((uint32_t)adc * ADC_FULLSCALE_MV) / (uint32_t)ADC_MAX);
}

/* R_sensor = rFixed * (Vsupply - Vout) / Vout. Returns -1 for "open".
 * Takes rFixed as an argument rather than reading a global: the FSR and the
 * flex strip sit on different resistors, and sharing one value here would
 * silently scale one of them wrong. */
static int32_t sensorOhms(uint16_t adc, uint32_t rFixed) {
  int32_t mv = adcToMillivolts(adc);
  if (mv <= 0) return -1;
  if (mv >= VDIV_SUPPLY_MV) return 0;
  return ((int32_t)rFixed * (int32_t)(VDIV_SUPPLY_MV - mv)) / mv;
}

/* ---------- output ------------------------------------------------------- */

static void emitBanner() {
  Serial.print(F("#GLOVE fw=" FW_VERSION " proto="));
  Serial.print(PROTO_VERSION);
  Serial.print(F(" board=" GLOVE_BOARD " rate="));
  Serial.print(SAMPLE_RATE_HZ);
  Serial.print(F(" adc_bits="));
  Serial.print(ADC_BITS);
  Serial.print(F(" adc_ref_mv="));
  Serial.print(ADC_FULLSCALE_MV);
  Serial.print(F(" vdiv_mv="));
  Serial.print(VDIV_SUPPLY_MV);
  Serial.print(F(" r_fixed="));
  Serial.print(R_FIXED_DEFAULT_OHMS);
  /* imu= is the compiled-in library name ONLY if the chip actually answered.
   * A library that is installed but silent must read as none, or the host
   * will expect six columns that never arrive. */
  Serial.print(F(" imu="));
  Serial.print(g_imuOk ? IMU_LIB_NAME : "none");
  if (g_imuOk) {
    Serial.print(F(" imu_scale="));
    Serial.print(IMU_SCALE);
  }
  Serial.print(F(" emg=0 cols=seq,t_us"));
  for (uint8_t i = 0; i < N_CHANNELS; i++) {
    Serial.print(',');
    Serial.print(CHANNELS[i].name);
  }
  if (g_imuOk) {
    for (uint8_t i = 0; i < 6; i++) {
      Serial.print(',');
      Serial.print(IMU_COLS[i]);
    }
  }
  /*
   * Per-channel detail: name:kind:rFixed, comma separated. This is an ADDITIVE
   * banner field - `cols` and the frame layout are unchanged, and the host's
   * parser ignores keys it does not know - so proto stays 1 and older
   * recordings still read. A host that does not understand `chan` falls back
   * to r_fixed above and to the f./p. naming convention for kind.
   */
  Serial.print(F(" chan="));
  for (uint8_t i = 0; i < N_CHANNELS; i++) {
    if (i) Serial.print(',');
    Serial.print(CHANNELS[i].name);
    Serial.print(':');
    Serial.print(CHANNELS[i].kind);
    Serial.print(':');
    Serial.print(CHANNELS[i].rFixed);
  }
  /* IMU entries carry a kind but NO third field: there is no low-side
   * resistor on an accelerometer, and putting the scale in that slot would
   * invite a host to read it as ohms. The scale is a separate banner key. */
  if (g_imuOk) {
    for (uint8_t i = 0; i < 6; i++) {
      Serial.print(',');   /* CHANNELS[] is never empty, so a comma always leads */
      Serial.print(IMU_COLS[i]);
      Serial.print(i < 3 ? ":accel" : ":gyro");
    }
  }
  Serial.println();
}

static void emitFrame() {
  /*
   * Native USB CDC blocks when the host is not draining the port, which would
   * stall the sampler and corrupt the timeline every temporal metric depends
   * on. Drop the frame instead - the seq gap makes the loss auditable on the
   * host, whereas a stalled sampler is invisible.
   */
  /* seq + t_us + analog counts + (when fitted) six signed milli-unit fields,
   * the widest of which is a gyro reading at +/-2000000. */
  const int NEEDED = 12 + 12 + (N_CHANNELS * 6) + (g_imuOk ? 6 * 9 : 0);
  if (!Serial) {
    g_missed++;
    return;
  }
  /*
   * Print::availableForWrite() is a virtual that DEFAULTS TO 0 on cores which
   * do not override it - the Nano 33 BLE's USB CDC is one of them. Treating 0
   * as "no room" silently drops every frame, so only honour this reading when
   * it reports an actual capacity.
   */
  const int room = Serial.availableForWrite();
  if (room > 0 && room < NEEDED) {
    g_missed++;
    return;
  }

  Serial.print(F("G,"));
  Serial.print(g_seq);
  Serial.print(',');
  Serial.print(micros() - g_epochUs);
  for (uint8_t i = 0; i < N_CHANNELS; i++) {
    Serial.print(',');
    Serial.print(g_sample[i]);
  }
  if (g_imuOk) {
    for (uint8_t i = 0; i < 6; i++) {
      Serial.print(',');
      Serial.print(g_imu[i]);
    }
  }
  Serial.println();
}

static void emitDiag() {
  for (uint8_t i = 0; i < N_CHANNELS; i++) {
    Serial.print(F("#DIAG "));
    Serial.print(CHANNELS[i].name);
    Serial.print(F(" adc="));
    Serial.print(g_sample[i]);
    Serial.print(F(" mv="));
    Serial.print(adcToMillivolts(g_sample[i]));
    Serial.print(F(" ohm="));
    Serial.print(sensorOhms(g_sample[i], CHANNELS[i].rFixed));
    Serial.print(F(" min="));
    Serial.print(g_min[i]);
    Serial.print(F(" max="));
    Serial.print(g_max[i]);
    Serial.print(F(" missed="));
    Serial.println(g_missed);
  }
  if (g_imuOk) {
    Serial.print(F("#DIAG imu mg="));
    Serial.print(g_imu[0]); Serial.print(',');
    Serial.print(g_imu[1]); Serial.print(',');
    Serial.print(g_imu[2]);
    Serial.print(F(" mdps="));
    Serial.print(g_imu[3]); Serial.print(',');
    Serial.print(g_imu[4]); Serial.print(',');
    Serial.print(g_imu[5]);
    /* Held frames reused the previous sample because the IMU's own output
     * rate had nothing new. High counts mean the effective IMU rate is below
     * the frame rate, which matters for anything spectral. */
    Serial.print(F(" held="));
    Serial.println(g_imuHeld);
  }
}

/* ---------- commands ----------------------------------------------------- */

static void resetSpans() {
  for (uint8_t i = 0; i < N_CHANNELS; i++) {
    /* Must seed from ADC_MAX, not a literal 1023: at 12-bit a seed of 1023
     * would pin the minimum there for any reading above it. */
    g_min[i] = (uint16_t)ADC_MAX;
    g_max[i] = 0;
  }
}

static void handleCommand(char c) {
  switch (c) {
    case '?': emitBanner();                      break;
    case 'S': g_streaming = true;                break;
    case 'X': g_streaming = false;               break;
    case 'D': g_diag = !g_diag;                  break;
    case 'Z':
      g_seq     = 0;
      g_epochUs = micros();
      g_missed  = 0;
      g_imuHeld = 0;
      resetSpans();
      Serial.println(F("#ZERO"));
      break;
    default:  /* ignore newlines and stray bytes */ break;
  }
}

/* ---------- lifecycle ---------------------------------------------------- */

void setup() {
  Serial.begin(115200);
  /* Bounded wait so the banner is not lost to a slow host, but the board
   * still runs headless if nothing ever opens the port. */
  while (!Serial && millis() < 3000) { }

#if HAS_ADC_RESOLUTION
  analogReadResolution(ADC_BITS);
#endif

  for (uint8_t i = 0; i < 4; i++) pinMode(MUX_SEL_PINS[i], OUTPUT);

#if HAS_IMU
  g_imuOk = IMU.begin();
  if (!g_imuOk) {
    /* Say so loudly on the wire. Silence here is how "wrong library for this
     * board revision" hides for a week. */
    Serial.println(F("!IMU " IMU_LIB_NAME " begin() failed - no motion columns"));
  }
#endif

  resetSpans();
  g_epochUs   = micros();
  g_nextDueUs = micros() + FRAME_PERIOD_US;

  emitBanner();
}

void loop() {
  while (Serial.available()) handleCommand((char)Serial.read());

  if ((int32_t)(micros() - g_nextDueUs) < 0) return;

  /* Absolute grid: accumulate the period rather than restarting from "now",
   * so the schedule cannot drift. Same technique as core/tapping's metronome. */
  g_nextDueUs += FRAME_PERIOD_US;
  if ((int32_t)(micros() - g_nextDueUs) >= 0) {
    /* More than a full period behind - resync instead of running a burst of
     * catch-up frames carrying stale timestamps. */
    g_missed++;
    g_nextDueUs = micros() + FRAME_PERIOD_US;
  }

  sampleAll();
  sampleImu();
  g_seq++;

  if (g_streaming) emitFrame();

  if (g_diag) {
    static uint32_t lastDiagMs = 0;
    if (millis() - lastDiagMs >= 200) {
      lastDiagMs = millis();
      emitDiag();
    }
  }
}
