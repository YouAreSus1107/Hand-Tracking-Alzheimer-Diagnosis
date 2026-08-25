/* Participant flow — arrival → consent → camera → framing → calibrate →
   practice → trial → result → upload.  REMOTE_SESSION_PLAN.md §2, and the
   elder-first rules in WEB_PLATFORM_PLAN.md §5.

   Every scored number comes from engine.js, which is a checked port of the
   Python engine (see tests/parity.mjs). Nothing in this file computes a
   metric of its own. */

import { FilesetResolver, HandLandmarker } from
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
import {
  Calibrator, MODES, TapDetector, computeMetrics, minIntertapS, thumbIndexDistance,
} from "./engine.js";
import * as cloud from "./cloud.js";

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

const MODE = MODES.big_and_fast;
const EMA_ALPHA = 0.4;

// The data-quality gate (§7, "bad data is worse than no data"). Nobody is in
// the room to override it, so it refuses rather than reports a soft number.
const MIN_FPS = 15;
const FRAMING_FRAMES = 20;      // consecutive good frames before Start unlocks
const MIN_VISIBLE_RATIO = 0.8;

const $ = (id) => document.getElementById(id);
const state = {
  token: null, invite: null, screen: "s-boot",
  stream: null, landmarker: null,
  dClosed: 0, dOpen: 1,
  fps: 0, session: null,
};

/* ── Screens, speech, text size ────────────────────────────────────────── */

function show(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === id));
  state.screen = id;
  window.scrollTo(0, 0);
  const line = document.querySelector(`#${id} [data-say]`);
  if (line) say(line.textContent);
}

let sayOn = false;
function say(text) {
  if (!sayOn || !window.speechSynthesis || !text) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/\s+/g, " ").trim());
    u.lang = (state.invite && state.invite.lang === "zh") ? "zh-TW" : "en-US";
    u.rate = 0.92;
    speechSynthesis.speak(u);
  } catch (e) { /* speech is a convenience, never a dependency */ }
}

$("btn-say").addEventListener("click", (e) => {
  sayOn = !sayOn;
  e.currentTarget.setAttribute("aria-pressed", String(sayOn));
  if (sayOn) {
    const line = document.querySelector(`#${state.screen} [data-say]`);
    if (line) say(line.textContent);
  } else if (window.speechSynthesis) {
    speechSynthesis.cancel();
  }
});

let scale = 1;
$("btn-bigger").addEventListener("click", () => {
  scale = scale >= 1.4 ? 1 : scale + 0.2;
  document.documentElement.style.setProperty("--scale", String(scale));
});

$("btn-stop").addEventListener("click", () => {
  stopCamera();
  location.reload();
});

function blocked(title, body, hint) {
  $("blocked-title").textContent = title;
  $("blocked-body").textContent = body;
  $("blocked-hint").innerHTML = hint || "";
  $("blocked-hint").style.display = hint ? "" : "none";
  show("s-blocked");
}

/* ── Browser sniffing, only where it changes the instructions (§5.2/§5.3) ── */

