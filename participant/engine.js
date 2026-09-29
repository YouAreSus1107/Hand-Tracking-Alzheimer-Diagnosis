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
    duration_s: 20.0,
    expected_rate_hz: 1.2,
    max_rate_hz: 5.0,
    min_effort_hz: 0.5,
    min_taps: 6,
    trim_taps: 2,
    cv_typical: 15.0,
    cv_monitor: 25.0,
    compat_window_s: 10.0,
  },
};

// TapMode.min_intertap_s / max_iti_ms are properties in Python.
// The debounce follows max_rate_hz, not expected_rate_hz — see modes.py.
export function minIntertapS(mode) { return 0.5 / (mode.max_rate_hz || mode.expected_rate_hz); }
export function maxItiMs(mode) {
  return mode.paced ? mode.interval_s * 1000 * 1.5
                    : 3.0 * 1000.0 / mode.expected_rate_hz;
}

/* ── detector.py ──────────────────────────────────────────────────────── */

export const CLOSE_FRAC = 0.40;
export const OPEN_FRAC = 0.55;

// Rolling-envelope adaptation: the thresholds follow the excursion actually
// being performed rather than the wide-open warm-up. See detector.py's
// module docstring for why a frozen threshold drops the shallow half of a run.
export const ENVELOPE_S = 3.0;
export const ENVELOPE_MIN_FRAMES = 20;
export const ADAPT_MIN_RANGE_FRAC = 0.20;

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
  constructor(minIntertap, emaAlpha, dClosed, dOpen, adaptive = true) {
    const rng = Math.max(1e-6, dOpen - dClosed);
    this.calRange = rng;
    this.calCloseAt = dClosed + CLOSE_FRAC * rng;
    this.calOpenAt = dClosed + OPEN_FRAC * rng;
    this.closeAt = this.calCloseAt;
    this.openAt = this.calOpenAt;
    this.adaptive = adaptive;
    this._win = [];
    this.adaptedFrames = 0;
    this.thresholdSeries = [];   // [t, closeAt, openAt] in force per frame
    this.minIntertapS = minIntertap;
    this.emaAlpha = emaAlpha;
    this._ema = null;
    this._closed = false;
    this.tapTimes = [];
    this.series = [];          // [t, d] pairs
    this.lastTapT = -1e9;
    this.nearMiss = 0;
    this._dipMin = null;
    this._frames = 0;
    this._closedFrames = 0;
  }

  update(t, dRaw) {
    if (dRaw === null || dRaw === undefined) return false;
    this._ema = this._ema === null ? dRaw
      : this.emaAlpha * dRaw + (1 - this.emaAlpha) * this._ema;
    const d = this._ema;
    this.series.push([t, d]);
    this.thresholdSeries.push([t, this.closeAt, this.openAt]);
    this._frames += 1;
    let tapped = false;
    if (!this._closed && d < this.closeAt) {
      this._closed = true;
      this._dipMin = null;
      if (t - this.lastTapT >= this.minIntertapS) {
        this.tapTimes.push(t);
        this.lastTapT = t;
        tapped = true;
      }
    } else if (this._closed && d > this.openAt) {
      this._closed = false;
      this._dipMin = null;
    } else if (!this._closed) {
      if (d < this.openAt) this._dipMin = this._dipMin === null ? d : Math.min(this._dipMin, d);
      else if (this._dipMin !== null) { this.nearMiss += 1; this._dipMin = null; }
    }
    if (this._closed) this._closedFrames += 1;
    // Re-estimate AFTER deciding, so a frame never moves the threshold it is
    // being judged against.
    this._trackEnvelope(t, d);
    return tapped;
  }

  /** Slide the window and re-derive the thresholds from the excursion actually
   *  being performed. Holds the last good pair when the window is too short or
   *  too flat to trust — a hand held still must never collapse the range onto
   *  the noise floor and start scoring jitter as taps. */
  _trackEnvelope(t, d) {
    if (!this.adaptive) return;
    this._win.push([t, d]);
    const cut = t - ENVELOPE_S;
    let i = 0;
    while (i < this._win.length && this._win[i][0] < cut) i += 1;
    if (i) this._win.splice(0, i);
    if (this._win.length < ENVELOPE_MIN_FRAMES) return;
    const [lo, hi] = this._windowPercentiles();
    const rng = hi - lo;
    if (rng < ADAPT_MIN_RANGE_FRAC * this.calRange) return;
    this.closeAt = lo + CLOSE_FRAC * rng;
    this.openAt = lo + OPEN_FRAC * rng;
    this.adaptedFrames += 1;
  }

  /** 5th/95th of the window — the same estimator Calibrator uses, so the seed
   *  and the running estimate mean the same thing. */
  _windowPercentiles() {
    const s = this._win.map(([, d]) => d).sort((a, b) => a - b);
    const n = s.length;
    return [s[Math.floor(n * 0.05)], s[Math.min(n - 1, Math.floor(n * 0.95))]];
  }

  get smoothed() { return this._ema; }
  get closedDwellFrac() { return this._frames ? this._closedFrames / this._frames : 0; }
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

