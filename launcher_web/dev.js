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

const dev = {
  built: false, fastTimer: null, envTimer: null, raf: null,
  env: null, status: null,
  channels: [], series: [], span: [],   // per channel: values[], {min,max}
  lastSeq: -1, paused: false,
  window_s: 5, yAuto: false, unit: "force", smooth: false,
  console: [], autoscroll: true,
  selected: new Set(),
  port: null,          // user's chosen port, survives re-renders
  connSig: null,       // last rendered connection-row signature
};

/* ── helpers ─────────────────────────────────────────────────────── */

function devOhmText(v){
  if(v === null || v === undefined) return "open";
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
    open:   ["dev-badge-dim",  "no contact"],
    below:  ["dev-badge-dim",  `below ${m ? m.rated_min_n : 0.2} N actuation`],
    rated:  ["dev-badge-ok",   `datasheet ±${tol}%`],
    above:  ["dev-badge-warn", `beyond rated ${m ? m.rated_max_n : 20} N — upper bound only`],
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
  const ratio = (m && m.min_span_ratio) || 1.2;
  const b = dev.status && dev.status.banner;
  const s = dev.span[i];
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
  return pct.toFixed(0) + "% bend";
}
// An uncalibrated span must never look like a measurement, and the badge has
// to say WHICH span produced the number.
function devBendBadge(range, span){
  const basis = span ? span.basis : null;
  if(range === "open" || !basis){
    return `<span class="dev-badge dev-badge-dim">no signal</span>`;
  }
  if(basis === "provisional"){
    return `<span class="dev-badge dev-badge-warn">provisional span — bend the sensor to set its range</span>`;
  }
  if(range === "below" || range === "above"){
    // On an observed span this cannot persist: the span grows to include the
    // new extreme on the next frame. On a calibrated one it is a real warning.
    return `<span class="dev-badge dev-badge-warn">${range === "below" ? "flatter" : "bent"} than recorded — re-record span</span>`;
  }
  return basis === "calibrated"
    ? `<span class="dev-badge dev-badge-ok">calibrated span</span>`
    : `<span class="dev-badge dev-badge-warn">observed span — not calibrated</span>`;
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
function devMedian(values){
  const v = values.filter(x => x !== null && x !== undefined);
  if(!v.length) return null;
  const s = v.slice().sort((a,b)=>a-b);
  return s[Math.floor(s.length/2)];
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
    toast(d.message || (d.ok ? "Done" : "Failed"), d.ok ? "ok" : "fail");
    return d;
  }catch(e){ toast("Request failed", "fail"); return {ok:false}; }
}

/* ── static build ────────────────────────────────────────────────── */

