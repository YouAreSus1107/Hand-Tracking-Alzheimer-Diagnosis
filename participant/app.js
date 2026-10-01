/* Participant flow — arrival → consent → hand → camera → framing →
   calibrate → practice → trial → thank-you → upload.  REMOTE_SESSION_PLAN.md
   §2, and the elder-first rules in WEB_PLATFORM_PLAN.md §5.

   Every scored number comes from engine.js, which is a checked port of the
   Python engine (see tests/parity.mjs). Nothing in this file computes a
   metric of its own.

   Every user-facing string goes through t() with its English as the key
   (i18n.js); tests/i18n_check.mjs fails on one with no Chinese entry, and on
   a t() given anything but a plain string literal, which it could not see. */

import { FilesetResolver, HandLandmarker } from
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
import {
  CLIPPED, Calibrator, FramingMonitor, LOST, MODES, NEAR, PRE_ROLL_S, TapDetector,
  computeMetrics, edgeState, emaAlpha, hint, makeLandmarkFilters, minIntertapS,
  smoothLandmarks, thumbIndexDistance,
} from "./engine.js";
import * as cloud from "./cloud.js";
import { applyStatic, getLang, setLang, t, translate } from "./i18n.js";

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

const MODE = MODES.big_and_fast;
const EMA_ALPHA = emaAlpha(MODE);
// After a framing pause, taps this soon after resuming are not trusted: the
// detector's state is from before the pause (finger_tapping.RESUME_GUARD_S).
const RESUME_GUARD_S = 0.25;
// Nobody is in the room to end a run that is stuck paused, so the page does.
const MAX_PAUSED_S = 20;
const APP_VERSION = "participant-0.3";

// The data-quality gate (§7, "bad data is worse than no data"). Nobody is in
// the room to override it, so it refuses rather than reports a soft number.
const MIN_FPS = 15;
const FRAMING_FRAMES = 20;      // consecutive good frames before Start unlocks
const MIN_VISIBLE_RATIO = 0.8;
// Practice unlocks the real test only after this many counted taps, so
// "I'm ready" is never pressed before the movement has been tried at all.
const MIN_PRACTICE_TAPS = 5;

const CAMERA_SCREENS = new Set(["s-setup", "s-calibrate", "s-practice", "s-trial"]);

const $ = (id) => document.getElementById(id);
const state = {
  token: null, invite: null, screen: "s-boot",
  stream: null, landmarker: null, loading: null,
  dClosed: 0, dOpen: 1,
  fps: 0, session: null,
  hand: null,                 // what the participant said they tap with
  handVotes: {},              // MediaPipe's label, counted over the trial
  delegate: null, frameW: 0, frameH: 0,
  retry: null,                // the step "Try again" returns to
};

/** Names from the invite go into markup; never trust them to be plain. */
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function helperName() {
  return state.invite && state.invite.helper
    ? state.invite.helper : t("the person who invited you");
}

/* ── Screens, speech, text size ────────────────────────────────────────── */

function show(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === id));
  state.screen = id;
  window.scrollTo(0, 0);
  checkUpright();
  const line = document.querySelector(`#${id} [data-say]`);
  if (line) say(line.textContent);
}

let sayOn = false;
function say(text) {
  if (!sayOn || !window.speechSynthesis || !text) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/\s+/g, " ").trim());
    u.lang = getLang() === "zh" ? "zh-TW" : "en-US";
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

/* "Start over" is always there (§5.6), and it must not cost the participant
   the link check, the consent and the camera prompt again: a reload did all
   three, and iOS often asks for the camera afresh. It returns to setting the
   phone up if the camera was reached, else to the welcome. A reload remains
   only for a page that never got past checking its link. */
$("btn-stop").addEventListener("click", () => {
  stopLoop?.();
  $("trial-paused").hidden = true;
  if (!state.invite) { location.reload(); return; }
  if (state.stream || CAMERA_SCREENS.has(state.screen) || state.screen === "s-nogood") {
    toSetup();
  } else {
    welcome(state.invite);
  }
});

