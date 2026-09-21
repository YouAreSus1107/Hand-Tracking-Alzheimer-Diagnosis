/* ── Developer page: sensor-glove toolchain + live scope ──────────────
   Classic script (loaded after app.js) so it shares that file's top-level
   `I` icon library, `toast()` and `reducedMotion` bindings.

   Data path:  Arduino --USB--> launcher.py GloveReader --> /api/glove/samples
               --> ring buffers here --> canvas scope + per-channel tiles.

   Polling runs ONLY while this page is on screen; app.js's showPage() calls
   startDev()/stopDev(). */

/* Categorical series palette — validated with the dataviz skill's checker
   against this page's surface (#1C2430, dark): lightness band, chroma floor,
   CVD separation, normal-vision floor and contrast all pass. Slots are
   assigned to channels in FIXED ORDER and never cycled; past slot 8 the
   per-channel tiles below act as small multiples instead of new hues.
   Status colors (--success/--warning/--danger) are reserved and never used
   as a series color. */
const DEV_SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500",
                    "#d55181", "#008300", "#9085e9", "#e66767"];
const DEV_MAX_SERIES = DEV_SERIES.length;

const DEV_CAP = 1500;            // samples retained per channel (~15 s at 100 Hz)
const DEV_CONSOLE_CAP = 200;
const DEV_POLL_MS = 100;
const DEV_ENV_MS = 4000;

const DEV_IMU_MS = 500;          // derived motion readout; runs a small DFT

/* Full-scale for the per-axis bars and the motion plots, in physical units.
   Chosen for a HAND, not for the sensor's range: a glove sees roughly +/-2 g
   and a few hundred deg/s, and scaling to the chip's +/-2000 dps would leave
   every real gesture an invisible sliver. Values past full scale clamp the
   bar; the number beside it stays authoritative. */
/* Canvas text needs its own stack: JetBrains Mono has no CJK glyphs, and a
   canvas silently draws tofu rather than falling back per-glyph. */
const DEV_FONT = "11px 'JetBrains Mono','Noto Sans TC','Microsoft JhengHei',monospace";

const DEV_ACCEL_FS = 2;          // g
const DEV_GYRO_FS = 250;         // deg/s

const dev = {
  built: false, fastTimer: null, envTimer: null, imuTimer: null, raf: null,
  env: null, status: null, imu: null,
  channels: [], series: [], span: [],   // per channel: values[], {min,max}
  bendSpan: [],                        // flex only: outlier-resistant {min,max}
  lastSeq: -1, paused: false,
  window_s: 5, yAuto: false, unit: "force", smooth: false,
  view: "stacked",     // "stacked" = one lane per channel | "overlaid" = shared axis
  console: [], autoscroll: true,
  selected: new Set(),
  port: null,          // port shown in the select, survives re-renders
  portPinned: false,   // true only once the user has picked one by hand
  connSig: null,       // last rendered connection-row signature
};

/* ── helpers ─────────────────────────────────────────────────────── */

function devOhmText(v){
  if(v === null || v === undefined) return t("open");
  if(v >= 1e6) return (v/1e6).toFixed(2) + " MΩ";
  if(v >= 1e3) return (v/1e3).toFixed(1) + " kΩ";
  return v + " Ω";
}
// Mirrors core/glove/protocol.py — integer math, so the page and the board's
// own #DIAG output can never disagree.
function devMv(adc, b){
  const ref = b ? b.adc_ref_mv : 3300, bits = b ? b.adc_bits : 10;
  return Math.floor((adc * ref) / ((1 << bits) - 1));
}
// rFixed is passed in rather than read off the banner's global, because each
// channel has its own low-side resistor (see devRFixed). Falls back to the
// global when a caller has no channel in hand.
function devOhm(adc, b, rFixed){
  const mv = devMv(adc, b);
  const vdiv = b ? b.vdiv_mv : 3300;
  const rf = (rFixed && rFixed > 0) ? rFixed : (b ? b.r_fixed : 10000);
  if(mv <= 0) return null;
  if(mv >= vdiv) return 0;
  return Math.floor((rf * (vdiv - mv)) / mv);
}

/* ── force estimation ─────────────────────────────────────────────────
   Interpolates the curve the SERVER sends (dev.status.force_model), which
   comes from core/glove/force.py. The anchor points are deliberately not
   duplicated here — one definition, in Python. */

function devForceModel(){
  return (dev.status && dev.status.force_model) || null;
}
// Log-log piecewise interpolation, mirroring force.force_newtons().
function devForce(ohm){
  const m = devForceModel();
  if(!m || ohm === null || ohm === undefined) return null;
  const p = m.points;                       // [[newtons, ohms], ...] asc force
  if(ohm <= 0) return ohm === 0 ? p[p.length-1][0] : null;
  const last = p.length - 2;
  let seg;
  if(ohm >= p[0][1]) seg = 0;
  else if(ohm <= p[p.length-1][1]) seg = last;
  else { seg = last;
    for(let i=0;i<=last;i++){ if(p[i+1][1] <= ohm && ohm <= p[i][1]){ seg = i; break; } } }
  const [f0,r0] = p[seg], [f1,r1] = p[seg+1];
  if(r1 === r0) return f0;
  const t = (Math.log(ohm) - Math.log(r0)) / (Math.log(r1) - Math.log(r0));
  return Math.exp(Math.log(f0) + t * (Math.log(f1) - Math.log(f0)));
}
function devForceRange(n){
  const m = devForceModel();
  if(n === null || n === undefined) return "open";
  if(!m) return "rated";
  if(n < m.rated_min_n) return "below";
  if(n > m.rated_max_n) return "above";
  return "rated";
}
function devForceText(n){
  if(n === null || n === undefined) return "—";
  return (n < 10 ? n.toFixed(2) : n.toFixed(1)) + " N";
}
function devGramsText(n){
  if(n === null || n === undefined) return "";
  const g = n / 9.80665 * 1000;
  return g >= 1000 ? (g/1000).toFixed(2) + " kgf" : g.toFixed(0) + " gf";
}
// Honest badge — never present an out-of-spec reading as a measurement.
function devForceBadge(range){
  const m = devForceModel();
  const tol = m ? m.tolerance_pct : 6;
  const map = {
    open:   ["dev-badge-dim",  t("no contact")],
    below:  ["dev-badge-dim",  t("below {n} N actuation", {n: m ? m.rated_min_n : 0.2})],
    rated:  ["dev-badge-ok",   t("datasheet ±{tol}%", {tol})],
    above:  ["dev-badge-warn", t("beyond rated {n} N — upper bound only", {n: m ? m.rated_max_n : 20})],
  };
  const [cls, text] = map[range] || map.rated;
  return `<span class="dev-badge ${cls}">${text}</span>`;
}
/* ── bend estimation ──────────────────────────────────────────────────
   Same contract as force above: the span comes from the SERVER
   (dev.status.flex_model / core/glove/flex.py), never a copy kept here.
   Deliberately thinner than the force path — there is no published curve for
   a bend sensor, so this is a position within a recorded span, not an angle. */

function devFlexModel(){
  return (dev.status && dev.status.flex_model) || null;
}

/* Which span to measure a bend against.

   The server's default span is a placeholder (§5c) — real flex strips vary
   enough part-to-part that a reading will often sit entirely outside it, which
   clamps the trace flat at 0% or 100% and looks like a dead sensor.

   So until a calibration exists, prefer the span this channel has ACTUALLY
   been seen to cover. That is not a fudge: §5c's whole position is that bend
   is a position within a recorded range, and the live min/max is a recorded
   range. It is labelled "observed" rather than "calibrated" so nobody mistakes
   it for a measurement, and it widens as the finger moves further.

   Direction matters. Both sensors sit on the high side of their divider, so
   rising resistance pulls the count down. Bending a flex strip raises its
   resistance, so the HIGHEST count is flattest and the LOWEST is most bent. */
function devFlexSpan(i){
  const m = devFlexModel();
  if(m && m.calibrated && m.usable){
    return {flat: m.flat_ohm, bent: m.bent_ohm, basis: "calibrated"};
  }
  // Deliberately NOT m.min_span_ratio: see DEV_OBSERVED_MIN_RATIO.
  const ratio = DEV_OBSERVED_MIN_RATIO;
  const b = dev.status && dev.status.banner;
  const s = dev.bendSpan[i];
  if(s && s.min !== null && s.max !== null){
    const rf = devRFixed(i);
    const flat = devOhm(s.max, b, rf);      // highest count  -> lowest R
    const bent = devOhm(s.min, b, rf);      // lowest count   -> highest R
    // Same "is this travel or noise?" guard flex.py applies: dividing by a
    // span narrower than this turns jitter into a full-scale swing.
    if(flat !== null && bent !== null && flat > 0 && bent / flat >= ratio){
      return {flat, bent, basis: "observed"};
    }
  }
  if(m && m.usable) return {flat: m.flat_ohm, bent: m.bent_ohm, basis: "provisional"};
  return null;
}

