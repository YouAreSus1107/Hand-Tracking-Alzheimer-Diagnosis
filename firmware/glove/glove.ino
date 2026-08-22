/*
 * glove.ino - analog acquisition for the sensor-glove digital twin
 *
 * Implements the analog front end and serial protocol specified in
 * docs/GLOVE_FIRMWARE_PLAN.md (sections 3 and 4).
 *
 * Current hardware (build gate 3): one FSR402 on A0, wired as
 *     3V3 --- FSR --- A0 --- R_FIXED --- GND
 * Channels are declared in the CHANNELS[] table below; adding the remaining
 * flex/FSR sensors (and the CD74HC4067 mux) is a table edit, not a rewrite.
 *
 * Firmware emits RAW ADC counts only. Conversion to newtons and degrees is a
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

/* ---------- configuration ------------------------------------------------ */

#define FW_VERSION      "0.2.0"
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
 * Fixed low-side resistor, ohms. A divider is most sensitive where
 * R_FIXED is near the sensor's resistance, so this value sets *which* force
 * band gets the most ADC range. 10k centres on a moderate press; if light
 * touch matters more (it probably does for fine-motor work), try 47k-100k
 * and compare the spans you record at gate 3.
 */
static const uint32_t R_FIXED_OHMS = 10000;

/* Reads averaged per channel per timestep - noise reduction within one
 * sample, which does not touch the inter-sample dynamics we care about.
 * Raised to 8 with the move to 12-bit: the extra two bits are only worth
 * having if they sit above the ADC's noise floor. */
static const uint8_t OVERSAMPLE = 8;

/* Mux settle time. Raise this if adjacent channels bleed into each other. */
static const uint8_t MUX_SETTLE_US = 5;

/* CD74HC4067 select lines - unused until a channel sets muxCh >= 0. */
static const uint8_t MUX_SEL_PINS[4] = { 2, 3, 4, 5 };

struct AnalogChannel {
  const char *name;   /* protocol column name */
  uint8_t     pin;    /* analog pin (mux common pin if muxCh >= 0) */
  int8_t      muxCh;  /* -1 = wired directly, else CD74HC4067 channel */
};

/*
 * Column order here IS the frame's column order, and is published in the boot
 * banner so the host can verify the layout before trusting a single sample.
 * Naming follows the plan: f0..f4 = flex thumb->pinky, p0..p5 = FSR.
 */
static const AnalogChannel CHANNELS[] = {
  { "p0", A0, -1 },
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

/* ---------- derived values (diagnostics only) ---------------------------- */

static uint16_t adcToMillivolts(uint16_t adc) {
  return (uint16_t)(((uint32_t)adc * ADC_FULLSCALE_MV) / (uint32_t)ADC_MAX);
}

/* R_sensor = R_FIXED * (Vsupply - Vout) / Vout. Returns -1 for "open". */
static int32_t sensorOhms(uint16_t adc) {
  int32_t mv = adcToMillivolts(adc);
  if (mv <= 0) return -1;
  if (mv >= VDIV_SUPPLY_MV) return 0;
  return (R_FIXED_OHMS * (int32_t)(VDIV_SUPPLY_MV - mv)) / mv;
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
  Serial.print(R_FIXED_OHMS);
  Serial.print(F(" imu=none emg=0 cols=seq,t_us"));
  for (uint8_t i = 0; i < N_CHANNELS; i++) {
    Serial.print(',');
    Serial.print(CHANNELS[i].name);
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
  const int NEEDED = 12 + 12 + (N_CHANNELS * 6);
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
    Serial.print(sensorOhms(g_sample[i]));
    Serial.print(F(" min="));
    Serial.print(g_min[i]);
    Serial.print(F(" max="));
    Serial.print(g_max[i]);
    Serial.print(F(" missed="));
    Serial.println(g_missed);
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