/** A dead end with its next action. `action` = {label, run} puts that action
 *  on a button, for the cases the page can recover from by itself. */
function blocked(title, body, hintHtml, action) {
  $("blocked-title").textContent = title;
  $("blocked-body").textContent = body;
  $("blocked-hint").innerHTML = hintHtml || "";
  $("blocked-hint").style.display = hintHtml ? "" : "none";
  const btn = $("blocked-action");
  btn.hidden = !action;
  if (action) {
    btn.textContent = action.label;
    btn.onclick = action.run;
  }
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
            : /FBAN|FBAV/.test(ua) ? "Facebook" : "";
  return { ua, inApp, ios, app };
}

const B = browserInfo();

function permissionCopy() {
  return B.ios
    ? t("The question appears at the <b>top of the screen</b>. Tap <b>Allow</b>.")
    : t("The question appears near the <b>top of the screen</b>. Tap <b>Allow</b> or <b>While using the app</b>.");
}

function recoverySteps() {
  return B.ios
    ? [t("Open the <b>Settings</b> app on your phone."),
       t("Scroll down and tap <b>Safari</b>."),
       t("Tap <b>Camera</b>, then choose <b>Ask</b> or <b>Allow</b>."),
       t("Come back here and tap the button below.")]
    : [t("Tap the <b>lock</b> or <b>sliders</b> icon next to the web address at the top."),
       t("Tap <b>Permissions</b>, then <b>Camera</b>."),
       t("Choose <b>Allow</b>."),
       t("Come back here and tap the button below.")];
}

/* ── Boot ──────────────────────────────────────────────────────────────── */

async function boot() {
  // Until the invite says otherwise, follow the phone's own language, so the
  // screens before the link is checked (and the dead ends) are readable too.
  setLang(/^zh\b/i.test(navigator.language || "") ? "zh" : "en");

  // §5.3: a link from a family member usually arrives inside a chat app, where
  // getUserMedia is restricted. This is the expected path, not an edge case.
  if (B.inApp) {
    blocked(t("Please open this in your browser"),
      B.app ? t("Camera tests do not work inside {app}.", { app: B.app })
            : t("Camera tests do not work inside this app."),
      `<p>${B.ios
        ? t("Tap the <b>&#8943;</b> or <b>&#8942;</b> menu in the corner of this screen, then choose <b>Open in Safari</b>.")
        : t("Tap the <b>&#8943;</b> or <b>&#8942;</b> menu in the corner of this screen, then choose <b>Open in Chrome</b>.")}</p>`);
    return;
  }

  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    blocked(t("This phone cannot run the test"),
      t("The camera is not available in this browser."),
      `<p>${t("Please try again in Safari or Chrome.")}</p>`);
    return;
  }

  const m = location.pathname.match(/\/s\/([A-Za-z0-9_-]{20,64})/);
  state.token = m ? m[1] : new URLSearchParams(location.search).get("t");
  if (!state.token) {
    blocked(t("This link is incomplete"),
      t("The web address is missing its last part."),
      `<p>${t("Please ask for the link again, and open it by tapping it rather than typing it.")}</p>`);
    return;
  }

  // Anything parked from a previous visit goes first, before a new test.
  cloud.flushParked().catch(() => {});

  let invite;
  try {
    invite = await cloud.fetchInvite(state.token);
  } catch (err) {
    if (err.message === "NO_FIREBASE_KEY" || err.message === "ANON_AUTH_DISABLED") {
      // The second line is for whoever set the page up, so it stays English.
      blocked(t("Not quite ready yet"),
        t("This link is not switched on at the other end."),
        `<p>${t("Please let the person who sent it know.")}</p>` +
        `<p class="fine">${err.message === "NO_FIREBASE_KEY"
          ? "The page was published without its Firebase web config."
          : "Anonymous sign-in is not enabled for this project."}</p>`);
      return;
    }
    blocked(t("We could not check this link"),
      t("Something went wrong reaching the internet."),
      `<p>${t("Check your connection, then try again.")}</p>`,
      { label: t("Try again"), run: () => { show("s-boot"); boot(); } });
    return;
  }

  // The helper chose the language when making the link; that wins.
  if (invite && invite.lang) setLang(invite.lang);

  const refusal = inviteRefusal(invite);
  if (refusal) {
    blocked(t("This link cannot be used"), refusal,
      `<p>${t("Ask the person who sent it for a new one.")}</p>`);
    return;
  }
  // Only what engine.js can score. The hub no longer mints anything else
  // (core/remote/invites.py remote_modes), but an older link may still say
  // spiral or paced, and running tapping under that name would file tapping
  // numbers in the wrong history.
  if (!supported(invite)) {
    blocked(t("This test is not ready yet"),
      t("This link is for a test that cannot be done on a phone yet."),
      `<p>${t("Please let the person who sent it know.")}</p>`);
    return;
  }
  state.invite = invite;

  // Already done on this phone: say so, rather than start the test again.
  // Another go is offered only while the link still has uses to spend.
  const done = cloud.doneCount(state.token);
  if (done > 0) {
    $("done-lead").textContent =
      t("You have already done this check. Your result was saved for {name}.", { name: helperName() });
    $("btn-done-again").hidden = done >= Number(invite.uses_left || 0);
    show("s-done");
    return;
  }
  welcome(invite);
}