// Linear in resistance, mirroring flex.bend_fraction(). Clamped at both ends:
// past the span the sensor has left the range that was recorded, and
// extrapolating would invent travel nobody measured.
function devBend(ohm, span){
  if(!span || ohm === null || ohm === undefined || ohm <= 0) return null;
  const {flat, bent} = span;
  if(bent === flat) return null;
  return Math.max(0, Math.min(1, (ohm - flat) / (bent - flat))) * 100;
}
function devBendRange(ohm, span){
  if(!span || ohm === null || ohm === undefined || ohm <= 0) return "open";
  const lo = Math.min(span.flat, span.bent), hi = Math.max(span.flat, span.bent);
  const flatIsLow = span.flat <= span.bent;
  if(ohm < lo) return flatIsLow ? "below" : "above";
  if(ohm > hi) return flatIsLow ? "above" : "below";
  return "in";
}
function devBendText(pct){
  if(pct === null || pct === undefined) return "—";
  return t("{pct}% bend", {pct: pct.toFixed(0)});
}
// An uncalibrated span must never look like a measurement, and the badge has
// to say WHICH span produced the number.
function devBendBadge(range, span){
  const basis = span ? span.basis : null;
  if(range === "open" || !basis){
    return `<span class="dev-badge dev-badge-dim">${t("no signal")}</span>`;
  }
  if(basis === "provisional"){
    return `<span class="dev-badge dev-badge-warn">${t("provisional span — bend the sensor to set its range")}</span>`;
  }
  if(range === "below" || range === "above"){
    // On an observed span this cannot persist: the span grows to include the
    // new extreme on the next frame. On a calibrated one it is a real warning.
    return `<span class="dev-badge dev-badge-warn">${range === "below"
      ? t("flatter than recorded — re-record span")
      : t("bent than recorded — re-record span")}</span>`;
  }
  return basis === "calibrated"
    ? `<span class="dev-badge dev-badge-ok">${t("calibrated span")}</span>`
    : `<span class="dev-badge dev-badge-warn">${t("observed span — not calibrated")}</span>`;
}

/* Which channels get which curve. The kind comes from the firmware's banner
   (chan=name:kind:rFixed); the f./p. name check is the fallback for boards
   still running firmware that predates that field. Getting this wrong is the
   bug this whole branch exists to prevent: the FSR402 force curve applied to
   a bending finger prints a confident newton figure that means nothing. */
function devKind(i){
  const b = dev.status && dev.status.banner;
  if(b && b.chan && b.chan[i] && b.chan[i].kind) return b.chan[i].kind;
  const n = dev.channels[i] || "";
  if(n[0] === "f") return "flex";
  if(n[0] === "p") return "fsr";
  return "unknown";
}
// Per-channel resistor, for the same reason: the FSR and the flex strip sit on
// different low-side resistors and sharing one mis-scales whichever lost.
function devRFixed(i){
  const b = dev.status && dev.status.banner;
  if(b && b.chan && b.chan[i] && b.chan[i].r_fixed > 0) return b.chan[i].r_fixed;
  return b ? b.r_fixed : 10000;
}

/* -- onboard IMU ----------------------------------------------------
   Motion channels are NOT divider sensors. They carry no low-side resistor,
   so every ohm/force/bend helper above is meaningless for them - applying one
   would print a confident resistance for an acceleration, the same class of
   bug the fsr/flex split exists to prevent. They convert with one scale from
   the banner and nothing else. */
function devIsImu(kind){ return kind === "accel" || kind === "gyro"; }
function devImuScale(){
  const b = dev.status && dev.status.banner;
  return (b && b.imu_scale > 0) ? b.imu_scale : 1000;
}
// Raw milli-units -> g or deg/s. Never hardcode the divisor: the banner owns it.
function devImuVal(raw){
  if(raw === null || raw === undefined) return null;
  return raw / devImuScale();
}
function devImuUnit(kind){ return kind === "gyro" ? " \u00B0/s" : " g"; }
function devImuFS(kind){ return kind === "gyro" ? DEV_GYRO_FS : DEV_ACCEL_FS; }
function devImuText(v, kind){
  if(v === null || v === undefined) return "\u2014";
  return (kind === "gyro" ? v.toFixed(0) : v.toFixed(2)) + devImuUnit(kind);
}

/* Median-of-N, for the DISPLAY ONLY.

   At the top of the FSR's range the force curve is steep enough that one ADC
   count is worth about a newton, so ordinary count noise reads as large force
   swings. A median rejects those single-sample spikes without smearing real
   edges the way a moving average would.

   This must never touch recorded data. Jitter is signal — tremor and
   micro-instability are precisely what this suite measures (plan §2, and the
   same rule spiral_test.py enforces on the raw fingertip). Recording happens
   server-side from raw frames and does not pass through here. */
const DEV_SMOOTH_N = 5;

/* ── the bend span's own accumulator ───────────────────────────────────
   dev.span is the RAW min/max, and it has to stay raw: it feeds the peak
   readout, and a peak must never be quietly lowered by a display filter.

   But the same raw min/max was also serving as the denominator for bend %,
   and those two jobs want opposite things. A denominator built from raw
   extremes is destroyed by a single sample:

     * Measured 2026-09-20 on a 150 s recording, an untouched sensor's own
       noise gave a raw min/max ratio of 1.377 — above MIN_SPAN_RATIO — so
       pure jitter was promoted to an "observed span" and then mapped across
       the full 0-100%. That is the trace filling the plot while nothing is
       being bent.
     * Worse, the span only ever widens. One touch transient took it to
       241..4095 counts, and a genuine 11-36 kΩ bend then occupied 3.3% of
       it. That is why a full bend was reading as a move from 1% to 26%.

   So the bend denominator gets its own accumulator, fed a MEDIAN and with
   the ADC rails excluded. This is not a display filter — it decides what the
   number means, which is exactly why it must be robust. */
const DEV_BEND_SPAN_N = 9;       // median width feeding the bend span
const DEV_RAIL_MARGIN = 8;       // counts from either rail = saturation, not travel
/* An OBSERVED span is inferred from live data, so it has to clear a higher
   bar than a span somebody deliberately recorded. flex.py's MIN_SPAN_RATIO
   (1.2) is the latter; at these resistances it is inside the noise. */
const DEV_OBSERVED_MIN_RATIO = 1.5;
function devMedian(values){
  const v = values.filter(x => x !== null && x !== undefined);
  if(!v.length) return null;
  const s = v.slice().sort((a,b)=>a-b);
  return s[Math.floor(s.length/2)];
}
/* Widen a flex channel's bend span, from a median and never from a rail.
   Called per sample; cheap because it only medians the tail of the buffer. */
function devTrackBendSpan(c, buf){
  if(buf.length < DEV_BEND_SPAN_N) return;
  const v = devMedian(buf.slice(-DEV_BEND_SPAN_N));
  if(v === null) return;
  const b = dev.status && dev.status.banner;
  const full = (1 << ((b && b.adc_bits) || 10)) - 1;
  // A reading pinned at either rail is saturation - an open sensor, a short,
  // or a transient - and admitting it would define the span by the fault.
  if(v <= DEV_RAIL_MARGIN || v >= full - DEV_RAIL_MARGIN) return;
  const s = dev.bendSpan[c];
  if(s.min === null || v < s.min) s.min = v;
  if(s.max === null || v > s.max) s.max = v;
}

function devSmoothSeries(data){
  if(!dev.smooth || data.length < DEV_SMOOTH_N) return data;
  const out = new Array(data.length);
  for(let i=0;i<data.length;i++){
    if(data[i] === null){ out[i] = null; continue; }   // keep breaks in the line
    const lo = Math.max(0, i - (DEV_SMOOTH_N - 1));
    out[i] = devMedian(data.slice(lo, i + 1));
  }
  return out;
}

function devPill(state, label, value){
  // Style guide 2.4: never encode meaning in colour alone — icon + word always.
  const map = {ok:["st-yes", I.check], bad:["st-no", I.x], warn:["st-partial", I.minus]};
  const [cls, icon] = map[state] || map.warn;
  return `<span class="dev-pill ${cls}">${icon}<b>${label}</b><span>${value}</span></span>`;
}
function devBtn(id, label, icon, cls){
  return `<button class="btn ${cls || "btn-ghost"}" data-dev="${id}">${icon ? icon+" " : ""}${label}</button>`;
}

