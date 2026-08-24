/* Tapping engine — a direct port of core/tapping/{detector,metrics,modes}.py.
   REMOTE_SESSION_PLAN.md §3.1, WEB_PLATFORM_PLAN.md §3.

   Python stays the normative implementation (web plan §3, "the parity
   discipline"). This file is a mechanical translation and must not acquire
   improvements of its own: a silent drift in CV% invalidates every
   longitudinal comparison between a desktop session and a remote one. The
   parity harness in tests/parity.mjs checks it against vectors dumped from the
   Python engine, and that is the thing that keeps this honest.

   Pure: no DOM, no MediaPipe, no network. */

/* ── modes.py ─────────────────────────────────────────────────────────── */

export const MODES = {
  big_and_fast: {
    key: "big_and_fast",
    title: "Big & Fast",
    paced: false,
    duration_s: 10.0,
    expected_rate_hz: 5.0,
    min_taps: 10,
    trim_taps: 2,
    cv_typical: 15.0,
    cv_monitor: 25.0,
  },
};

// TapMode.min_intertap_s / max_iti_ms are properties in Python.
export function minIntertapS(mode) { return 0.5 / mode.expected_rate_hz; }
export function maxItiMs(mode) {
  return mode.paced ? mode.interval_s * 1000 * 1.5
                    : 3.0 * 1000.0 / mode.expected_rate_hz;
}

/* ── detector.py ──────────────────────────────────────────────────────── */

export const CLOSE_FRAC = 0.40;
export const OPEN_FRAC = 0.55;

/** Thumb-tip↔index-tip distance normalised by hand span. `landmarks` is an
 *  array of {x, y} (or [x, y]) in normalised image space. null on a glitch. */
export function thumbIndexDistance(landmarks) {
  const at = (i) => {
    const p = landmarks[i];
    return Array.isArray(p) ? { x: p[0], y: p[1] } : p;
  };
  const w = at(0), m = at(9), th = at(4), ix = at(8);
  const span = Math.hypot(w.x - m.x, w.y - m.y);
  if (span < 1e-4) return null;
  return Math.hypot(th.x - ix.x, th.y - ix.y) / span;
}

export class Calibrator {
  static MIN_FRAMES = 45;
  static MIN_RANGE = 0.30;
  static MIN_CYCLES = 2;
  static TIMEOUT_S = 20.0;

  constructor() {
    this._samples = [];
    this._t0 = null;
    this._belowMid = false;
    this.cycles = 0;
  }

  update(t, d) {
    if (this._t0 === null) this._t0 = t;
    this._samples.push(d);
    const [lo, hi] = this._percentiles();
    if (hi - lo >= Calibrator.MIN_RANGE * 0.6) {
      const mid = lo + 0.4 * (hi - lo);
      if (d < mid && !this._belowMid) {
        this._belowMid = true;
        this.cycles += 1;
      } else if (d > lo + 0.6 * (hi - lo)) {
        this._belowMid = false;
      }
    }
  }

  _percentiles() {
    if (this._samples.length < 5) return [0.0, 0.0];
    const s = [...this._samples].sort((a, b) => a - b);
    const n = s.length;
    // Python's int() truncates toward zero; Math.floor matches for n >= 0.
    return [s[Math.floor(n * 0.05)], s[Math.min(n - 1, Math.floor(n * 0.95))]];
  }

  get rangeSeen() {
    const [lo, hi] = this._percentiles();
    return hi - lo;
  }

  get progress() {
    const f = Math.min(1.0, this._samples.length / Calibrator.MIN_FRAMES);
    const r = Math.min(1.0, this.rangeSeen / Calibrator.MIN_RANGE);
    const c = Math.min(1.0, this.cycles / Calibrator.MIN_CYCLES);
    return Math.min(f, r, c);
  }

  get done() {
    return this._samples.length >= Calibrator.MIN_FRAMES
        && this.rangeSeen >= Calibrator.MIN_RANGE
        && this.cycles >= Calibrator.MIN_CYCLES;
  }

  timedOut(t) {
    return this._t0 !== null && (t - this._t0) > Calibrator.TIMEOUT_S;
  }

  result() { return this._percentiles(); }   // [d_closed, d_open]
}

export class TapDetector {
  constructor(minIntertap, emaAlpha, dClosed, dOpen) {
    const rng = Math.max(1e-6, dOpen - dClosed);
    this.closeAt = dClosed + CLOSE_FRAC * rng;
    this.openAt = dClosed + OPEN_FRAC * rng;
    this.minIntertapS = minIntertap;
    this.emaAlpha = emaAlpha;
    this._ema = null;
    this._closed = false;
    this.tapTimes = [];
    this.series = [];          // [t, d] pairs
    this.lastTapT = -1e9;
  }

  update(t, dRaw) {
    if (dRaw === null || dRaw === undefined) return false;
    this._ema = this._ema === null ? dRaw
      : this.emaAlpha * dRaw + (1 - this.emaAlpha) * this._ema;
    const d = this._ema;
    this.series.push([t, d]);
    let tapped = false;
    if (!this._closed && d < this.closeAt) {
      this._closed = true;
      if (t - this.lastTapT >= this.minIntertapS) {
        this.tapTimes.push(t);
        this.lastTapT = t;
        tapped = true;
      }
    } else if (this._closed && d > this.openAt) {
      this._closed = false;
    }
    return tapped;
  }

  get smoothed() { return this._ema; }
}