function welcome(invite) {
  // Start fetching the hand model now, while the welcome is being read, so
  // the camera screen is not a silent wait on ~8 MB over mobile data.
  landmarkerReady().catch(() => { /* reported by toSetup() when it matters */ });
  const helper = helperName();
  $("welcome-title").textContent = invite.participant
    ? t("Hello, {name}", { name: invite.participant }) : t("Hello");
  $("welcome-lead").textContent =
    t("{name} has asked you to do a short finger-tapping check.", { name: helper });
  $("welcome-helper").innerHTML =
    t("Only the measurements are sent, and only to <b>{name}</b>.", { name: esc(helper) });
  $("camera-where").innerHTML = permissionCopy();
  $("denied-steps").innerHTML = recoverySteps().map((s) => `<li>${s}</li>`).join("");
  show("s-welcome");
}

$("btn-done-again").addEventListener("click", () => welcome(state.invite));

/** The invite names a test and mode this page runs. */
function supported(invite) {
  return (invite.session_test || "finger_tapping") === "finger_tapping" &&
         Object.prototype.hasOwnProperty.call(MODES, invite.mode || "");
}

/** Mirrors core/remote/invites.refusal() — same states, same wording. */
function inviteRefusal(invite) {
  if (!invite) return t("That link is not valid.");
  if (invite.revoked) return t("That link was cancelled.");
  const expires = Date.parse(invite.expires_at);
  if (!Number.isNaN(expires) && Date.now() >= expires) {
    return t("That link has expired. Ask for a new one.");
  }
  if (Number(invite.uses_left || 0) <= 0) return t("That link has already been used.");
  return null;
}

/* ── Camera + MediaPipe ────────────────────────────────────────────────── */

$("btn-consent").addEventListener("click", () => show("s-hand"));
for (const side of ["left", "right"]) {
  $(`btn-hand-${side}`).addEventListener("click", () => {
    state.hand = side;
    show("s-camera");
  });
}
$("btn-camera").addEventListener("click", toSetup);
$("btn-retry-camera").addEventListener("click", toSetup);

/** The hand model, loaded once. Started from the welcome screen; awaited by
 *  the setup screen. A failure clears the promise so a retry really retries. */
function landmarkerReady() {
  if (!state.loading) {
    state.loading = loadLandmarker().catch((err) => {
      state.loading = null;
      throw err;
    });
  }
  return state.loading;
}