async function devPost(path, body){
  try{
    const r = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"},
                                body: JSON.stringify(body || {})});
    const d = await r.json();
    // Server text is English; tMsg maps the known strings (i18n.zh.js).
    toast(tMsg(d.message) || t(d.ok ? "Done" : "Failed"), d.ok ? "ok" : "fail");
    return d;
  }catch(e){ toast(t("Request failed"), "fail"); return {ok:false}; }
}

/* ── static build ────────────────────────────────────────────────── */

/* Markup only — safe to run again when the language changes. The delegated
   listeners are bound once, separately, or a switch would stack them up. */
function devBuildStatic(){
  const icon = document.getElementById("dev-icon");
  if(icon) icon.innerHTML = I.code;

  document.getElementById("dev-tasks").innerHTML =
    devBtn("setup", t("Run Setup"), I.play, "btn-primary") +
    devBtn("install_pyserial", t("Install pyserial")) +
    devBtn("install_imu_bmi270", t("IMU lib: Rev2 (BMI270)")) +
    devBtn("install_imu_lsm9ds1", t("IMU lib: original (LSM9DS1)")) +
    devBtn("compile", t("Compile Firmware")) +
    devBtn("upload", t("Upload Firmware")) +
    devBtn("tests", t("Run Glove Tests"));

  document.getElementById("dev-cmds").innerHTML =
    devBtn("cmd:?", t("Re-read Banner")) +
    devBtn("cmd:S", t("Start Stream")) +
    devBtn("cmd:X", t("Stop Stream")) +
    devBtn("cmd:Z", t("Zero &amp; Reset Span")) +
    devBtn("cmd:D", t("Toggle Diagnostics")) +
    devBtn("rec", t(dev.status && dev.status.recording ? "Stop Recording" : "Start Recording"),
           null, "btn-primary");

  // One unit at a time, never two y-scales on one plot.
  document.getElementById("dev-scope-tools").innerHTML =
    `<label class="dev-sel">${t("View")}
       <select data-dev="view"><option value="stacked" selected>${t("Stacked")}</option>
       <option value="overlaid">${t("Overlaid")}</option></select></label>
     <label class="dev-sel">${t("Unit")}
       <select data-dev="unit"><option value="force" selected>${t("Force (N)")}</option>
       <option value="bend" data-kind="flex">${t("Bend (%)")}</option>
       <option value="accel" data-kind="accel">${t("Accel (g)")}</option>
       <option value="gyro" data-kind="gyro">${t("Gyro (°/s)")}</option>
       <option value="adc">${t("Raw ADC")}</option><option value="ohm">${t("Resistance (Ω)")}</option>
       <option value="us">${t("Conductance (µS)")}</option></select></label>
     <label class="dev-sel">${t("Window")}
       <select data-dev="window"><option value="2">${t("{n} s", {n:2})}</option>
       <option value="5" selected>${t("{n} s", {n:5})}</option><option value="10">${t("{n} s", {n:10})}</option></select></label>
     <label class="dev-sel">${t("Y axis")}
       <select data-dev="yaxis"><option value="fixed" selected>${t("Fixed")}</option>
       <option value="auto">${t("Auto")}</option></select></label>
     <label class="dev-check" title="${t("Median of {n} samples. Display only — recordings stay raw.", {n:DEV_SMOOTH_N})}">
       <input type="checkbox" data-dev="smooth"> ${t("Smooth (display only)")}</label>` +
    devBtn("pause", t(dev.paused ? "Resume" : "Pause"), null, dev.paused ? "btn-primary" : null);

  document.getElementById("dev-console-tools").innerHTML =
    `<label class="dev-check"><input type="checkbox" data-dev="autoscroll" checked> ${t("Auto-scroll")}</label>` +
    devBtn("clearconsole", t("Clear"));

  devRestoreControls();
}

/* The rebuilt <select>s come back on their defaults; put the user's choices
   back so a language switch never silently changes what is being plotted. */
function devRestoreControls(){
  const set = (k, v) => { const el = document.querySelector(`[data-dev="${k}"]`); if(el) el.value = v; };
  set("view", dev.view);
  set("unit", dev.unit);
  set("window", String(dev.window_s));
  set("yaxis", dev.yAuto ? "auto" : "fixed");
  const sm = document.querySelector('[data-dev="smooth"]');
  if(sm) sm.checked = dev.smooth;
  const as = document.querySelector('[data-dev="autoscroll"]');
  if(as) as.checked = dev.autoscroll;
  devSyncUnitOptions();
}

function devBuild(){
  if(dev.built) return;
  devBuildStatic();

  // One delegated listener for every control on the page.
  document.getElementById("page-dev").addEventListener("click", devClick);
  document.getElementById("page-dev").addEventListener("change", devChange);

  dev.built = true;
}

/* ── event handling ──────────────────────────────────────────────── */

async function devClick(e){
  const btn = e.target.closest("[data-dev]");
  if(!btn || btn.tagName === "SELECT" || btn.tagName === "INPUT") return;
  const id = btn.dataset.dev;

  if(id === "pause"){
    dev.paused = !dev.paused;
    btn.textContent = t(dev.paused ? "Resume" : "Pause");
    btn.classList.toggle("btn-primary", dev.paused);
    return;
  }
  if(id === "clearconsole"){ dev.console = []; devRenderConsole(); return; }
  if(id === "refreshports"){ await devLoadEnv(); toast(t("Ports refreshed"), "info"); return; }

  if(id === "connect"){
    const sel = document.querySelector('[data-dev="port"]');
    const d = await devPost("/api/glove/connect", {port: sel ? sel.value : ""});
    if(d.ok) devResetBuffers();
    await devPollStatus();
    return;
  }
  if(id === "disconnect"){ await devPost("/api/glove/disconnect"); await devPollStatus(); return; }

  if(id === "rec"){
    const on = !(dev.status && dev.status.recording);
    await devPost("/api/glove/record", {on});
    await devPollStatus();
    return;
  }
  if(id.startsWith("cmd:")){
    const cmd = id.slice(4);
    await devPost("/api/glove/command", {cmd});
    // The board restarts its counters on Z, so the on-screen spans must too.
    if(cmd === "Z") devResetBuffers();
    return;
  }

  // Remaining ids are dev tasks; upload needs the chosen port.
  const sel = document.querySelector('[data-dev="port"]');
  await devPost("/api/dev/run", {task:id, port: sel ? sel.value : null});
  if(id === "upload"){ devResetBuffers(); setTimeout(devPollStatus, 500); }
  setTimeout(devLoadEnv, 1500);
}

function devChange(e){
  const el = e.target.closest("[data-dev]");
  if(!el) return;
  if(el.dataset.dev === "window") dev.window_s = +el.value;
  if(el.dataset.dev === "yaxis") dev.yAuto = el.value === "auto";
  if(el.dataset.dev === "unit") dev.unit = el.value;
  if(el.dataset.dev === "view") dev.view = el.value;
  if(el.dataset.dev === "smooth") dev.smooth = el.checked;
  if(el.dataset.dev === "autoscroll") dev.autoscroll = el.checked;
  if(el.dataset.dev === "port"){ dev.port = el.value; dev.portPinned = true; }
  if(el.dataset.dev === "chan"){
    const i = +el.dataset.i;
    if(el.checked){
      if(dev.selected.size >= DEV_MAX_SERIES){
        el.checked = false;
        toast(t("Scope shows at most {n} channels — the tiles below cover the rest.",
                {n: DEV_MAX_SERIES}), "info");
        return;
      }
      dev.selected.add(i);
    } else dev.selected.delete(i);
    devRenderLegend();
  }
}

/* ── data ────────────────────────────────────────────────────────── */

function devResetBuffers(){
  dev.lastSeq = -1;
  dev.series = dev.channels.map(()=>[]);
  dev.span = dev.channels.map(()=>({min:null, max:null}));
  dev.bendSpan = dev.channels.map(()=>({min:null, max:null}));
}

function devSetChannels(names){
  const same = names.length === dev.channels.length &&
               names.every((n,i)=> n === dev.channels[i]);
  if(same) return;
  dev.channels = names.slice();
  dev.selected = new Set(names.map((_,i)=>i).slice(0, DEV_MAX_SERIES));
  devResetBuffers();
  devRenderChannelTiles();
  devRenderLegend();
  devSyncUnitOptions();
}

/* Only offer units that some fitted channel can actually be shown in.
   With no flex strip wired, "Bend (%)" previously stayed selectable and drew
   an empty chart — an offered control that does nothing reads as a bug. */