function intervalStats(mode, tapTimes) {
  if (tapTimes.length < 2) return null;
  const all = [];
  for (let i = 0; i < tapTimes.length - 1; i++) all.push((tapTimes[i + 1] - tapTimes[i]) * 1000);
  const cutoff = mode.paced ? maxItiMs(mode) : 3.0 * median(all);
  const iti = all.filter(v => v <= cutoff);
  if (iti.length < 2) return null;
  const mean = iti.reduce((a,b) => a+b, 0) / iti.length;
  const iiv = sd(iti);
  if (iiv === null || mean <= 0) return null;
  return {all, iti, cutoff, mean_iti_ms:mean, iiv_ms:iiv,
    cv_pct:iiv/mean*100, frequency_hz:1000/mean,
    rejected_frac:(all.length-iti.length)/all.length};
}

export function cvRelSe(cvFrac, n) { return n < 2 ? null : Math.sqrt((0.5 + cvFrac*cvFrac)/n); }
export function cvCi(cvPct, n) {
  const r = cvRelSe(cvPct/100, n); if (r === null) return null;
  const half = 1.959964 * cvPct * r; return [Math.max(0, cvPct-half), cvPct+half];
}
function confidence(n, cv, mean, width, fps, visible, rejected) {
  const r = cvRelSe(cv/100, n);
  const errorFactor = Math.max(0, Math.min(1, 1-(cv*r)/width));
  const precision = errorFactor * Math.sqrt(Math.min(1, n/30));
  const quant = fps && fps > 0 ? 100*(1000/fps)/Math.sqrt(6)/mean : null;
  const timing = quant === null || cv <= 0 ? 1 : Math.max(0, Math.min(1, 1-(quant/cv)**2));
  const tracking = Math.max(0, Math.min(1, (visible-0.70)/0.30));
  const continuity = Math.max(0, Math.min(1, 1-rejected/0.25));
  return 100*precision*timing*tracking*continuity;
}

/* ── gaps: port of core/tapping/gaps.py ─────────────────────────────────
 * One missed tap is forgiven -- only when it is the single long interval in
 * the run and a full closure sits in its middle. Pauses and partial closures
 * always count. See the Python module for the evidence behind the numbers. */
export const GAP_LONG = 1.5;
export const MISSED_LO = 1.7, MISSED_HI = 2.3;
export const MID_LO = 0.25, MID_HI = 0.75;
export const MIN_DIP = 0.25;
export const FULL_CLOSE = 0.25;
const NEIGHBOURS = 3;

function localMedian(iti, k) {
  const nb = iti.slice(Math.max(0, k - NEIGHBOURS), k).concat(iti.slice(k + 1, k + 1 + NEIGHBOURS));
  return nb.length ? median(nb) : median(iti);
}
function bisectLeft(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; } return lo; }
function bisectRight(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] <= x) lo = m + 1; else hi = m; } return lo; }