async function loadLandmarker() {
  const files = await FilesetResolver.forVisionTasks(WASM);
  // Some phones advertise WebGL but fail to build the GPU graph; the CPU
  // path is slower but works everywhere, and the fps gate judges the result.
  for (const delegate of ["GPU", "CPU"]) {
    try {
      state.landmarker = await HandLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: MODEL, delegate },
        runningMode: "VIDEO",
        numHands: 1,
      });
      state.delegate = delegate;
      return state.landmarker;
    } catch (err) {
      if (delegate === "CPU") throw err;
    }
  }
  return null;
}

/** Ask for the camera once and keep the stream across retries. */
async function openCamera() {
  if (state.stream) return true;
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
    return true;
  } catch (err) {
    if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) {
      show("s-denied");
    } else {
      blocked(t("We cannot reach the camera"),
        t("Another app may be using it."),
        `<p>${t("Close your other apps, then try again.")}</p>`,
        { label: t("Try again"), run: toSetup });
    }
    return false;
  }
}

/** The camera screen: framing first, whatever came before. */
async function toSetup() {
  stopLoop?.();
  if (!(await openCamera())) return;
  show("s-setup");
  attach($("video"));
  $("btn-setup").disabled = true;
  $("framing").textContent = t("Getting ready…");
  $("framing").classList.remove("good");
  try {
    await landmarkerReady();
  } catch (err) {
    blocked(t("We could not start the test"),
      t("The hand-tracking part did not load."),
      `<p>${t("Check your connection, then try again.")}</p>`,
      { label: t("Try again"), run: toSetup });
    return;
  }
  if (state.screen === "s-setup") runFraming();
}

function attach(video) {
  if (video.srcObject !== state.stream) video.srcObject = state.stream;
  // Shape the stage to the camera (portrait on most phones) so `contain`
  // fills it without letterboxing; see .stage in style.css.
  const fit = () => {
    if (video.videoWidth && video.videoHeight) {
      video.parentElement.style.setProperty("--stage-ar", String(video.videoWidth / video.videoHeight));
    }
  };
  fit();
  video.addEventListener("loadedmetadata", fit, { once: true });
  video.play().catch(() => {});
}

function stopCamera() {
  if (state.stream) state.stream.getTracks().forEach((tr) => tr.stop());
  state.stream = null;
}

/* ── Upright check (portrait lock) ─────────────────────────────────────── */
// A phone turned on its side mid-test turns the camera's picture under the
// hand, and a phone that is being turned is usually a phone being held. It
// applies to phones only: a tablet in landscape is a steady, sensible setup.

function sideways() {
  const landscape = window.matchMedia("(orientation: landscape)").matches;
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const phone = Math.min(window.screen.width, window.screen.height) < 600;
  return landscape && coarse && phone;
}

function checkUpright() {
  $("turn").hidden = !(CAMERA_SCREENS.has(state.screen) && sideways());
}

window.matchMedia("(orientation: landscape)").addEventListener?.("change", checkUpright);
window.addEventListener("resize", checkUpright);

/* ── The frame loop ────────────────────────────────────────────────────── */

// MediaPipe needs strictly increasing timestamps for the landmarker's whole
// life, across every loop; the scoring clock below is a separate matter.
let lastDetectMs = 0;

/** One landmark read per *camera* frame, never per display refresh.

    The first version ran on requestAnimationFrame, which fires at the
    screen's rate (60 Hz or more) while a phone camera delivers about 30 fps.
    Each camera frame was then scored twice under two timestamps: the fps gate
    measured the screen instead of the camera and could not fire, the
    detector's EMA ran twice per real frame, and tap times fell on display
    ticks. requestVideoFrameCallback fires once per new frame and says when it
    was captured; where it is missing, rAF skips any frame whose currentTime
    has not moved.

    Each frame hands `onFrame(t, f)` the frame's time in seconds and
    f = {raw, smoothed, d, label, mon}: raw landmarks for framing (as the
    desktop does, since the smoothed ones lag), One-Euro-smoothed landmarks
    for the distance, `d` (null while the framing monitor distrusts the hand)
    and MediaPipe's handedness label. */