function devSyncUnitOptions(){
  const sel = document.querySelector('[data-dev="unit"]');
  if(!sel) return;
  let hidActive = false;
  for(const opt of sel.options){
    const kind = opt.dataset.kind;
    const ok = !kind || dev.channels.some((_,i) => devKind(i) === kind);
    opt.hidden = !ok;
    opt.disabled = !ok;
    if(!ok && opt.value === dev.unit) hidActive = true;
  }
  // Never leave the page on a unit that just disappeared.
  if(hidActive){ dev.unit = "force"; sel.value = "force"; }
}

async function devPollStatus(){
  try{
    const r = await fetch("/api/glove/status");
    dev.status = await r.json();
    devRenderConn();
    devRenderBanner();
    devRenderHealth();
  }catch(e){}
}

async function devPollSamples(){
  try{
    const r = await fetch(`/api/glove/samples?since=${dev.lastSeq}&max=2000`);
    const d = await r.json();
    if(d.channels && d.channels.length) devSetChannels(d.channels);

    if(d.console && d.console.length){
      dev.console.push(...d.console);
      if(dev.console.length > DEV_CONSOLE_CAP)
        dev.console = dev.console.slice(-DEV_CONSOLE_CAP);
      devRenderConsole();
    }

    if(d.frames && d.frames.length){
      dev.lastSeq = d.frames[d.frames.length-1][0];
      if(!dev.paused){
        for(const f of d.frames){
          for(let c=0; c<dev.channels.length; c++){
            const v = f[2+c];
            if(v === undefined) continue;
            const buf = dev.series[c];
            buf.push(v);
            if(buf.length > DEV_CAP) buf.splice(0, buf.length - DEV_CAP);
            const s = dev.span[c];
            if(s.min === null || v < s.min) s.min = v;
            if(s.max === null || v > s.max) s.max = v;
            if(devKind(c) === "flex") devTrackBendSpan(c, buf);
          }
        }
        devRenderChannelValues();
      }
    }
    document.getElementById("dev-scope-empty").style.display =
      (d.connected && dev.series.some(s=>s.length>1)) ? "none" : "";
  }catch(e){}
}

async function devPollImu(){
  try{
    const r = await fetch("/api/glove/imu");
    dev.imu = await r.json();
  }catch(e){ dev.imu = null; }
  devRenderImu();
}

async function devLoadEnv(){
  try{
    const r = await fetch("/api/dev/env");
    dev.env = await r.json();
    devRenderEnv();
    devRenderConn();
  }catch(e){}
}

/* ── rendering ───────────────────────────────────────────────────── */

function devRenderEnv(){
  const e = dev.env; if(!e) return;
  const py = e.python_exe ? e.python_exe.split(/[\\/]/).slice(-3).join("\\") : "?";
  const missing = e.missing_deps || [];

  // "Cannot tell" is its own state. Without pyserial there is no way to look
  // at the USB bus, so claiming "Not plugged in" would be a false negative.
  const board = e.board_detected === null
    ? devPill("warn", t("Board"), t("Unknown — needs pyserial"))
    : devPill(e.board_detected ? "ok" : "warn", t("Board"),
              t(e.board_detected ? "Detected" : "Not plugged in"));

  // The interpreter pill reports CONSEQUENCES, not identity. A non-venv python
  // with every package importable is fine and must not be flagged red — the
  // old version kept shouting after the underlying problem had been fixed.
  const interp = missing.length
    ? devPill("bad", t("Interpreter"), t("missing {names}", {names: missing.join(", ")}))
    : devPill("ok", t("Interpreter"),
              `Python ${e.python_version || "?"}${e.on_venv ? " (.venv)" : ""}`);

  document.getElementById("dev-env").innerHTML =
    interp +
    devPill(e.pyserial ? "ok":"bad", "pyserial", t(e.pyserial ? "Installed" : "Missing")) +
    devPill(e.arduino_cli_present ? "ok":"bad", "arduino-cli", t(e.arduino_cli_present ? "Found" : "Missing")) +
    devPill(e.mbed_core ? "ok":"bad", t("mbed_nano core"), t(e.mbed_core ? "Installed" : "Missing")) +
    devImuLibPill(e) +
    devPill(e.sketch_present ? "ok":"bad", t("Sketch"), e.sketch_present ? "glove.ino" : t("Missing")) +
    board;

  const warn = document.getElementById("dev-env-warn");
  if(warn && e.arduino_cli_present && e.imu_selected &&
     e.imu_selected !== "none" && !e.imu_ready){
    // This is a compile blocker, not a runtime one: the sketch asks for a
    // header that is not there, and says so rather than quietly building
    // without motion.
    const btn = t(e.imu_selected === "LSM9DS1"
      ? "IMU lib: original (LSM9DS1)" : "IMU lib: Rev2 (BMI270)");
    warn.innerHTML = t(
      "<strong>glove.ino selects <code>{imu}</code>, which is not installed.</strong> " +
      "Compiling will fail on the missing header. Press <em>{btn}</em> below — or, if " +
      "that is the wrong chip for this board, change the <code>#define GLOVE_IMU_…</code> " +
      "line at the top of <code>firmware/glove/glove.ino</code> to match the silkscreen.",
      {imu: e.imu_selected, btn});
    warn.style.display = "";
  } else if(warn){
    const show = missing.length > 0;
    warn.innerHTML = !show ? "" : t(
      "<strong>{names} {isare} not importable by this hub.</strong> It is running " +
      "<code>{py}</code>{venv}. Either restart it with <code>run_hub.bat</code>, or use " +
      "the install button below — that installs into the interpreter this hub is " +
      "actually using.",
      {
        names: missing.join(t(" and ")),
        isare: t(missing.length > 1 ? "are" : "is"),
        py,
        venv: e.on_venv ? "" : t(", which is not the project's <code>.venv</code>"),
      });
    warn.style.display = show ? "" : "none";
  }
  const note = document.getElementById("dev-env-note");
  if(note) note.textContent = e.fqbn;
}

/* Which IMU the SKETCH is set to build against, and whether that library is
   installed. The selection is a one-line #define in glove.ino chosen by board
   revision (plan §1.3), so "installed" on its own answers the wrong question:
   what matters is whether the compile will find the header it asks for. */
function devImuLibPill(e){
  const sel = e.imu_selected;
  if(!sel) return devPill("warn", "IMU", t("Sketch selection unreadable"));
  if(sel === "none") return devPill("warn", "IMU", t("Sketch builds without motion"));
  return e.imu_ready
    ? devPill("ok", "IMU", sel)
    : devPill("bad", "IMU", t("{imu} selected, not installed", {imu: sel}));
}

function devRenderConn(){
  const e = dev.env, st = dev.status;
  const connected = !!(st && st.connected);
  const ports = (e && e.ports) || [];

  // Rebuilding this row on every 4 s status poll would reset the <select> and
  // steal focus mid-interaction, so only redraw when something actually moved.
  const sig = JSON.stringify([connected, st && st.port, e && e.pyserial,
                              ports.map(p=>p.port + p.is_glove)]);
  if(sig === dev.connSig) return;
  dev.connSig = sig;

  const opts = ports.length
    ? ports.map(p => `<option value="${p.port}">${p.port}${p.is_glove ? " — Arduino" : ""}${p.description ? " (" + p.description + ")" : ""}</option>`).join("")
    : `<option value="">${t("No serial ports found")}</option>`;

  document.getElementById("dev-conn").innerHTML = `
    <label class="dev-sel">${t("Port")} <select data-dev="port" ${connected?"disabled":""}>${opts}</select></label>
    ${devBtn("refreshports",t("Refresh"))}
    ${connected
      ? devBtn("disconnect",t("Disconnect"), I.stop, "btn-danger")
      : devBtn("connect",t("Connect"), I.play, "btn-primary")}
    ${devPill(connected?"ok":"warn",t("Serial"), connected ? (st.port || t("connected")) : t("Disconnected"))}`;

  // Restore the port: what the board reports, else a pick the user actually
  // made, else the one that looks like an Arduino. The pin is what separates
  // those last two -- dev.port is also written from whatever the box happened
  // to be showing, so without it a board plugged in while this page was
  // already open loses to the Bluetooth port that was sitting in the select,
  // and each Refresh re-selects that dead port instead of the Arduino.
  // A pinned port that has gone away releases the pin rather than holding a
  // selection that cannot be opened: flashing re-enumerates the board on a
  // different COM number (GLOVE_FIRMWARE_PLAN.md 7.2), so the port the user
  // picked by hand a minute ago is routinely not the port it is on now.
  const sel = document.querySelector('[data-dev="port"]');
  if(sel){
    const has = v => !!v && [...sel.options].some(o => o.value === v);
    if(dev.portPinned && !has(dev.port)) dev.portPinned = false;
    const want = (st && st.port) ||
                 (dev.portPinned ? dev.port : null) ||
                 (ports.find(p => p.is_glove) || {}).port;
    if(has(want)) sel.value = want;
    dev.port = sel.value;
  }
  const cbtn = document.querySelector('[data-dev="connect"]');
  if(cbtn && (!e || !e.pyserial)){
    cbtn.disabled = true;
    cbtn.title = t("Install pyserial first — use the button above.");
  }
}