function makeTrace(series, taps) {
  const tr = { ts: series.map(p => p[0]), ds: series.map(p => p[1]), ok: false };
  tr.span = (a, b) => [bisectLeft(tr.ts, a), bisectRight(tr.ts, b)];
  const floors = [], amps = [], lags = [];
  for (let k = 0; k + 1 < taps.length; k++) {
    const [i0, i1] = tr.span(taps[k], taps[k + 1]);
    if (i1 - i0 < 3) continue;
    const seg = tr.ds.slice(i0, i1);
    amps.push(Math.max(...seg) - Math.min(...seg));
    const half = i0 + Math.max(1, Math.floor((i1 - i0) / 2));
    let m = i0;
    for (let q = i0; q < half; q++) if (tr.ds[q] < tr.ds[m]) m = q;
    floors.push(tr.ds[m]);
    lags.push(tr.ts[m] - taps[k]);
  }
  tr.ok = amps.length >= 3;
  if (tr.ok) { tr.amp = median(amps); tr.floor = median(floors); tr.lag = median(lags); }
  tr.midDip = (a, b) => {
    const [i0, i1] = tr.span(a, b);
    if (i1 - i0 < 5) return null;
    let best = null;
    for (let q = i0 + 1; q < i1 - 1; q++) {
      const frac = (tr.ts[q] - a) / (b - a);
      if (frac < MID_LO || frac > MID_HI) continue;
      if (tr.ds[q] <= tr.ds[q - 1] && tr.ds[q] < tr.ds[q + 1]) {
        const prom = Math.min(Math.max(...tr.ds.slice(i0, q + 1)), Math.max(...tr.ds.slice(q, i1))) - tr.ds[q];
        if (prom >= MIN_DIP * tr.amp && (best === null || tr.ds[q] < tr.ds[best])) best = q;
      }
    }
    return best;
  };
  return tr;
}

export function labelGaps(taps, series) {
  const pairs = [];
  for (let k = 0; k + 1 < taps.length; k++) pairs.push([taps[k], taps[k + 1]]);
  if (pairs.length < 4 || !series.length) return [];
  const tr = makeTrace(series, taps);
  if (!tr.ok) return [];
  const iti = pairs.map(([a, b]) => b - a);
  const out = [];
  pairs.forEach(([a, b], k) => {
    const ratio = iti[k] / localMedian(iti, k);
    if (ratio <= GAP_LONG) return;
    const q = tr.midDip(a, b);
    let kind;
    if (q === null) kind = "pause";
    else if (tr.ds[q] > tr.floor + FULL_CLOSE * tr.amp) kind = "partial_closure";
    else if (ratio >= MISSED_LO && ratio <= MISSED_HI) kind = "missed_tap";
    else kind = "pause";
    out.push([a, b, kind]);
  });
  return out;
}

export function restoreMissedTap(taps, series) {
  const labels = labelGaps(taps, series);
  if (labels.length !== 1 || labels[0][2] !== "missed_tap") return null;
  const [a, b] = labels[0];
  const tr = makeTrace(series, taps);
  const t = tr.ts[tr.midDip(a, b)] - tr.lag;
  return a < t && t < b ? t : null;
}

const BANDS = ["success", "warning", "danger"];

function scoredTaps(mode, tapTimes) {
  return tapTimes.length - mode.trim_taps >= mode.min_taps ? tapTimes.slice(mode.trim_taps) : tapTimes;
}

/** Port of compute_metrics(): score as recorded, then forgive one missed tap
 *  if the verdict moves one band at most. */
export function computeMetrics(mode, tapTimes, series, tStart, tEnd,
                               beatTimes = null, handVisibleRatio = 1.0,
                               cameraFps = null, nearMiss = 0) {
  const args = [beatTimes, handVisibleRatio, cameraFps, nearMiss];
  const out = scoreRun(mode, tapTimes, series, tStart, tEnd, ...args);
  const scored = scoredTaps(mode, tapTimes);
  const labels = out.scoreable ? labelGaps(scored, series) : [];
  out.missed_tap_forgiven = 0;
  out.cv_pct_unrepaired = out.cv_pct;
  out.interruptions = out.scoreable ? labels.filter(l => l[2] !== "missed_tap").length : null;
  if (!out.scoreable) return out;
  const tNew = restoreMissedTap(scored, series);
  if (tNew === null) return out;
  const fixed = scoreRun(mode, [...tapTimes, tNew].sort((x, y) => x - y), series, tStart, tEnd, ...args);
  if (!fixed.scoreable || BANDS.indexOf(out.status) - BANDS.indexOf(fixed.status) > 1) return out;
  fixed.missed_tap_forgiven = 1;
  fixed.cv_pct_unrepaired = out.cv_pct;
  fixed.interruptions = out.interruptions;
  return fixed;
}