function makeLoop(video, canvas, onFrame) {
  const ctx = canvas.getContext("2d");
  const [fx, fy] = makeLandmarkFilters();
  const mon = new FramingMonitor();
  let stopped = false;
  let lastT = null;
  let fpsEma = 0;
  let clock = null;          // which frame clock this loop uses, fixed at frame 1
  let lastMediaTime = -1;

  const frameTime = (meta) => {
    if (!meta) return performance.now() / 1000;
    if (clock === null) {
      clock = typeof meta.captureTime === "number" ? "capture"
            : meta.mediaTime > 0 ? "media" : "display";
    }
    if (clock === "capture") return meta.captureTime / 1000;
    if (clock === "media") return meta.mediaTime;
    return meta.expectedDisplayTime / 1000;
  };

  const process = (tNow) => {
    if (lastT !== null) {
      const dt = tNow - lastT;
      if (dt <= 0) return;                 // same frame twice: never score it
      fpsEma = fpsEma ? 0.9 * fpsEma + 0.1 * (1 / dt) : 1 / dt;
      state.fps = fpsEma;
    }
    lastT = tNow;

    let raw = null, smoothed = null, label = null;
    if (state.landmarker) {
      if (canvas.width !== video.videoWidth) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        state.frameW = video.videoWidth;
        state.frameH = video.videoHeight;
      }
      const ms = Math.max(lastDetectMs + 1, performance.now());
      lastDetectMs = ms;
      const res = state.landmarker.detectForVideo(video, ms);
      raw = (res.landmarks && res.landmarks[0]) || null;
      if (raw) {
        smoothed = smoothLandmarks(raw, fx, fy, tNow);
        const cat = res.handedness && res.handedness[0] && res.handedness[0][0];
        // The camera's own frame is unmirrored (only the CSS mirrors it), and
        // on an unmirrored frame the label names the real hand
        // (core/hand_utils.true_hand, selfie=False).
        label = cat ? String(cat.categoryName || "").toLowerCase() : null;
      }
      draw(ctx, canvas, smoothed);
    }
    mon.update(raw, tNow);
    const d = smoothed && !mon.untrusted ? thumbIndexDistance(smoothed) : null;
    onFrame(tNow, { raw, smoothed, d, label, mon });
  };

  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    const onVideoFrame = (_now, meta) => {
      if (stopped) return;
      process(frameTime(meta));
      if (!stopped) video.requestVideoFrameCallback(onVideoFrame);
    };
    video.requestVideoFrameCallback(onVideoFrame);
  } else {
    const tick = () => {
      if (stopped) return;
      if (video.readyState >= 2 && video.currentTime !== lastMediaTime) {
        lastMediaTime = video.currentTime;
        process(performance.now() / 1000);
      }
      if (!stopped) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  return () => { stopped = true; };
}

const LINKS = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[0,9],[9,10],[10,11],[11,12],
               [0,13],[13,14],[14,15],[15,16],[0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]];

function draw(ctx, canvas, lm) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!lm) return;
  const X = (p) => p[0] * canvas.width, Y = (p) => p[1] * canvas.height;
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

/** The coaching line for a hand at the edge, in the page's language. The
 *  engine's hint() stays English (it mirrors core/framing.py). */
function edgeHint(mon) {
  return mon.level === LOST ? t("Show your hand to the camera") : translate(hint(mon.edges));
}

/* ── Framing gate ──────────────────────────────────────────────────────── */

let stopLoop = null;

function runFraming() {
  const box = $("framing"), stage = $("video").parentElement;
  let good = 0;
  stopLoop = makeLoop($("video"), $("overlay"), (tNow, f) => {
    let msg = t("Hold your hand up, so the camera can see it.");
    let ok = false;
    const lm = f.raw;
    const [level] = edgeState(lm);
    if (lm) {
      const span = Math.hypot(lm[0].x - lm[9].x, lm[0].y - lm[9].y);
      // The whole hand, with room to spare, before anything else: a hand at
      // the edge is guessed, and the guesses jitter (core/framing.py).
      if (level === CLIPPED || level === NEAR) msg = edgeHint(f.mon);
      else if (span < 0.10) msg = t("Come a little closer.");
      else if (span > 0.32) msg = t("Move back a little.");
      else if (state.fps < MIN_FPS) msg = t("Close your other apps. This phone is busy.");
      else if (sideways()) msg = t("Please turn your phone upright");
      else { msg = t("That's it. Hold still."); ok = true; }
    }
    good = ok ? good + 1 : 0;
    box.textContent = msg;
    box.classList.toggle("good", ok);
    stage.classList.toggle("good", ok);
    $("btn-setup").disabled = good < FRAMING_FRAMES;
  });
}