function devRenderBanner(){
  const b = dev.status && dev.status.banner;
  const el = document.getElementById("dev-banner");
  if(!b){ el.innerHTML = `<div class="dev-banner-empty">${t("No banner yet — connect and the board announces its firmware, rate and column layout.")}</div>`; return; }
  const rows = [
    [t("Firmware"), b.fw],
    [t("Protocol"), b.proto + (b.supported ? t(" (supported)") : t(" (UNSUPPORTED)"))],
    [t("Board"), b.board], [t("Rate"), b.rate + " Hz"],
    ["ADC", t("{bits}-bit @ {mv} mV", {bits: b.adc_bits, mv: b.adc_ref_mv})],
    [t("Divider"), b.vdiv_mv + " mV / " + b.r_fixed + " Ω"],
    ["IMU", b.imu], [t("Channels"), b.channels.join(", ") || "—"],
  ];
  el.innerHTML = rows.map(([k,v]) =>
    `<div class="dev-kv"><span>${k}</span><b>${v}</b></div>`).join("");
}

function devRenderLegend(){
  const el = document.getElementById("dev-legend");
  const sel = [...dev.selected].sort((a,b)=>a-b);
  if(!dev.channels.length || sel.length < 2){ el.innerHTML = ""; return; }
  // A legend is always present for >= 2 series; the name sits beside the
  // swatch so identity never rides on colour alone.
  el.innerHTML = sel.map(i =>
    `<span class="dev-key"><i style="background:${DEV_SERIES[i % DEV_MAX_SERIES]}"></i>${dev.channels[i]}</span>`).join("");
}

function devRenderChannelTiles(){
  const el = document.getElementById("dev-channels");
  if(!dev.channels.length){
    el.innerHTML = `<div class="dev-banner-empty">${t("No channels yet.")}</div>`;
    return;
  }
  el.innerHTML = dev.channels.map((name,i) => `
    <div class="dev-chan">
      <div class="dev-chan-head">
        <label class="dev-check"><input type="checkbox" data-dev="chan" data-i="${i}"
          ${dev.selected.has(i)?"checked":""}> <i class="dev-swatch" style="background:${DEV_SERIES[i % DEV_MAX_SERIES]}"></i>${name}</label>
        <span class="dev-chan-kind">${t(devKind(i))}</span>
      </div>
      <div class="dev-chan-val" id="dev-force-${i}">&#8212;</div>
      <div class="dev-chan-sub" id="dev-gram-${i}">&#8212;</div>
      <div class="dev-chan-bar"><i id="dev-bar-${i}" style="background:${DEV_SERIES[i % DEV_MAX_SERIES]}"></i><u id="dev-barpk-${i}"></u></div>
      <div id="dev-badge-${i}"></div>
      <div class="dev-chan-raw" id="dev-raw-${i}">&#8212;</div>
      <div class="dev-chan-span" id="dev-span-${i}">${t("peak")} &#8212;</div>
    </div>`).join("");
}

/* Fraction of the tile bar to fill, 0-1, for the current reading and the peak.
   Force scales against the FSR402's rated band and bend against its span, so
   in both cases "full bar" means "top of what this part is specified for". */
function devSetBar(i, kind, ohm, b, rf){
  const fill = document.getElementById("dev-bar-" + i);
  const notch = document.getElementById("dev-barpk-" + i);
  if(!fill && !notch) return;

  let cur = null, peak = null;
  if(devIsImu(kind)){
    // Signed value, unsigned bar: the tile shows HOW MUCH this axis is moving,
    // and the number above it carries the direction.
    const fs = devImuFS(kind);
    const buf = dev.series[i] || [];
    const last = buf.length ? devImuVal(buf[buf.length-1]) : null;
    cur = last === null ? null : Math.abs(last) / fs;
    const s = dev.span[i];
    if(s && s.min !== null){
      peak = Math.max(Math.abs(devImuVal(s.min)), Math.abs(devImuVal(s.max))) / fs;
    }
  } else if(kind === "flex"){
    const sp = devFlexSpan(i);
    cur = devBend(ohm, sp);
    const s = dev.span[i];
    if(s && s.min !== null) peak = devBend(devOhm(s.min, b, rf), sp);
    cur = cur === null ? null : cur / 100;
    peak = peak === null ? null : peak / 100;
  } else if(kind === "fsr"){
    const m = devForceModel();
    const max = (m && m.rated_max_n) || 20;
    const n = devForce(ohm);
    cur = n === null ? null : n / max;
    const s = dev.span[i];
    if(s && s.max !== null){
      const pn = devForce(devOhm(s.max, b, rf));
      peak = pn === null ? null : pn / max;
    }
  }
  const pct = x => (x === null ? 0 : Math.max(0, Math.min(1, x)) * 100).toFixed(1) + "%";
  if(fill) fill.style.width = pct(cur);
  if(notch){
    notch.style.display = peak === null ? "none" : "block";
    notch.style.left = pct(peak);
  }
}

/* One motion channel's tile: value, full-scale bar, and the extreme seen
   since the last Z. Peak is |value|: an accelerometer swings both ways, and
   taking the maximum alone would report a hand that only ever accelerated
   downward as having done nothing. */
function devRenderImuChannel(i, kind){
  const buf = dev.series[i];
  if(!buf || !buf.length) return;
  const raw = dev.smooth ? devMedian(buf.slice(-DEV_SMOOTH_N)) : buf[buf.length-1];
  const v = devImuVal(raw);
  const fs = devImuFS(kind);
  const set = (id, text) => { const el = document.getElementById(id+i); if(el) el.textContent = text; };

  set("dev-force-", devImuText(v, kind));
  set("dev-gram-", t(kind === "gyro" ? "rotation rate" : "proper acceleration"));
  const bd = document.getElementById("dev-badge-"+i);
  const b = dev.status && dev.status.banner;
  if(bd) bd.innerHTML = `<span class="dev-badge dev-badge-dim">${t("onboard {imu}", {imu: b && b.imu ? b.imu : "IMU"})}</span>`;
  set("dev-raw-", `${raw} m${kind === "gyro" ? "dps" : "g"} \u00b7 ${t("bar")} \u00b1${fs}${devImuUnit(kind)}`);

  devSetBar(i, kind, null, b, null);

  const sp = document.getElementById("dev-span-"+i);
  const s = dev.span[i];
  if(sp){
    if(!s || s.min === null) sp.textContent = t("peak") + " \u2014";
    else {
      const peak = Math.max(Math.abs(devImuVal(s.min)), Math.abs(devImuVal(s.max)));
      sp.textContent = `${t("peak")} \u00b1${devImuText(peak, kind)}`;
    }
  }
}