/* ── metrics.py ───────────────────────────────────────────────────────── */

function sd(vals) {
  if (vals.length < 2) return null;
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const varr = vals.reduce((a, v) => a + (v - mean) ** 2, 0) / (vals.length - 1);
  return Math.sqrt(varr);
}

function median(vals) {
  const s = [...vals].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[Math.floor(n / 2)] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

function slope(xs, ys) {
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  const denom = xs.reduce((a, x) => a + (x - mx) ** 2, 0);
  if (denom < 1e-9) return null;
  let num = 0;
  for (let i = 0; i < n; i++) num += (xs[i] - mx) * (ys[i] - my);
  return num / denom;
}

export function band(cvPct, mode) {
  if (cvPct < mode.cv_typical) return ["success", "Within typical range"];
  if (cvPct < mode.cv_monitor) return ["warning", "Mild variability - consider monitoring"];
  return ["danger", "Elevated variability - recommend follow-up"];
}

/** Port of compute_metrics(). Same keys, same order of decisions, same
 *  early-return reasons — those strings are shown to the participant. */
export function computeMetrics(mode, tapTimes, series, tStart, tEnd,
                               beatTimes = null, handVisibleRatio = 1.0) {
  const out = {
    scoreable: false,
    reason: null,
    taps: tapTimes.length,
    duration_s: Math.round((tEnd - tStart) * 100) / 100,
    frequency_hz: null, mean_iti_ms: null, iiv_ms: null,
    cv_pct: null, amplitude_mean: null, amplitude_cv_pct: null,
    decrement_pct_per_s: null, sync_sd_ms: null,
    mean_latency_ms: null, hits: null, misses: null,
    status: null, label: null,
  };

  if (tapTimes.length < mode.min_taps) {
    out.reason = handVisibleRatio < 0.8
      ? "Your hand was out of view for part of the test - keep it in the frame and try again."
      : `Only ${tapTimes.length} taps detected - at least ${mode.min_taps} are needed for a reliable score.`;
    return out;
  }

  let taps = tapTimes;
  if (taps.length - mode.trim_taps >= mode.min_taps) taps = taps.slice(mode.trim_taps);

  const itiMs = [];
  for (let i = 0; i < taps.length - 1; i++) itiMs.push((taps[i + 1] - taps[i]) * 1000);

  const cutoff = mode.paced ? maxItiMs(mode) : 3.0 * median(itiMs);
  const iti = itiMs.filter((v) => v <= cutoff);
  if (iti.length < mode.min_taps - 1) {
    out.reason = "Tapping was too irregular to score - large pauses interrupted the rhythm. Try to keep a continuous motion.";
    return out;
  }

  const meanIti = iti.reduce((a, b) => a + b, 0) / iti.length;
  const iiv = sd(iti);
  const cv = (iiv !== null && meanIti > 0) ? (iiv / meanIti) * 100 : null;
  if (cv === null) {
    out.reason = "Not enough valid intervals to compute variability.";
    return out;
  }

  out.mean_iti_ms = meanIti;
  out.iiv_ms = iiv;
  out.cv_pct = cv;
  out.frequency_hz = 1000.0 / meanIti;

  const mids = [], rates = [];
  for (let i = 0; i < taps.length - 1; i++) {
    const itiI = (taps[i + 1] - taps[i]) * 1000;
    if (itiI <= cutoff) {
      mids.push((taps[i] + taps[i + 1]) / 2 - tStart);
      rates.push(1000.0 / itiI);
    }
  }
  const sl = slope(mids, rates);
  if (sl !== null && rates.length) {
    const meanRate = rates.reduce((a, b) => a + b, 0) / rates.length;
    if (meanRate > 0) out.decrement_pct_per_s = (sl / meanRate) * 100.0;
  }

  const amps = [];
  for (let i = 0; i < taps.length - 1; i++) {
    const seg = series.filter(([t]) => t >= taps[i] && t < taps[i + 1]).map(([, d]) => d);
    if (seg.length >= 2) amps.push(Math.max(...seg) - Math.min(...seg));
  }
  if (amps.length >= 2) {
    out.amplitude_mean = amps.reduce((a, b) => a + b, 0) / amps.length;
    const aSd = sd(amps);
    if (aSd !== null && out.amplitude_mean > 0) {
      out.amplitude_cv_pct = (aSd / out.amplitude_mean) * 100.0;
    }
  }

  if (mode.paced && beatTimes && beatTimes.length) {
    const firstTap = new Map();
    const half = mode.interval_s / 2;
    for (const tt of tapTimes) {
      let j = 0;
      for (let k = 1; k < beatTimes.length; k++) {
        if (Math.abs(beatTimes[k] - tt) < Math.abs(beatTimes[j] - tt)) j = k;
      }
      if (Math.abs(tt - beatTimes[j]) <= half && !firstTap.has(j)) firstTap.set(j, tt);
    }
    const keys = [...firstTap.keys()].sort((a, b) => a - b);
    const lats = keys.map((j) => (firstTap.get(j) - beatTimes[j]) * 1000);
    out.hits = firstTap.size;
    out.misses = beatTimes.length - firstTap.size;
    if (lats.length >= 2) {
      out.mean_latency_ms = lats.reduce((a, b) => a + b, 0) / lats.length;
      out.sync_sd_ms = sd(lats);
    }
  }

  [out.status, out.label] = band(cv, mode);
  out.scoreable = true;
  return out;
}