function browserInfo() {
  const ua = navigator.userAgent;
  const inApp = /FBAN|FBAV|Instagram|Line\//.test(ua) ||
                (/MicroMessenger/.test(ua)) || /\bTwitter/.test(ua);
  const ios = /iPad|iPhone|iPod/.test(ua) ||
              (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const app = /MicroMessenger/.test(ua) ? "WeChat"
            : /Line\//.test(ua) ? "LINE"
            : /Instagram/.test(ua) ? "Instagram"
            : /FBAN|FBAV/.test(ua) ? "Facebook" : "this app";
  return { ua, inApp, ios, app };
}

const B = browserInfo();

function permissionCopy() {
  return B.ios
    ? "The question appears at the <b>top of the screen</b>. Tap <b>Allow</b>."
    : "The question appears near the <b>top of the screen</b>. Tap <b>Allow</b> or <b>While using the app</b>.";
}

function recoverySteps() {
  return B.ios
    ? ["Open the <b>Settings</b> app on your phone.",
       "Scroll down and tap <b>Safari</b>.",
       "Tap <b>Camera</b>, then choose <b>Ask</b> or <b>Allow</b>.",
       "Come back here and tap the button below."]
    : ["Tap the <b>lock</b> or <b>sliders</b> icon next to the web address at the top.",
       "Tap <b>Permissions</b>, then <b>Camera</b>.",
       "Choose <b>Allow</b>.",
       "Come back here and tap the button below."];
}

/* ── Boot ──────────────────────────────────────────────────────────────── */

async function boot() {
  // §5.3: a link from a family member usually arrives inside a chat app, where
  // getUserMedia is restricted. This is the expected path, not an edge case.
  if (B.inApp) {
    blocked("Please open this in your browser",
      `Camera tests do not work inside ${B.app}.`,
      `<p>Tap the <b>&#8943;</b> or <b>&#8942;</b> menu in the corner of this screen, then choose
       <b>Open in ${B.ios ? "Safari" : "Chrome"}</b>.</p>`);
    return;
  }

  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    blocked("This phone cannot run the test",
      "The camera is not available in this browser.",
      "<p>Please try again in Safari or Chrome.</p>");
    return;
  }

  const m = location.pathname.match(/\/s\/([A-Za-z0-9_-]{20,64})/);
  state.token = m ? m[1] : new URLSearchParams(location.search).get("t");
  if (!state.token) {
    blocked("This link is incomplete",
      "The web address is missing its last part.",
      "<p>Please ask for the link again, and open it by tapping it rather than typing it.</p>");
    return;
  }

  // Anything parked from a previous visit goes first, before a new test.
  cloud.flushParked().catch(() => {});

  let invite;
  try {
    invite = await cloud.fetchInvite(state.token);
  } catch (err) {
    if (err.message === "NO_FIREBASE_KEY") {
      blocked("Not quite ready yet",
        "This link is not switched on at the other end.",
        "<p>Please let the person who sent it know. (The page was published without its Firebase web config.)</p>");
      return;
    }
    if (err.message === "ANON_AUTH_DISABLED") {
      blocked("Not quite ready yet",
        "This link is not switched on at the other end.",
        "<p>Please let the person who sent it know. (Anonymous sign-in is not enabled for this project.)</p>");
      return;
    }
    blocked("We could not check this link",
      "Something went wrong reaching the internet.",
      "<p>Check your connection and open the link again.</p>");
    return;
  }

  const refusal = inviteRefusal(invite);
  if (refusal) {
    blocked("This link cannot be used", refusal,
      "<p>Ask the person who sent it for a new one.</p>");
    return;
  }
  state.invite = invite;

  const helper = invite.helper || "the person who invited you";
  $("welcome-title").textContent = invite.participant ? `Hello, ${invite.participant}` : "Hello";
  $("welcome-lead").textContent =
    `${helper} has asked you to do a short finger-tapping check.`;
  $("welcome-helper").textContent = helper;
  $("camera-where").innerHTML = permissionCopy();
  $("denied-steps").innerHTML = recoverySteps().map((s) => `<li>${s}</li>`).join("");
  show("s-welcome");
}

/** Mirrors core/remote/invites.refusal() — same states, same wording. */
function inviteRefusal(invite) {
  if (!invite) return "That link is not valid.";
  if (invite.revoked) return "That link was cancelled.";
  const expires = Date.parse(invite.expires_at);
  if (!Number.isNaN(expires) && Date.now() >= expires) {
    return "That link has expired. Ask for a new one.";
  }
  if (Number(invite.uses_left || 0) <= 0) return "That link has already been used.";
  return null;
}

/* ── Camera + MediaPipe ────────────────────────────────────────────────── */

$("btn-consent").addEventListener("click", () => show("s-camera"));
$("btn-camera").addEventListener("click", startCamera);
$("btn-retry-camera").addEventListener("click", startCamera);