function devRenderChannelValues(){
  const b = dev.status && dev.status.banner;
  for(let i=0;i<dev.channels.length;i++){
    const buf = dev.series[i];
    if(!buf || !buf.length) continue;
    const kind = devKind(i);
    const rf = devRFixed(i);

    // Motion channels leave before any divider maths happens. Not a style
    // choice: mv/ohm/force computed from an acceleration are numbers with no
    // meaning, and a tile that prints them is worse than one that prints
    // nothing.
    if(devIsImu(kind)){ devRenderImuChannel(i, kind); continue; }
    // Smoothing applies to the headline number as well as the trace, so the
    // tile and the plot never disagree about what is on screen.
    const v = dev.smooth
      ? devMedian(buf.slice(-DEV_SMOOTH_N))
      : buf[buf.length-1];
    const ohm = devOhm(v, b, rf);
    const us = ohm ? 1e6/ohm : null;

    const set = (id, text) => { const el = document.getElementById(id+i); if(el) el.textContent = text; };
    const bd = document.getElementById("dev-badge-"+i);

    // Branch by sensor kind. The FSR402 force curve is meaningless for a bend
    // sensor — applying it anyway would print confident newtons for a bending
    // finger, which is exactly the kind of dressed-up guess this project
    // refuses to show.
    if(kind === "flex"){
      const span = devFlexSpan(i);
      const pct = devBend(ohm, span);
      set("dev-force-", devBendText(pct));
      set("dev-gram-", devOhmText(ohm));
      if(bd) bd.innerHTML = devBendBadge(devBendRange(ohm, span), span);
    } else if(kind === "fsr"){
      const n = devForce(ohm);
      set("dev-force-", devForceText(n));
      set("dev-gram-", devGramsText(n) || "—");
      if(bd) bd.innerHTML = devForceBadge(devForceRange(n));
    } else {
      // Unknown kind: stop at what was actually measured rather than guess.
      set("dev-force-", devOhmText(ohm));
      set("dev-gram-", "—");
      if(bd) bd.innerHTML = `<span class="dev-badge dev-badge-dim">${t("unknown sensor — raw only")}</span>`;
    }
    set("dev-raw-", `${v} adc · ${devOhmText(ohm)} · ${us === null ? "—" : us.toFixed(0)+" µS"}`);

    // Fill + peak notch, so "which sensor is pressed hardest" is a glance
    // rather than a comparison of numbers across tiles. Scaled to the part's
    // rated band; the numeric readout and badge above stay authoritative
    // (style guide 2.4 — never meaning in colour or length alone).
    devSetBar(i, kind, ohm, b, rf);

    // Peak latches from the extreme ADC already tracked for the span — the
    // number that matters for a grip, a tap, or a full finger curl. Peak is
    // always taken from RAW counts, never the smoothed value: smoothing is a
    // display aid and must not quietly lower a recorded maximum.
    const s = dev.span[i];
    const sp = document.getElementById("dev-span-"+i);
    if(sp){
      if(s.max === null || s.min === null) sp.textContent = t("peak") + " —";
      else {
        // Which end of the ADC span is the "peak" depends on the sensor. Both
        // sit on the high side of their divider, so resistance rising pulls
        // the reading DOWN. Pressing an FSR lowers its resistance, so hardest
        // press = highest count; bending a flex strip raises its resistance,
        // so most bend = LOWEST count. Taking s.max for both would report a
        // flex sensor's peak as the moment it was straightest.
        const peakAdc = kind === "flex" ? s.min : s.max;
        const peakOhm = devOhm(peakAdc, b, rf);
        const peak = kind === "flex"
          ? devBendText(devBend(peakOhm, devFlexSpan(i)))
          : devForceText(devForce(peakOhm));
        sp.textContent = t("peak {peak}  ·  adc span {lo}–{hi} of {max}",
          {peak, lo: s.min, hi: s.max, max: b ? (1<<b.adc_bits)-1 : 1023});
      }
    }
  }
}

/* ── Motion card (onboard IMU) ───────────────────────────────────────

   The camera measures WHERE the hand is; this measures how it is moving,
   sampled on the hand itself at 100 Hz. Every derived number here comes from
   core/glove/imu.py via /api/glove/imu — the tremor band and its minimum
   window are defined there and shipped in the payload, so this page never
   carries its own copy of a threshold. */

// Signed bar: zero in the middle, fill growing left or right, so the sign is
// visible without reading the number. Clamped at full scale.
function devAxisRow(label, value, kind, colour){
  const fs = devImuFS(kind);
  const v = value === null || value === undefined ? null : value;
  const frac = v === null ? 0 : Math.max(-1, Math.min(1, v / fs));
  const w = Math.abs(frac) * 50;
  const left = frac >= 0 ? 50 : 50 - w;
  return `<div class="dev-axis">
    <span class="dev-axis-l">${label}</span>
    <span class="dev-axis-bar"><i style="left:${left}%;width:${w}%;background:${colour}"></i></span>
    <span class="dev-axis-v">${devImuText(v, kind)}</span>
  </div>`;
}

function devRenderImu(){
  const el = document.getElementById("dev-imu");
  if(!el) return;
  const d = dev.imu;

  if(!d || !d.present){
    // Say WHY there is nothing, always. A blank motion card is
    // indistinguishable from a board sitting perfectly still.
    const note = (d && d.note) ? tMsg(d.note)
      : t("Connect the board to read its onboard accelerometer and gyroscope.");
    el.innerHTML = `<div class="dev-banner-empty">${note}</div>`;
    return;
  }

  const tilt = d.tilt || {};   // not `t` — that is the translator
  const tr = d.tremor;
  const stat = (n, l, cls) =>
    `<div class="dev-stat"><div class="dev-stat-n ${cls || ""}">${n}</div>
     <div class="dev-stat-l">${l}</div></div>`;
  const f = (v, dp, suffix) =>
    (v === null || v === undefined) ? "\u2014" : v.toFixed(dp) + (suffix || "");

  // Tilt is only gravity when the hand is still; during movement the vector is
  // gravity PLUS whatever the hand is doing, and an angle read off it is a
  // guess. The server decides which case this is; the card just reports it.
  const tiltVal = tilt.static
    ? `${f(tilt.pitch_deg, 0, "\u00b0")} / ${f(tilt.roll_deg, 0, "\u00b0")}`
    : t("moving");
  const tiltLbl = tilt.static
    ? t("Tilt pitch / roll \u2014 board axes")
    : t("Tilt \u2014 hold still, this needs gravity alone");

  const stats =
    stat(tiltVal, tiltLbl, tilt.static ? "" : "bad") +
    stat(f(d.accel && d.accel.magnitude, 2, " g"), t("Acceleration magnitude \u2014 1.00 g at rest")) +
    stat(f(d.motion_rms_g == null ? null : d.motion_rms_g * 1000, 0, " mg"),
         t("Motion RMS \u2014 movement about its own mean")) +
    stat(f(d.gyro_rms_dps, 1, " \u00b0/s"), t("Rotation RMS")) +
    stat(tr ? f(tr.peak_hz, 1, " Hz") : "\u2014",
         tr ? t("Tremor peak in {lo}\u2013{hi} Hz",
                {lo: tr.band[0].toFixed(1), hi: tr.band[1].toFixed(1)})
            : t("Tremor peak \u2014 not enough data yet")) +
    stat(tr ? f(tr.band_frac * 100, 1, " %") : "\u2014",
         t("Share of movement power in the tremor band"));

  const A = DEV_SERIES[0], G = DEV_SERIES[2];
  const a = d.accel || {}, gy = d.gyro || {};
  const axes = `<div class="dev-axes">
      ${devAxisRow("ax", a.x, "accel", A)}
      ${devAxisRow("ay", a.y, "accel", A)}
      ${devAxisRow("az", a.z, "accel", A)}
      ${devAxisRow("gx", gy.x, "gyro", G)}
      ${devAxisRow("gy", gy.y, "gyro", G)}
      ${devAxisRow("gz", gy.z, "gyro", G)}
    </div>`;

  // Honesty row. Each badge names a specific reason the numbers above are
  // weaker than they look, and is absent when it does not apply.
  const badges = [];
  if(d.held_frac !== null && d.held_frac !== undefined && d.held_frac > 0.02){
    badges.push(`<span class="dev-badge dev-badge-warn">${t(
      "{pct}% of frames repeated the previous IMU sample \u2014 the chip's own rate is below {fs} Hz, which flattens the top of the band",
      {pct: (d.held_frac*100).toFixed(0), fs: d.fs})}</span>`);
  }
  if(!tr && d.tremor_note){
    badges.push(`<span class="dev-badge dev-badge-dim">${tMsg(d.tremor_note)}</span>`);
  }
  if(tr){
    badges.push(`<span class="dev-badge dev-badge-dim">${t(
      "{s} s window at {fs} Hz \u00b7 {imu}",
      {s: tr.window_s.toFixed(1), fs: d.fs, imu: d.imu})}</span>`);
  }

  el.innerHTML = `<div class="dev-health">${stats}</div>${axes}
    <div class="dev-imu-badges">${badges.join(" ")}</div>`;
}

function devRenderHealth(){
  const s = dev.status; if(!s) return;
  const rate = s.rate_hz ? s.rate_hz.toFixed(2) + " Hz" : "—";
  const target = s.banner ? s.banner.rate : 0;
  const rateOk = target ? Math.abs(s.rate_hz - target) < target*0.05 : false;
  document.getElementById("dev-health").innerHTML =
    `<div class="dev-stat"><div class="dev-stat-n ${rateOk?"good":""}">${rate}</div><div class="dev-stat-l">${t("Measured rate")}${target?` ${t("(target {n})",{n:target})}`:""}</div></div>
     <div class="dev-stat"><div class="dev-stat-n ${s.dropped?"bad":"good"}">${s.dropped}</div><div class="dev-stat-l">${t("Dropped frames")}</div></div>
     <div class="dev-stat"><div class="dev-stat-n">${s.total}</div><div class="dev-stat-l">${t("Frames received")}</div></div>
     <div class="dev-stat"><div class="dev-stat-n">${s.uptime_s ? s.uptime_s.toFixed(0)+" s" : "—"}</div><div class="dev-stat-l">${t("Connected for")}</div></div>
     <div class="dev-stat"><div class="dev-stat-n">${s.recording ? s.record_rows : t("off")}</div><div class="dev-stat-l">${s.recording ? t("Rows recorded — {path}",{path:s.record_path}) : t("Recording")}</div></div>`;

  const rec = document.querySelector('[data-dev="rec"]');
  if(rec) rec.textContent = t(s.recording ? "Stop Recording" : "Start Recording");
  if(s.last_error) document.getElementById("dev-banner").dataset.err = s.last_error;
}

