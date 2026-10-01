/* Parity harness — JS port vs the normative Python engine.
   WEB_PLATFORM_PLAN.md §3, "the parity discipline".

     node participant/tests/parity.mjs

   Replays the golden vectors in vectors.json (dumped by make_vectors.py)
   through participant/engine.js and asserts agreement. A drift here means the
   same participant would score differently on the phone than on the desktop,
   which silently invalidates every longitudinal comparison — so this is a
   hard failure, not a warning.

   Tolerance is 1e-9 relative: the two engines do the same float64 arithmetic
   in the same order, so anything larger is a real divergence, not rounding. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  CLEAR_HOLD_S, Calibrator, EDGE_CLIP, EDGE_NEAR, FramingMonitor, MODES,
  PRE_ROLL_S, TapDetector, band, computeMetrics, hint, makeLandmarkFilters,
  maxItiMs, minIntertapS, smoothLandmarks, thumbIndexDistance,
} from "../engine.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const V = JSON.parse(readFileSync(join(HERE, "vectors.json"), "utf-8"));
const TOL = 1e-9;

let failures = 0;
let checks = 0;

function close(a, b) {
  if (a === null && b === null) return true;
  if (a === null || b === null) return false;
  if (typeof a === "boolean" || typeof b === "boolean") return a === b;
  if (typeof a === "string" || typeof b === "string") return a === b;
  const scale = Math.max(1, Math.abs(a), Math.abs(b));
  return Math.abs(a - b) <= TOL * scale;
}

function check(label, got, want) {
  checks += 1;
  if (close(got, want)) return;
  failures += 1;
  console.log(`  FAIL  ${label}\n          python=${want}\n          js    =${got}`);
}

function checkArray(label, got, want) {
  checks += 1;
  if (got.length !== want.length) {
    failures += 1;
    console.log(`  FAIL  ${label} length  python=${want.length} js=${got.length}`);
    return;
  }
  for (let i = 0; i < want.length; i++) {
    if (!close(got[i], want[i])) {
      failures += 1;
      console.log(`  FAIL  ${label}[${i}]  python=${want[i]} js=${got[i]}`);
      return;
    }
  }
}

/* ── mode constants ────────────────────────────────────────────────────── */
// A mode Python has and JS does not is "not ported yet", not "drifted" — the
// prototype ships big_and_fast only. It is still printed, loudly, so the gap
// cannot quietly become permanent.
const pending = [];
for (const [key, py] of Object.entries(V.modes)) {
  const js = MODES[key];
  if (!js) { pending.push(key); continue; }
  for (const field of ["paced", "duration_s", "expected_rate_hz", "min_taps",
                       "trim_taps", "cv_typical", "cv_monitor",
                       "max_rate_hz", "min_effort_hz"]) {
    check(`mode.${key}.${field}`, js[field], py[field]);
  }
  check(`mode.${key}.min_intertap_s`, minIntertapS(js), py.min_intertap_s);
  check(`mode.${key}.max_iti_ms`, maxItiMs(js), py.max_iti_ms);
}

/* ── thumb_index_distance ──────────────────────────────────────────────── */
V.landmark_cases.forEach((lc, i) => {
  check(`thumbIndexDistance[${i}]`, thumbIndexDistance(lc.landmarks), lc.expect);
});