$("btn-setup").addEventListener("click", () => {
  stopLoop?.();
  toCalibration();
});

/* ── Calibration ───────────────────────────────────────────────────────── */

function toCalibration() {
  show("s-calibrate");
  attach($("video-cal"));
  runCalibration();
}

function runCalibration() {
  const cal = new Calibrator();
  $("cal-fill").style.width = "0%";
  $("cal-status").textContent = t("Touch them together…");
  stopLoop = makeLoop($("video-cal"), $("overlay-cal"), (tNow, f) => {
    if (f.d !== null) cal.update(tNow, f.d);
    $("cal-fill").style.width = `${Math.round(cal.progress * 100)}%`;
    $("cal-status").textContent = f.mon.untrusted && f.raw
      ? edgeHint(f.mon)
      : cal.cycles < 1 ? t("Touch them together…")
      : t("Good. {n} of {total}", { n: Math.min(cal.cycles, Calibrator.MIN_CYCLES), total: Calibrator.MIN_CYCLES });

    if (cal.done) {
      const [dc, dOpen] = cal.result();
      state.dClosed = dc;
      state.dOpen = dOpen;
      stopLoop?.();
      show("s-practice");
      attach($("video-practice"));
      runPractice();
    } else if (cal.timedOut(tNow)) {
      stopLoop?.();
      noGood(t("We could not see your hand opening and closing clearly. Let's try once more, a little slower."),
             "calibrate");
    }
  });
}

/* ── Practice (unscored, repeatable) ───────────────────────────────────── */