function devRenderConsole(){
  const el = document.getElementById("dev-console");
  el.textContent = dev.console.join("\n");
  if(dev.autoscroll) el.scrollTop = el.scrollHeight;
}

/* ── scope ───────────────────────────────────────────────────────── */

function devDraw(){
  const cv = document.getElementById("dev-scope");
  if(!cv || !cv.clientWidth) return;
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if(cv.width !== w*dpr || cv.height !== h*dpr){ cv.width = w*dpr; cv.height = h*dpr; }
  const g = cv.getContext("2d");
  g.setTransform(dpr,0,0,dpr,0,0);
  g.clearRect(0,0,w,h);

  const b = dev.status && dev.status.banner;
  const rate = (b && b.rate) || 100;
  const adcMax = b ? (1<<b.adc_bits)-1 : 1023;
  const n = Math.max(2, Math.round(rate * dev.window_s));
  const pad = {l:46, r:10, t:10, b:20};
  const pw = w - pad.l - pad.r, ph = h - pad.t - pad.b;
  if(pw <= 0 || ph <= 0) return;

  const sel = [...dev.selected].sort((a,b)=>a-b);

  // Map raw ADC into the selected unit. One unit for the whole plot — a second
  // y-scale would make two series silently incomparable.
  const fm = devForceModel();
  const convFor = (i) => {
    // Both resolved once per channel per redraw, not per sample: they depend
    // only on the channel, and the window holds hundreds of samples.
    const rf = devRFixed(i);
    const sp = dev.unit === "bend" ? devFlexSpan(i) : null;
    return {
      adc:   v => v,
      ohm:   v => devOhm(v, b, rf),
      us:    v => { const r = devOhm(v, b, rf); return r ? 1e6/r : null; },
      force: v => devForce(devOhm(v, b, rf)),
      bend:  v => devBend(devOhm(v, b, rf), sp),
      accel: devImuVal,
      gyro:  devImuVal,
    }[dev.unit] || (v => v);
  };
  const fixedRange = {
    adc:   [0, adcMax],
    force: [0, fm ? fm.rated_max_n : 20],   // default to the part's rated band
    bend:  [0, 100],
    ohm:   [0, (b ? b.r_fixed : 10000) * 3],
    us:    [0, 2000],
    // Motion is signed and centred on zero - a 0-based axis would put a hand
    // at rest against the floor of the plot and hide half of every wobble.
    accel: [-DEV_ACCEL_FS, DEV_ACCEL_FS],
    gyro:  [-DEV_GYRO_FS, DEV_GYRO_FS],
  }[dev.unit] || [0, adcMax];
  const label = {adc:"", ohm:" Ω", us:" µS", force:" N", bend:" %",
                 accel:" g", gyro:" °/s"}[dev.unit] || "";

  // Newtons and bend-percent cannot share a y-axis without being misleading,
  // so a kind-specific unit draws only the channels it applies to. The
  // kind-neutral units (adc/ohm/us) still draw everything.
  const unitKind = {force:"fsr", bend:"flex", accel:"accel", gyro:"gyro"}[dev.unit] || null;
  const drawable = sel.filter(i => !unitKind || devKind(i) === unitKind);

  const traces = drawable.map(i => devSmoothSeries(
    (dev.series[i] || []).slice(-n).map(convFor(i))));

  // Stacked gives every channel its own band, so traces cannot overlap however
  // many sensors are fitted — the failure mode of the shared axis is that
  // unpressed sensors all sit on zero and draw on top of each other. Overlaid
  // stays available because it is still the right view for comparing two
  // channels' magnitudes directly.
  if(dev.view === "stacked"){
    devDrawStacked(g, {pad, pw, ph, n, traces, drawable, fixedRange, label, unitKind, sel});
    return;
  }

  let [lo, hi] = fixedRange;
  if(dev.yAuto){
    lo = Infinity; hi = -Infinity;
    for(const t of traces) for(const v of t){
      if(v === null) continue;
      if(v<lo) lo=v; if(v>hi) hi=v;
    }
    if(!isFinite(lo)){ [lo, hi] = fixedRange; }
    const min = dev.unit === "force" ? 0.5 : 10;
    if(hi - lo < min){ const m=(hi+lo)/2; lo=Math.max(0,m-min/2); hi=m+min/2; }
  }
  const yOf = v => pad.t + ph * (1 - (v-lo)/((hi-lo)||1));
  const fmtTick = v => Math.abs(v) >= 100 ? Math.round(v).toString()
                     : (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1));

  // Recessive grid + axis labels in text tokens, never a series colour.
  g.strokeStyle = "#2A3442"; g.lineWidth = 1;
  g.fillStyle = "#64748B"; g.font = DEV_FONT;
  g.textAlign = "right"; g.textBaseline = "middle";
  for(let k=0;k<=4;k++){
    const v = lo + (hi-lo)*k/4, y = Math.round(yOf(v))+0.5;
    g.beginPath(); g.moveTo(pad.l, y); g.lineTo(pad.l+pw, y); g.stroke();
    g.fillText(fmtTick(v) + (k===4 ? label : ""), pad.l-8, y);
  }
  // In force mode, mark the actuation floor: below it the part is unspecified.
  if(dev.unit === "force" && fm && fm.rated_min_n > lo && fm.rated_min_n < hi){
    const y = Math.round(yOf(fm.rated_min_n)) + 0.5;
    g.save(); g.strokeStyle = "#64748B"; g.setLineDash([3,4]);
    g.beginPath(); g.moveTo(pad.l, y); g.lineTo(pad.l+pw, y); g.stroke(); g.restore();
  }
  g.textAlign = "center"; g.textBaseline = "top";
  g.fillText(`-${dev.window_s}s`, pad.l+14, pad.t+ph+5);
  g.fillText(t("now"), pad.l+pw-14, pad.t+ph+5);

  // 2px lines, one per drawable channel, in fixed palette order.
  //
  // Clip to the plot rectangle. The fixed force range stops at the part's
  // rated 20 N, but nothing clamps the values, so a hard press maps above the
  // top gridline and used to draw over the axis labels and out to the canvas
  // edge — which read as the trace flattening out at 20 N when it was really
  // running off the chart. Clipping makes "off the top" look like off the top.
  // Switch the Y axis to Auto to see where it actually went.
  g.save();
  g.beginPath();
  g.rect(pad.l, pad.t, pw, ph);
  g.clip();
  g.lineWidth = 2; g.lineJoin = "round"; g.lineCap = "round";
  drawable.forEach((i, s) => {
    const data = traces[s];
    if(!data || data.length < 2) return;
    g.strokeStyle = DEV_SERIES[i % DEV_MAX_SERIES];
    g.beginPath();
    let pen = false;
    for(let k=0;k<data.length;k++){
      const v = data[k];
      // An open sensor has no resistance/force — break the line rather than
      // drawing a fake zero.
      if(v === null){ pen = false; continue; }
      const x = pad.l + pw * (k/(n-1));
      const y = yOf(v);
      if(pen) g.lineTo(x,y); else g.moveTo(x,y);
      pen = true;
    }
    g.stroke();
  });
  g.restore();   // release the plot-rectangle clip

  g.fillStyle = "#64748B"; g.font = DEV_FONT;
  g.textAlign = "left"; g.textBaseline = "top";
  if(!drawable.length && unitKind){
    devDrawEmptyNote(g, pad, pw, unitKind, sel);
  } else {
    const hidden = sel.length - drawable.length;
    if(hidden > 0){
      g.fillText(t("{n} channels hidden — not {kind}",
                   {n: hidden, kind: devKindWord(unitKind)}), pad.l + 6, pad.t + 6);
    }
    // On an observed span, say so on the plot too — the y-axis reads 0-100%
    // and that is 100% of what has been SEEN, not of the sensor's travel.
    if(dev.unit === "bend" && drawable.length){
      const sp = devFlexSpan(drawable[0]);
      if(sp && sp.basis !== "calibrated"){
        g.textAlign = "right";
        g.fillText(t(sp.basis === "observed" ? "% of observed range" : "provisional range"),
                   pad.l + pw - 6, pad.t + 6);
      }
    }
  }
}