async function startCamera() {
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
  } catch (err) {
    if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) {
      show("s-denied");
    } else {
      blocked("We cannot reach the camera",
        "Another app may be using it.",
        "<p>Close your other apps, then open this link again.</p>");
    }
    return;
  }

  show("s-setup");
  attach($("video"));
  try {
    const files = await FilesetResolver.forVisionTasks(WASM);
    state.landmarker = await HandLandmarker.createFromOptions(files, {
      baseOptions: { modelAssetPath: MODEL, delegate: "GPU" },
      runningMode: "VIDEO",
      numHands: 1,
    });
  } catch (err) {
    blocked("We could not start the test",
      "The hand-tracking part did not load.",
      "<p>Check your internet connection and open the link again.</p>");
    return;
  }
  runFraming();
}

function attach(video) {
  if (video.srcObject !== state.stream) video.srcObject = state.stream;
  video.play().catch(() => {});
}

function stopCamera() {
  if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
  state.stream = null;
}

/** One landmark read for the current frame, plus a rolling fps estimate. */
function makeLoop(video, canvas, onFrame) {
  const ctx = canvas.getContext("2d");
  let stopped = false;
  let last = performance.now();
  let fpsEma = 0;

  const tick = () => {
    if (stopped) return;
    const now = performance.now();
    const dt = now - last;
    last = now;
    if (dt > 0) fpsEma = fpsEma ? 0.9 * fpsEma + 0.1 * (1000 / dt) : 1000 / dt;
    state.fps = fpsEma;

    let landmarks = null;
    if (video.readyState >= 2 && state.landmarker) {
      if (canvas.width !== video.videoWidth) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
      }
      const res = state.landmarker.detectForVideo(video, now);
      landmarks = (res.landmarks && res.landmarks[0]) || null;
      draw(ctx, canvas, landmarks);
    }
    onFrame(now / 1000, landmarks);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return () => { stopped = true; };
}

const LINKS = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[0,9],[9,10],[10,11],[11,12],
               [0,13],[13,14],[14,15],[15,16],[0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]];

function draw(ctx, canvas, lm) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!lm) return;
  const X = (p) => p.x * canvas.width, Y = (p) => p.y * canvas.height;
  ctx.strokeStyle = "rgba(18,165,148,.85)";
  ctx.lineWidth = Math.max(2, canvas.width / 200);
  ctx.beginPath();
  for (const [a, b] of LINKS) { ctx.moveTo(X(lm[a]), Y(lm[a])); ctx.lineTo(X(lm[b]), Y(lm[b])); }
  ctx.stroke();
  // Thumb and index tips carry the signal, so they get the emphasis.
  ctx.fillStyle = "#F8FAFC";
  for (const i of [4, 8]) {
    ctx.beginPath();
    ctx.arc(X(lm[i]), Y(lm[i]), Math.max(5, canvas.width / 90), 0, Math.PI * 2);
    ctx.fill();
  }
}

/* ── Framing gate ──────────────────────────────────────────────────────── */

let stopLoop = null;

function runFraming() {
  const box = $("framing"), stage = $("video").parentElement;
  let good = 0;
  stopLoop = makeLoop($("video"), $("overlay"), (t, lm) => {
    let msg = "Hold your hand up, so the camera can see it.";
    let ok = false;
    if (lm) {
      const span = Math.hypot(lm[0].x - lm[9].x, lm[0].y - lm[9].y);
      if (span < 0.10) msg = "Come a little closer.";
      else if (span > 0.32) msg = "Move back a little.";
      else if (state.fps < MIN_FPS) msg = "Close your other apps &mdash; this phone is busy.";
      else { msg = "That's it &mdash; hold still."; ok = true; }
    }
    good = ok ? good + 1 : 0;
    box.innerHTML = msg;
    box.classList.toggle("good", ok);
    stage.classList.toggle("good", ok);
    $("btn-setup").disabled = good < FRAMING_FRAMES;
  });
}