function runPractice() {
  const det = new TapDetector(minIntertapS(MODE), EMA_ALPHA, state.dClosed, state.dOpen);
  const countEl = $("practice-count");
  const feedback = $("practice-feedback");
  const ready = $("btn-practice-done");
  countEl.textContent = "0";
  feedback.textContent = t("Tap a few times to try it.");
  ready.disabled = true;
  let nearSeen = 0;
  stopLoop = makeLoop($("video-practice"), $("overlay-practice"), (tNow, f) => {
    if (f.mon.untrusted) {
      feedback.textContent = edgeHint(f.mon);
      return;
    }
    if (det.update(tNow, f.d)) {
      const n = det.tapTimes.length;
      countEl.textContent = String(n);
      countEl.classList.remove("pulse");
      void countEl.offsetWidth;
      countEl.classList.add("pulse");
      feedback.textContent = n >= MIN_PRACTICE_TAPS
        ? t("Good. You're ready when you are.") : t("That's a tap. Good.");
      ready.disabled = n < MIN_PRACTICE_TAPS;
    } else if (det.nearMiss > nearSeen) {
      // A closure too shallow to count: the one thing a lone participant can
      // fix on the spot, and the commonest reason a real run scores badly.
      nearSeen = det.nearMiss;
      feedback.textContent = t("Open your fingers wider between taps.");
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
  $("trial-title").textContent = t("Get ready");
  cd.classList.add("show");
  for (const n of ["3", "2", "1", t("Go")]) {
    if (state.screen !== "s-trial") { cd.classList.remove("show"); return; }
    cd.textContent = n;
    say(n);
    await new Promise((r) => setTimeout(r, 700));
  }
  cd.classList.remove("show");
  if (state.screen !== "s-trial") return;     // "Start over" during the count

  const det = new TapDetector(minIntertapS(MODE), EMA_ALPHA, state.dClosed, state.dOpen);
  const countEl = $("trial-count");
  const pausedEl = $("trial-paused");
  countEl.textContent = "0";
  $("trial-bar").style.width = "0%";
  $("trial-title").textContent = t("Go!");
  state.handVotes = {};

  // The run pauses while the hand is (partly) out of view and resumes once it
  // is back, as on the desktop (finger_tapping._update_pause). It runs on a
  // *scored* clock -- frame time minus time spent paused -- so the window,
  // the progress bar and the tap times need no special casing; the one
  // interval that spans each pause is dropped via a blackout. A phone turned
  // on its side pauses it the same way.
  let t0 = null, frames = 0, seen = 0;
  let pausedTotal = 0, pausedSince = null;
  const pauses = [], blackouts = [];
  const scored = (tNow) => (pausedSince !== null ? pausedSince : tNow) - pausedTotal;

  stopLoop = makeLoop($("video-trial"), $("overlay-trial"), (tNow, f) => {
    if (t0 === null) t0 = tNow;
    const turned = sideways();
    const bad = f.mon.untrusted || turned;
    if (bad && pausedSince === null) {
      pausedSince = tNow;
    } else if (!bad && pausedSince !== null) {
      const at = pausedSince - pausedTotal;
      const wall = tNow - pausedSince;
      pausedTotal += wall;
      pausedSince = null;
      blackouts.push([at - PRE_ROLL_S, at + RESUME_GUARD_S]);
      pauses.push([Number((at - t0).toFixed(3)), Number(wall.toFixed(2))]);
    }
    const paused = pausedSince !== null;
    const st = scored(tNow);
    const elapsed = st - t0;

    pausedEl.hidden = !paused;
    if (paused) {
      $("trial-paused-hint").textContent = turned
        ? t("Please turn your phone upright") : edgeHint(f.mon);
      if (pausedTotal + (tNow - pausedSince) > MAX_PAUSED_S) {
        stopLoop?.();
        pausedEl.hidden = true;
        noGood(t("Your hand was out of view for too long. Let's try again with the phone a little further away."),
               "setup");
        return;
      }
    } else {
      frames += 1;
      if (f.raw) seen += 1;
      if (f.label) state.handVotes[f.label] = (state.handVotes[f.label] || 0) + 1;
    }

    if (elapsed >= MODE.duration_s) {
      stopLoop?.();
      pausedEl.hidden = true;
      finish(det, t0, st, frames ? seen / frames : 0, {
        pauses, blackouts, pausedTotal, clippedPct: f.mon.clippedPct,
      });
      return;
    }
    if (!paused && det.update(st, f.d)) {
      countEl.textContent = String(det.tapTimes.length);
      countEl.classList.remove("pulse");
      void countEl.offsetWidth;
      countEl.classList.add("pulse");
    }
    $("trial-bar").style.width = `${Math.min(100, (elapsed / MODE.duration_s) * 100)}%`;
  });
}

/** A run that cannot be scored. The camera stays on, so "Try again" goes
 *  straight back to `step` rather than through the camera prompt again. */
function noGood(why, step) {
  state.retry = step;
  $("nogood-why").textContent = why;
  show("s-nogood");
}

$("btn-again").addEventListener("click", () => {
  if (state.retry === "calibrate" && state.stream) toCalibration();
  else toSetup();
});

function finish(det, tStart, tEnd, visibleRatio, framing) {
  // The gate the plan insists on: too few frames, or a hand out of view, and
  // we say so rather than publish a number we do not trust.
  if (state.fps < MIN_FPS || visibleRatio < MIN_VISIBLE_RATIO) {
    noGood(state.fps < MIN_FPS
      ? t("This phone was working too hard to measure accurately. Close your other apps and try again.")
      : t("Your hand went out of view during the test. Let's try again with the phone a little further away."),
      "setup");
    return;
  }

  const m = computeMetrics(MODE, det.tapTimes, det.series, tStart, tEnd, null,
                           visibleRatio, state.fps, det.nearMiss, framing.blackouts);
  if (!m.scoreable) {
    noGood(m.reason ? translate(m.reason) : t("We could not score that attempt."), "setup");
    return;
  }
  // Scored: the camera has done its job, so it goes off now.
  stopCamera();

  const votes = Object.entries(state.handVotes).sort((a, b) => b[1] - a[1]);

  // The record the hub expects (core/session.py schema, §4: metrics only).
  // Every metric the engine computes goes home, so the hub's Analysis view
  // shows the verdict the engine reached rather than re-deriving it.
  state.session = {
    session_id: uuid(),
    timestamp: new Date().toISOString(),
    test: state.invite.session_test || "finger_tapping",
    mode: state.invite.mode || MODE.key,
    hand: state.hand,
    duration_s: Number((tEnd - tStart).toFixed(2)),
    participant: state.invite.participant || "",
    device: {
      ua: navigator.userAgent.slice(0, 200),
      platform: B.ios ? "ios" : "other",
      fps_sustained: Number(state.fps.toFixed(1)),
      app_version: APP_VERSION,
      lang: getLang(),
      delegate: state.delegate || "",
      frame_w: state.frameW,
      frame_h: state.frameH,
      hand_detected: votes.length ? votes[0][0] : "",
    },
    metrics: {
      ...pick(m, METRIC_KEYS),
      pause_count: framing.pauses.length,
      paused_s: Number(framing.pausedTotal.toFixed(1)),
      edge_clipped_pct: Number(framing.clippedPct.toFixed(1)),
    },
  };

  renderResult(m);
  cloud.markDone(state.token);
  send();
}

// Every number computeMetrics() returns, and nothing it returns as text or as
// a list: `reason` is null on a scored run, and `label` is a band sentence the
// hub re-derives from `status`. core/remote/ingest.py accepts numbers only.
const METRIC_KEYS = [
  "scoreable", "taps", "duration_s", "frequency_hz", "mean_iti_ms", "iiv_ms",
  "cv_pct", "cv_pct_unrepaired", "amplitude_mean", "amplitude_cv_pct",
  "decrement_pct_per_s", "n_intervals", "cv_ci_low_pct", "cv_ci_high_pct",
  "confidence_pct", "band_edge", "taps_w10", "frequency_hz_w10", "cv_pct_w10",
  "near_miss_taps", "opening_shrink_ratio", "missed_tap_forgiven",
  "interruptions",
];

function pick(obj, keys) {
  const out = {};
  for (const k of keys) if (k in obj) out[k] = obj[k];
  return out;
}

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/* ── Result and upload ─────────────────────────────────────────────────── */
// The test counts as done on this phone the moment it is scored and parked,
// not when the upload lands: a parked result is still on its way.

// Thank-you only (decided 2026-09-29). The participant is alone, and may have
// the very impairment being measured; a steadiness sentence or a CV% with
// nobody there to put it in context helps nobody. The helper sees the verdict
// in the hub. The engine still computes everything, and all of it is sent.
function renderResult(m) {
  $("result-plain").textContent =
    t("Thank you. Your result is ready for {name}.", { name: helperName() });
  $("result-metric").innerHTML =
    `<div class="big">${m.taps}</div><div class="unit">${
      esc(t("taps in {secs} seconds", { secs: MODE.duration_s }))}</div>`;
  show("s-result");
}

async function send() {
  $("result-sent").textContent = t("Sending your result…");
  cloud.park(state.token, state.invite, state.session);
  try {
    await cloud.uploadResult(state.token, state.invite, state.session);
    cloud.clearPark(state.session.session_id);
    // "Saved", never "seen": the helper may not open the hub for a week (§6).
    $("result-sent").textContent = t("Saved and sent to {name}.", { name: helperName() });
    $("result-retry").hidden = true;
  } catch (err) {
    $("result-sent").textContent = "";
    $("result-retry").hidden = false;
  }
}

$("btn-resend").addEventListener("click", send);
window.addEventListener("online", () => { cloud.flushParked().catch(() => {}); });

applyStatic();
boot();