/* One lane per channel, sharing a single time axis.

   Each lane scales to its OWN data. That is the point: on a shared axis a
   light touch is invisible next to a hard press, and every idle sensor sits
   on the same zero line. Per-lane scaling costs direct magnitude comparison
   between lanes, which is exactly what the Overlaid view is still there for.

   The shared time axis is kept deliberately — it is what lets you see which
   sensor moved first, and separate mini-charts would lose that. */
function devDrawStacked(g, o){
  const {pad, pw, ph, n, traces, drawable, fixedRange, label, unitKind, sel} = o;
  const TEXT = "#64748B", GRID = "#2A3442";
  g.font = DEV_FONT;

  if(!drawable.length){
    devDrawEmptyNote(g, pad, pw, unitKind, sel);
    return;
  }

  const GAP = 8;
  const laneH = Math.max(18, (ph - GAP * (drawable.length - 1)) / drawable.length);
  const fmt = v => Math.abs(v) >= 100 ? Math.round(v).toString()
                 : (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1));

  drawable.forEach((ch, s) => {
    const data = traces[s] || [];
    const top = pad.t + s * (laneH + GAP);
    const bot = top + laneH;
    const colour = DEV_SERIES[ch % DEV_MAX_SERIES];

    // Lane range: start from the unit's fixed range so an idle lane still has
    // a sensible scale, then grow to fit anything that exceeds it. Never
    // shrink below the fixed range, or resting noise would fill the lane and
    // read as violent activity.
    let lo = fixedRange[0], hi = fixedRange[1];
    for(const v of data){ if(v === null) continue; if(v < lo) lo = v; if(v > hi) hi = v; }
    if(hi - lo <= 0) hi = lo + 1;
    const yOf = v => bot - (bot - top) * ((v - lo) / (hi - lo));

    // Baseline + top rule bound the lane so it reads as its own strip.
    g.strokeStyle = GRID; g.lineWidth = 1;
    g.beginPath();
    g.moveTo(pad.l, Math.round(bot) + 0.5); g.lineTo(pad.l + pw, Math.round(bot) + 0.5);
    g.stroke();

    // Peak marker — the hardest press since the last reset, from the raw ADC
    // span the poll loop already tracks. Faint: it is a reference, not data.
    const sp = dev.span[ch];
    if(sp && sp.max !== null){
      const b = dev.status && dev.status.banner;
      const pv = devLaneValue(ch, unitKind === "flex" ? sp.min : sp.max, b);
      if(pv !== null && pv > lo && pv < hi){
        g.save();
        g.strokeStyle = colour; g.globalAlpha = 0.35; g.setLineDash([2,3]);
        const y = Math.round(yOf(pv)) + 0.5;
        g.beginPath(); g.moveTo(pad.l, y); g.lineTo(pad.l + pw, y); g.stroke();
        g.restore();
      }
    }

    // Trace, clipped to its own lane so an over-range press cannot bleed into
    // a neighbour and be mistaken for that sensor firing.
    g.save();
    g.beginPath(); g.rect(pad.l, top, pw, bot - top); g.clip();
    g.strokeStyle = colour; g.lineWidth = 2; g.lineJoin = "round"; g.lineCap = "round";
    g.beginPath();
    let pen = false;
    for(let k = 0; k < data.length; k++){
      const v = data[k];
      if(v === null){ pen = false; continue; }   // open sensor: break the line
      const x = pad.l + pw * (k / (n - 1));
      const y = yOf(v);
      if(pen) g.lineTo(x, y); else g.moveTo(x, y);
      pen = true;
    }
    g.stroke();
    g.restore();

    // Channel name left, live value right — the trace and its number in one
    // place, instead of glancing down at the tiles to read the graph.
    g.fillStyle = colour;
    g.textAlign = "right"; g.textBaseline = "middle";
    g.fillText(dev.channels[ch] || ("ch" + ch), pad.l - 8, (top + bot) / 2);

    let last = null;
    for(let k = data.length - 1; k >= 0; k--){ if(data[k] !== null){ last = data[k]; break; } }
    g.textAlign = "right"; g.textBaseline = "top";
    g.fillStyle = last === null ? TEXT : colour;
    g.fillText(last === null ? "—" : fmt(last) + label, pad.l + pw - 4, top + 2);

    // Lane ceiling, so "how much headroom is left" is legible at a glance.
    g.fillStyle = TEXT; g.textAlign = "left"; g.textBaseline = "top";
    g.fillText(fmt(hi) + label, pad.l + 4, top + 2);
  });

  g.fillStyle = TEXT; g.textAlign = "center"; g.textBaseline = "top";
  g.fillText(`-${dev.window_s}s`, pad.l + 14, pad.t + ph + 5);
  g.fillText(t("now"), pad.l + pw - 14, pad.t + ph + 5);

  const hidden = sel.length - drawable.length;
  if(hidden > 0){
    g.textAlign = "left";
    g.fillText(t("{n} hidden — not {kind}", {n: hidden, kind: devKindWord(unitKind)}),
               pad.l + 4, pad.t + ph + 5);
  }
}

/* One raw ADC count → the currently selected unit, for a given channel.
   Mirrors convFor() inside devDraw but is callable from the lane renderer. */
function devLaneValue(ch, adc, b){
  if(adc === null || adc === undefined) return null;
  const rf = devRFixed(ch);
  switch(dev.unit){
    case "accel":
    case "gyro": return devImuVal(adc);
    case "adc":  return adc;
    case "ohm":  return devOhm(adc, b, rf);
    case "us":   { const r = devOhm(adc, b, rf); return r ? 1e6/r : null; }
    case "bend": return devBend(devOhm(adc, b, rf), devFlexSpan(ch));
    default:     return devForce(devOhm(adc, b, rf));
  }
}

/* A blank plot must say why it is blank — silently drawing nothing is
   indistinguishable from a dead sensor. */
/* What a unit's channels are called in prose, so every "nothing to draw"
   message names the right thing. */
function devKindWord(unitKind){
  const en = {fsr:"a force sensor", flex:"a bend sensor",
              accel:"an accelerometer axis", gyro:"a gyroscope axis"}[unitKind] || "that kind";
  return t(en);
}

function devDrawEmptyNote(g, pad, pw, unitKind, sel){
  g.fillStyle = "#64748B"; g.font = DEV_FONT;
  g.textAlign = "left"; g.textBaseline = "top";
  const word = devKindWord(unitKind);
  const anyOfKind = dev.channels.some((_, i) => devKind(i) === unitKind);
  const msg = !dev.channels.length
    ? t("no channels yet — connect the board")
    : !anyOfKind
      ? t("no {kind} on this board — check the banner's chan= field", {kind: word})
      : t("no {kind} selected — tick one in the tiles below", {kind: word});
  g.fillText(msg, pad.l + 6, pad.t + 6);
}

function devLoop(){
  devDraw();
  dev.raf = requestAnimationFrame(devLoop);
}

/* ── lifecycle (called from app.js showPage) ─────────────────────── */

function startDev(){
  devBuild();
  devLoadEnv();
  devPollStatus();
  devRenderChannelTiles();
  devRenderImu();
  if(!dev.fastTimer){
    dev.fastTimer = setInterval(()=>{
      devPollSamples();
      // Under reduced motion the scope refreshes on the poll tick instead of
      // running a continuous animation frame loop.
      if(reducedMotion) devDraw();
    }, DEV_POLL_MS);
  }
  if(!dev.envTimer) dev.envTimer = setInterval(devPollStatus, DEV_ENV_MS);
  // Slower than the sample poll on purpose: this endpoint runs a DFT, and the
  // raw motion columns are already live in the scope at DEV_POLL_MS.
  if(!dev.imuTimer) dev.imuTimer = setInterval(devPollImu, DEV_IMU_MS);
  if(!reducedMotion && !dev.raf) dev.raf = requestAnimationFrame(devLoop);
}

function stopDev(){
  clearInterval(dev.fastTimer); dev.fastTimer = null;
  clearInterval(dev.envTimer);  dev.envTimer = null;
  clearInterval(dev.imuTimer);  dev.imuTimer = null;
  if(dev.raf){ cancelAnimationFrame(dev.raf); dev.raf = null; }
}

/* A language switch redraws everything this page built. If the page has not
   been built yet, startDev() will build it in the new language anyway. */
onLang(() => {
  if(!dev.built) return;
  devBuildStatic();
  dev.connSig = null;          // force the connection row to redraw
  devRenderEnv();
  devRenderConn();
  devRenderBanner();
  devRenderChannelTiles();
  devRenderLegend();
  devRenderHealth();
  devRenderImu();
});

window.startDev = startDev;
window.stopDev = stopDev;