$("btn-setup").addEventListener("click", () => {
  stopLoop?.();
  show("s-calibrate");
  attach($("video-cal"));
  runCalibration();
});

/* ── Calibration ───────────────────────────────────────────────────────── */

function runCalibration() {
  const cal = new Calibrator();
  let t0 = null;
  stopLoop = makeLoop($("video-cal"), $("overlay-cal"), (t, lm) => {
    if (t0 === null) t0 = t;
    const d = lm ? thumbIndexDistance(lm) : null;
    if (d !== null && d !== undefined) cal.update(t, d);
    $("cal-fill").style.width = `${Math.round(cal.progress * 100)}%`;
    $("cal-status").textContent = cal.cycles < 1
      ? "Touch them together…" : `Good — ${cal.cycles} of 2`;

    if (cal.done) {
      const [dc, dOpen] = cal.result();
      state.dClosed = dc;
      state.dOpen = dOpen;
      stopLoop?.();
      show("s-practice");
      attach($("video-practice"));
      runPractice();
    } else if (cal.timedOut(t)) {
      stopLoop?.();
      $("nogood-why").textContent =
        "We could not see your hand opening and closing clearly. Let's try once more, a little slower.";
      show("s-nogood");
    }
  });
}

/* ── Practice (unscored, repeatable) ───────────────────────────────────── */

function runPractice() {
  const det = new TapDetector(minIntertapS(MODE), EMA_ALPHA, state.dClosed, state.dOpen);
  const countEl = $("practice-count");
  countEl.textContent = "0";
  stopLoop = makeLoop($("video-practice"), $("overlay-practice"), (t, lm) => {
    const d = lm ? thumbIndexDistance(lm) : null;
    if (det.update(t, d)) {
      countEl.textContent = String(det.tapTimes.length);
      countEl.classList.remove("pulse");
      void countEl.offsetWidth;
      countEl.classList.add("pulse");
      $("practice-feedback").textContent = "That's a tap — good.";
    }
  });
}

$("btn-practice-again").addEventListener("click", () => {
  stopLoop?.();
  runPractice();
});

$("btn-practice-done").addEventListener("click", () => {
  stopLoop?.();
  show("s-trial");
  attach($("video-trial"));
  runTrial();
});

/* ── The scored trial ──────────────────────────────────────────────────── */

async function runTrial() {
  const cd = $("trial-countdown");
  cd.classList.add("show");
  for (const n of ["3", "2", "1", "Go"]) {
    cd.textContent = n;
    say(n);
    await new Promise((r) => setTimeout(r, 700));
  }
  cd.classList.remove("show");

  const det = new TapDetector(minIntertapS(MODE), EMA_ALPHA, state.dClosed, state.dOpen);
  const countEl = $("trial-count");
  countEl.textContent = "0";
  $("trial-title").textContent = "Go!";

  let t0 = null, frames = 0, seen = 0;
  stopLoop = makeLoop($("video-trial"), $("overlay-trial"), (t, lm) => {
    if (t0 === null) t0 = t;
    frames += 1;
    if (lm) seen += 1;
    const d = lm ? thumbIndexDistance(lm) : null;
    if (det.update(t, d)) {
      countEl.textContent = String(det.tapTimes.length);
      countEl.classList.remove("pulse");
      void countEl.offsetWidth;
      countEl.classList.add("pulse");
    }
    const elapsed = t - t0;
    $("trial-bar").style.width = `${Math.min(100, (elapsed / MODE.duration_s) * 100)}%`;

    if (elapsed >= MODE.duration_s) {
      stopLoop?.();
      finish(det, t0, t, frames ? seen / frames : 0);
    }
  });
}