function devBuild(){
  if(dev.built) return;
  const icon = document.getElementById("dev-icon");
  if(icon) icon.innerHTML = I.code;

  document.getElementById("dev-tasks").innerHTML =
    devBtn("setup", "Run Setup", I.play, "btn-primary") +
    devBtn("install_pyserial", "Install pyserial") +
    devBtn("compile", "Compile Firmware") +
    devBtn("upload", "Upload Firmware") +
    devBtn("tests", "Run Glove Tests");

  document.getElementById("dev-cmds").innerHTML =
    devBtn("cmd:?", "Re-read Banner") +
    devBtn("cmd:S", "Start Stream") +
    devBtn("cmd:X", "Stop Stream") +
    devBtn("cmd:Z", "Zero &amp; Reset Span") +
    devBtn("cmd:D", "Toggle Diagnostics") +
    devBtn("rec", "Start Recording", null, "btn-primary");

  // One unit at a time, never two y-scales on one plot.
  document.getElementById("dev-scope-tools").innerHTML =
    `<label class="dev-sel">Unit
       <select data-dev="unit"><option value="force" selected>Force (N)</option>
       <option value="bend">Bend (%)</option>
       <option value="adc">Raw ADC</option><option value="ohm">Resistance (&#937;)</option>
       <option value="us">Conductance (&#181;S)</option></select></label>
     <label class="dev-sel">Window
       <select data-dev="window"><option value="2">2 s</option>
       <option value="5" selected>5 s</option><option value="10">10 s</option></select></label>
     <label class="dev-sel">Y axis
       <select data-dev="yaxis"><option value="fixed" selected>Fixed</option>
       <option value="auto">Auto</option></select></label>
     <label class="dev-check" title="Median of ${DEV_SMOOTH_N} samples. Display only — recordings stay raw.">
       <input type="checkbox" data-dev="smooth"> Smooth (display only)</label>` +
    devBtn("pause", "Pause");

  document.getElementById("dev-console-tools").innerHTML =
    `<label class="dev-check"><input type="checkbox" data-dev="autoscroll" checked> Auto-scroll</label>` +
    devBtn("clearconsole", "Clear");

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
    btn.textContent = dev.paused ? "Resume" : "Pause";
    btn.classList.toggle("btn-primary", dev.paused);
    return;
  }
  if(id === "clearconsole"){ dev.console = []; devRenderConsole(); return; }
  if(id === "refreshports"){ await devLoadEnv(); toast("Ports refreshed", "info"); return; }

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
  if(el.dataset.dev === "smooth") dev.smooth = el.checked;
  if(el.dataset.dev === "autoscroll") dev.autoscroll = el.checked;
  if(el.dataset.dev === "port") dev.port = el.value;
  if(el.dataset.dev === "chan"){
    const i = +el.dataset.i;
    if(el.checked){
      if(dev.selected.size >= DEV_MAX_SERIES){
        el.checked = false;
        toast(`Scope shows at most ${DEV_MAX_SERIES} channels — the tiles below cover the rest.`, "info");
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
          }
        }
        devRenderChannelValues();
      }
    }
    document.getElementById("dev-scope-empty").style.display =
      (d.connected && dev.series.some(s=>s.length>1)) ? "none" : "";
  }catch(e){}
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
    ? devPill("warn", "Board", "Unknown — needs pyserial")
    : devPill(e.board_detected ? "ok" : "warn", "Board",
              e.board_detected ? "Detected" : "Not plugged in");

  // The interpreter pill reports CONSEQUENCES, not identity. A non-venv python
  // with every package importable is fine and must not be flagged red — the
  // old version kept shouting after the underlying problem had been fixed.
  const interp = missing.length
    ? devPill("bad", "Interpreter", `missing ${missing.join(", ")}`)
    : devPill("ok", "Interpreter",
              `Python ${e.python_version || "?"}${e.on_venv ? " (.venv)" : ""}`);

  document.getElementById("dev-env").innerHTML =
    interp +
    devPill(e.pyserial ? "ok":"bad", "pyserial", e.pyserial ? "Installed" : "Missing") +
    devPill(e.arduino_cli_present ? "ok":"bad", "arduino-cli", e.arduino_cli_present ? "Found" : "Missing") +
    devPill(e.mbed_core ? "ok":"bad", "mbed_nano core", e.mbed_core ? "Installed" : "Missing") +
    devPill(e.sketch_present ? "ok":"bad", "Sketch", e.sketch_present ? "glove.ino" : "Missing") +
    board;

  const warn = document.getElementById("dev-env-warn");
  if(warn){
    const show = missing.length > 0;
    warn.innerHTML = !show ? "" :
      `<strong>${missing.join(" and ")} ${missing.length>1?"are":"is"} not importable
       by this hub.</strong> It is running <code>${py}</code>${e.on_venv ? "" :
       `, which is not the project's <code>.venv</code>`}.
       Either restart it with <code>run_hub.bat</code>, or use the install
       button below — that installs into the interpreter this hub is actually using.`;
    warn.style.display = show ? "" : "none";
  }
  const note = document.getElementById("dev-env-note");
  if(note) note.textContent = e.fqbn;
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
    : `<option value="">No serial ports found</option>`;

  document.getElementById("dev-conn").innerHTML = `
    <label class="dev-sel">Port <select data-dev="port" ${connected?"disabled":""}>${opts}</select></label>
    ${devBtn("refreshports","Refresh")}
    ${connected
      ? devBtn("disconnect","Disconnect", I.stop, "btn-danger")
      : devBtn("connect","Connect", I.play, "btn-primary")}
    ${devPill(connected?"ok":"warn","Serial", connected ? (st.port || "connected") : "Disconnected")}`;

  // Restore the port: what the board reports, else the user's pick, else the
  // one that looks like an Arduino.
  const sel = document.querySelector('[data-dev="port"]');
  if(sel){
    const want = (st && st.port) || dev.port ||
                 (ports.find(p=>p.is_glove) || {}).port;
    if(want && [...sel.options].some(o=>o.value === want)) sel.value = want;
    dev.port = sel.value;
  }
  const cbtn = document.querySelector('[data-dev="connect"]');
  if(cbtn && (!e || !e.pyserial)){
    cbtn.disabled = true;
    cbtn.title = "Install pyserial first — use the button above.";
  }
}

function devRenderBanner(){
  const b = dev.status && dev.status.banner;
  const el = document.getElementById("dev-banner");
  if(!b){ el.innerHTML = `<div class="dev-banner-empty">No banner yet — connect and the board announces its firmware, rate and column layout.</div>`; return; }
  const rows = [
    ["Firmware", b.fw], ["Protocol", b.proto + (b.supported ? " (supported)" : " (UNSUPPORTED)")],
    ["Board", b.board], ["Rate", b.rate + " Hz"],
    ["ADC", b.adc_bits + "-bit @ " + b.adc_ref_mv + " mV"],
    ["Divider", b.vdiv_mv + " mV / " + b.r_fixed + " Ω"],
    ["IMU", b.imu], ["Channels", b.channels.join(", ") || "—"],
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
    el.innerHTML = `<div class="dev-banner-empty">No channels yet.</div>`;
    return;
  }
  el.innerHTML = dev.channels.map((name,i) => `
    <div class="dev-chan">
      <div class="dev-chan-head">
        <label class="dev-check"><input type="checkbox" data-dev="chan" data-i="${i}"
          ${dev.selected.has(i)?"checked":""}> <i class="dev-swatch" style="background:${DEV_SERIES[i % DEV_MAX_SERIES]}"></i>${name}</label>
        <span class="dev-chan-kind">${devKind(i)}</span>
      </div>
      <div class="dev-chan-val" id="dev-force-${i}">&#8212;</div>
      <div class="dev-chan-sub" id="dev-gram-${i}">&#8212;</div>
      <div id="dev-badge-${i}"></div>
      <div class="dev-chan-raw" id="dev-raw-${i}">&#8212;</div>
      <div class="dev-chan-span" id="dev-span-${i}">peak &#8212;</div>
    </div>`).join("");
}

function devRenderChannelValues(){
  const b = dev.status && dev.status.banner;
  for(let i=0;i<dev.channels.length;i++){
    const buf = dev.series[i];
    if(!buf || !buf.length) continue;
    const kind = devKind(i);
    const rf = devRFixed(i);
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
      if(bd) bd.innerHTML = `<span class="dev-badge dev-badge-dim">unknown sensor — raw only</span>`;
    }
    set("dev-raw-", `${v} adc · ${devOhmText(ohm)} · ${us === null ? "—" : us.toFixed(0)+" µS"}`);

    // Peak latches from the extreme ADC already tracked for the span — the
    // number that matters for a grip, a tap, or a full finger curl. Peak is
    // always taken from RAW counts, never the smoothed value: smoothing is a
    // display aid and must not quietly lower a recorded maximum.
    const s = dev.span[i];
    const sp = document.getElementById("dev-span-"+i);
    if(sp){
      if(s.max === null || s.min === null) sp.textContent = "peak —";
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
        sp.textContent = `peak ${peak}  ·  adc span ${s.min}–${s.max}`
          + ` of ${b ? (1<<b.adc_bits)-1 : 1023}`;
      }
    }
  }
}

function devRenderHealth(){
  const s = dev.status; if(!s) return;
  const rate = s.rate_hz ? s.rate_hz.toFixed(2) + " Hz" : "—";
  const target = s.banner ? s.banner.rate : 0;
  const rateOk = target ? Math.abs(s.rate_hz - target) < target*0.05 : false;
  document.getElementById("dev-health").innerHTML =
    `<div class="dev-stat"><div class="dev-stat-n ${rateOk?"good":""}">${rate}</div><div class="dev-stat-l">Measured rate${target?` (target ${target})`:""}</div></div>
     <div class="dev-stat"><div class="dev-stat-n ${s.dropped?"bad":"good"}">${s.dropped}</div><div class="dev-stat-l">Dropped frames</div></div>
     <div class="dev-stat"><div class="dev-stat-n">${s.total}</div><div class="dev-stat-l">Frames received</div></div>
     <div class="dev-stat"><div class="dev-stat-n">${s.uptime_s ? s.uptime_s.toFixed(0)+" s" : "—"}</div><div class="dev-stat-l">Connected for</div></div>
     <div class="dev-stat"><div class="dev-stat-n">${s.recording ? s.record_rows : "off"}</div><div class="dev-stat-l">${s.recording ? "Rows recorded — "+s.record_path : "Recording"}</div></div>`;

  const rec = document.querySelector('[data-dev="rec"]');
  if(rec) rec.textContent = s.recording ? "Stop Recording" : "Start Recording";
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
    }[dev.unit] || (v => v);
  };
  const fixedRange = {
    adc:   [0, adcMax],
    force: [0, fm ? fm.rated_max_n : 20],   // default to the part's rated band
    bend:  [0, 100],
    ohm:   [0, (b ? b.r_fixed : 10000) * 3],
    us:    [0, 2000],
  }[dev.unit] || [0, adcMax];
  const label = {adc:"", ohm:" Ω", us:" µS", force:" N", bend:" %"}[dev.unit] || "";

  // Newtons and bend-percent cannot share a y-axis without being misleading,
  // so a kind-specific unit draws only the channels it applies to. The
  // kind-neutral units (adc/ohm/us) still draw everything.
  const unitKind = {force:"fsr", bend:"flex"}[dev.unit] || null;
  const drawable = sel.filter(i => !unitKind || devKind(i) === unitKind);

  const traces = drawable.map(i => devSmoothSeries(
    (dev.series[i] || []).slice(-n).map(convFor(i))));

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
  g.fillStyle = "#64748B"; g.font = "11px 'JetBrains Mono', monospace";
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
  g.fillText("now", pad.l+pw-14, pad.t+ph+5);

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

  // A blank plot must say why it is blank. Silently drawing nothing is
  // indistinguishable from a dead sensor, which is exactly the confusion this
  // page exists to remove.
  g.fillStyle = "#64748B"; g.font = "11px 'JetBrains Mono', monospace";
  g.textAlign = "left"; g.textBaseline = "top";
  if(!drawable.length && unitKind){
    const kindWord = unitKind === "flex" ? "bend" : "force";
    const anyOfKind = dev.channels.some((_,i) => devKind(i) === unitKind);
    const msg = !dev.channels.length
      ? "no channels yet — connect the board"
      : !anyOfKind
        ? `no ${kindWord} sensor on this board — check the banner's chan= field`
        : `no ${kindWord} channel selected — tick one in the tiles below`;
    g.fillText(msg, pad.l + 6, pad.t + 6);
  } else {
    const hidden = sel.length - drawable.length;
    if(hidden > 0){
      g.fillText(`${hidden} channel${hidden>1?"s":""} hidden — not a ${unitKind === "flex" ? "bend" : "force"} sensor`,
                 pad.l + 6, pad.t + 6);
    }
    // On an observed span, say so on the plot too — the y-axis reads 0-100%
    // and that is 100% of what has been SEEN, not of the sensor's travel.
    if(dev.unit === "bend" && drawable.length){
      const sp = devFlexSpan(drawable[0]);
      if(sp && sp.basis !== "calibrated"){
        g.textAlign = "right";
        g.fillText(sp.basis === "observed" ? "% of observed range" : "provisional range",
                   pad.l + pw - 6, pad.t + 6);
      }
    }
  }
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
  if(!dev.fastTimer){
    dev.fastTimer = setInterval(()=>{
      devPollSamples();
      // Under reduced motion the scope refreshes on the poll tick instead of
      // running a continuous animation frame loop.
      if(reducedMotion) devDraw();
    }, DEV_POLL_MS);
  }
  if(!dev.envTimer) dev.envTimer = setInterval(devPollStatus, DEV_ENV_MS);
  if(!reducedMotion && !dev.raf) dev.raf = requestAnimationFrame(devLoop);
}

function stopDev(){
  clearInterval(dev.fastTimer); dev.fastTimer = null;
  clearInterval(dev.envTimer);  dev.envTimer = null;
  if(dev.raf){ cancelAnimationFrame(dev.raf); dev.raf = null; }
}

window.startDev = startDev;
window.stopDev = stopDev;