/* ── per-case: calibration, detection, metrics ─────────────────────────── */
for (const c of V.cases) {
  const mode = MODES[c.mode];

  const cal = new Calibrator();
  for (const [t, d] of c.samples.slice(0, 90)) cal.update(t, d);
  const [dClosed, dOpen] = cal.result();
  check(`${c.name}/cal.d_closed`, dClosed, c.calibration.d_closed);
  check(`${c.name}/cal.d_open`, dOpen, c.calibration.d_open);
  check(`${c.name}/cal.cycles`, cal.cycles, c.calibration.cycles);
  check(`${c.name}/cal.done`, cal.done, c.calibration.done);
  check(`${c.name}/cal.progress`, cal.progress, c.calibration.progress);
  check(`${c.name}/cal.range_seen`, cal.rangeSeen, c.calibration.range_seen);

  const det = new TapDetector(minIntertapS(mode), 0.4, dClosed, dOpen);
  const flagged = [];
  for (const [t, d] of c.samples) if (det.update(t, d)) flagged.push(t);
  check(`${c.name}/det.close_at`, det.closeAt, c.detector.close_at);
  check(`${c.name}/det.open_at`, det.openAt, c.detector.open_at);
  check(`${c.name}/det.smoothed`, det.smoothed, c.detector.smoothed);
  checkArray(`${c.name}/det.tap_times`, flagged, c.detector.tap_times);

  const kw = c.kwargs || {};
  const m = computeMetrics(mode, det.tapTimes, det.series,
                           c.samples[0][0], c.samples[c.samples.length - 1][0],
                           null, kw.hand_visible_ratio ?? 1.0, kw.camera_fps ?? null,
                           kw.near_miss ?? 0, kw.blackouts ?? null);
  for (const key of Object.keys(c.metrics)) {
    check(`${c.name}/metrics.${key}`, m[key], c.metrics[key]);
  }

  // Guard on status, not cv_pct: a run can have a CV% and still be refused a
  // band (the min_effort_hz floor computes the stats, then declines to score).
  if (c.metrics.status !== null) {
    const [status, label] = band(c.metrics.cv_pct, mode);
    check(`${c.name}/band.status`, status, c.metrics.status);
    check(`${c.name}/band.label`, label, c.metrics.label);
  }
}

/* ── One-Euro smoothing (hand_utils.py) ────────────────────────────────── */
(V.one_euro_cases || []).forEach((oc, i) => {
  const [fx, fy] = makeLandmarkFilters();
  oc.frames.forEach((f, k) => {
    const sm = smoothLandmarks(f.raw, fx, fy, f.t);
    checkArray(`oneEuro[${i}][${k}]`, sm.flat(), f.smoothed.flat());
    check(`oneEuro[${i}][${k}].d`, thumbIndexDistance(sm), f.d);
  });
});

/* ── framing (framing.py) ──────────────────────────────────────────────── */
if (V.framing_consts) {
  check("framing.EDGE_CLIP", EDGE_CLIP, V.framing_consts.EDGE_CLIP);
  check("framing.EDGE_NEAR", EDGE_NEAR, V.framing_consts.EDGE_NEAR);
  check("framing.CLEAR_HOLD_S", CLEAR_HOLD_S, V.framing_consts.CLEAR_HOLD_S);
  check("framing.PRE_ROLL_S", PRE_ROLL_S, V.framing_consts.PRE_ROLL_S);
}
(V.framing_cases || []).forEach((fc, i) => {
  const mon = new FramingMonitor();
  fc.frames.forEach((f, k) => {
    check(`framing[${i}][${k}].level`, mon.update(f.points, f.t), f.level);
    check(`framing[${i}][${k}].edges`, mon.edges.join(","), f.edges.join(","));
    check(`framing[${i}][${k}].untrusted`, mon.untrusted, f.untrusted);
  });
  checkArray(`framing[${i}].blackouts`, mon.finish().flat(), fc.blackouts.flat());
  check(`framing[${i}].clipped_pct`, mon.clippedPct, fc.clipped_pct);
});
(V.hint_cases || []).forEach((hc) => {
  check(`hint(${hc.edges},${hc.tracing})`, hint(hc.edges, hc.tracing), hc.expect);
});

if (pending.length) {
  console.log(`\n  PENDING  mode(s) not ported to JS yet: ${pending.join(", ")}` +
              "\n           (deliberate for the prototype; see REMOTE_SESSION_PLAN.md status)");
}
console.log(`\n${checks - failures}/${checks} parity checks passed` +
            (failures ? ` — ${failures} FAILED` : ""));
process.exit(failures ? 1 : 0);