function finish(det, tStart, tEnd, visibleRatio) {
  stopCamera();
  $("trial-title").textContent = "Get ready";

  // The gate the plan insists on: too few frames, or a hand out of view, and
  // we say so rather than publish a number we do not trust.
  if (state.fps < MIN_FPS || visibleRatio < MIN_VISIBLE_RATIO) {
    $("nogood-why").textContent = state.fps < MIN_FPS
      ? "This phone was working too hard to measure accurately. Close your other apps and try again."
      : "Your hand went out of view during the test. Let's try again with the phone a little further away.";
    show("s-nogood");
    return;
  }

  const m = computeMetrics(MODE, det.tapTimes, det.series, tStart, tEnd, null, visibleRatio, state.fps, det.nearMiss);
  if (!m.scoreable) {
    $("nogood-why").textContent = m.reason || "We could not score that attempt.";
    show("s-nogood");
    return;
  }

  // The record the hub expects (core/session.py schema, §4: metrics only).
  state.session = {
    session_id: uuid(),
    timestamp: new Date().toISOString(),
    test: state.invite.session_test || "finger_tapping",
    mode: state.invite.mode || MODE.key,
    hand: null,
    duration_s: Number((tEnd - tStart).toFixed(2)),
    participant: state.invite.participant || "",
    device: {
      ua: navigator.userAgent.slice(0, 200),
      platform: B.ios ? "ios" : "other",
      fps_sustained: Number(state.fps.toFixed(1)),
      app_version: "participant-prototype-1",
    },
    metrics: {
      scoreable: true,
      taps: m.taps,
      frequency_hz: m.frequency_hz,
      mean_iti_ms: m.mean_iti_ms,
      iiv_ms: m.iiv_ms,
      cv_pct: m.cv_pct,
      amplitude_cv_pct: m.amplitude_cv_pct,
      decrement_pct_per_s: m.decrement_pct_per_s,
      n_intervals: m.n_intervals,
      cv_ci_low_pct: m.cv_ci_low_pct,
      cv_ci_high_pct: m.cv_ci_high_pct,
      confidence_pct: m.confidence_pct,
      band_edge: m.band_edge,
      taps_w10: m.taps_w10,
      frequency_hz_w10: m.frequency_hz_w10,
      cv_pct_w10: m.cv_pct_w10,
      near_miss_taps: m.near_miss_taps,
    },
  };

  renderResult(m);
  send();
}

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/* ── Result and upload ─────────────────────────────────────────────────── */

// §5.8: a plain sentence first, the number second, and never a verdict word.
const PLAIN = {
  success: "Your tapping rhythm was steady today.",
  warning: "Your tapping rhythm varied a little today.",
  danger: "Your tapping rhythm varied more than usual today.",
};

function renderResult(m) {
  $("result-plain").textContent = PLAIN[m.status] || "Thank you — that's done.";
  $("result-metric").innerHTML =
    `<div class="big">${m.taps}</div><div class="unit">taps in ${MODE.duration_s} seconds</div>` +
    `<div class="band ${m.status}">Steadiness: ${m.cv_pct.toFixed(1)}% variation</div>` +
    `<div class="unit">95% CI ${m.cv_ci_low_pct.toFixed(1)}-${m.cv_ci_high_pct.toFixed(1)}% · ` +
    `${m.confidence_pct >= 75 ? "high" : m.confidence_pct >= 45 ? "moderate" : "low"} confidence</div>`;
  show("s-result");
}

async function send() {
  const who = state.invite.helper || "the person who invited you";
  $("result-sent").textContent = "Sending your result…";
  cloud.park(state.token, state.invite, state.session);
  try {
    await cloud.uploadResult(state.token, state.invite, state.session);
    cloud.clearPark();
    $("result-sent").textContent = `Saved and sent to ${who}.`;
    $("result-retry").hidden = true;
  } catch (err) {
    $("result-sent").textContent = "";
    $("result-retry").hidden = false;
  }
}

$("btn-resend").addEventListener("click", send);
window.addEventListener("online", () => { cloud.flushParked().catch(() => {}); });

$("btn-again").addEventListener("click", () => location.reload());

boot();