/** Port of compute_metrics(). Same keys, same order of decisions, same
 *  early-return reasons — those strings are shown to the participant. */
function scoreRun(mode, tapTimes, series, tStart, tEnd,
                  beatTimes = null, handVisibleRatio = 1.0,
                  cameraFps = null, nearMiss = 0) {
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
    n_intervals: null, cv_ci_low_pct: null, cv_ci_high_pct: null,
    confidence_pct: null, band_edge: null, taps_w10: null,
    frequency_hz_w10: null, cv_pct_w10: null, near_miss_taps: nearMiss,
    opening_shrink_ratio: null,
  };

  if (tapTimes.length < mode.min_taps) {
    out.reason = handVisibleRatio < 0.8
      ? "Your hand was out of view for part of the test - keep it in the frame and try again."
      : nearMiss >= Math.max(2, tapTimes.length)
        ? `${nearMiss} closures were too shallow to count as taps - open the hand fully between taps.`
        : `Only ${tapTimes.length} taps detected - at least ${mode.min_taps} are needed for a reliable score.`;
    return out;
  }

  let taps = tapTimes;
  if (taps.length - mode.trim_taps >= mode.min_taps) taps = taps.slice(mode.trim_taps);

  const stats = intervalStats(mode, taps);
  const iti = stats ? stats.iti : [];
  if (iti.length < mode.min_taps - 1) {
    out.reason = "Tapping was too irregular to score - large pauses interrupted the rhythm. Try to keep a continuous motion.";
    return out;
  }

  const meanIti = stats.mean_iti_ms, cv = stats.cv_pct, cutoff = stats.cutoff;
  out.mean_iti_ms = meanIti; out.iiv_ms = stats.iiv_ms;
  out.cv_pct = cv; out.frequency_hz = stats.frequency_hz; out.n_intervals = iti.length;

  // Floor for having a rhythm at all — mirrors compute_metrics().
  if (mode.min_effort_hz && stats.frequency_hz < mode.min_effort_hz) {
    out.reason = `Tapping was too slow to score a rhythm ` +
      `(${stats.frequency_hz.toFixed(1)} taps/s - long pauses between taps ` +
      `leave no steady rhythm to measure). Try to keep a continuous tapping motion.`;
    return out;
  }

  out.confidence_pct = confidence(iti.length, cv, meanIti,
    mode.cv_monitor-mode.cv_typical, cameraFps, handVisibleRatio, stats.rejected_frac);
  const ci = cvCi(cv, iti.length); out.cv_ci_low_pct=ci[0]; out.cv_ci_high_pct=ci[1];
  out.band_edge = (ci[0] < mode.cv_typical && ci[1] > mode.cv_typical) ||
                  (ci[0] < mode.cv_monitor && ci[1] > mode.cv_monitor) ? 1 : 0;
  const tapsW10 = tapTimes.filter(t => t <= tStart + mode.compat_window_s);
  out.taps_w10 = tapsW10.length;
  let compatTaps = tapsW10;
  if (compatTaps.length-mode.trim_taps >= mode.min_taps) compatTaps=compatTaps.slice(mode.trim_taps);
  const compat = intervalStats(mode, compatTaps);
  if (compat) { out.frequency_hz_w10=compat.frequency_hz; out.cv_pct_w10=compat.cv_pct; }

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
  // Shrinking openings: last quarter over first. Information only.
  if (amps.length >= 8) {
    const k = Math.max(3, Math.floor(amps.length / 4));
    const first = amps.slice(0, k).reduce((a, b) => a + b, 0) / k;
    if (first > 0) out.opening_shrink_ratio = (amps.slice(-k).reduce((a, b) => a + b, 0) / k) / first;
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
