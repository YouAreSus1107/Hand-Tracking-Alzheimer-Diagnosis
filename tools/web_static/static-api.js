/* Hub connector — injected into the published build by tools/build_web.py.
   The local launcher never loads this file.

   launcher_web/ was written against launcher.py's /api/* endpoints, and the
   published copy has no server behind it. The tests are Python (OpenCV,
   MediaPipe, the engines in core/), so a browser cannot run them — but it can
   drive the hub the visitor installed on their own machine. This file is that
   bridge, and it has three states:

     connected — a paired hub answered on 127.0.0.1. Every /api/* call is
                 forwarded to it with the pairing token, so the page works in
                 full: status pills, Launch/Stop, camera chip, Analysis charts
                 off the local results/, Developer page. Results travel from
                 the visitor's machine to the visitor's browser; the host never
                 sees them.
     unpaired  — a hub is there but has not handed this page a token yet. The
                 Connect button navigates to the hub's /pair, which bounces
                 back here with the token in the fragment.
     probing   — the first ~1.5 s, before the hub has answered or timed out.
     offline   — no hub. Canned /api/* answers keep the dashboard rendering as
                 a preview, the machine-only UI is hidden, and the download
                 card is shown instead.

   The state lives on document.body.dataset.hub, which is what styles.css keys
   the download card off. The local hub never sets it, so that card cannot
   appear there. */
(function () {
  "use strict";

  var DEFAULT_PORT = 8770;
  var PROBE_MS = 1500;      // a local hub answers instantly or is not there
  var RETRY_MS = 10000;     // so starting the hub flips the page without a reload

  window.__HOSTED_PREVIEW__ = true;

  // Starts as "probing" so the download card does not flash on a machine
  // that does have a hub; styles.css only reveals it for offline/unpaired.
  var state = "probing";
  var port = DEFAULT_PORT;
  var token = "";
  var realAct = null;

  function hub() { return "http://127.0.0.1:" + port; }

  var NOTE_EN = "No hub found on this machine — download the app to run the tests.";
  var NOTE_ZH = "未偵測到本機 Hub — 請下載應用程式以執行測驗。";
  var PAIR_EN = "Connect this page to your hub first.";
  var PAIR_ZH = "請先將本頁與您的 Hub 配對。";

  function lang() {
    var v = null;
    try { v = localStorage.getItem("hubLang"); } catch (e) { /* private mode */ }
    if (v !== "en" && v !== "zh") {
      v = (navigator.language || "").toLowerCase().indexOf("zh") === 0 ? "zh" : "en";
    }
    return v;
  }

  function note() {
    if (state === "unpaired") return lang() === "zh" ? PAIR_ZH : PAIR_EN;
    return lang() === "zh" ? NOTE_ZH : NOTE_EN;
  }

  /* ── Stored pairing ───────────────────────────────────────────────── */

  function load() {
    try {
      token = localStorage.getItem("hubToken") || "";
      port = parseInt(localStorage.getItem("hubPort"), 10) || DEFAULT_PORT;
    } catch (e) { /* private mode: pair again each visit */ }
  }

  function save() {
    try {
      localStorage.setItem("hubToken", token);
      localStorage.setItem("hubPort", String(port));
    } catch (e) { /* not fatal — the token still works for this page load */ }
  }

  /* The hub redirects back here as #hub=<port>&token=<code>. Read it, then
     strip it from the address bar so the token is not left behind in a copied
     URL or a shared screenshot. */
  function readHash() {
    var h = (location.hash || "").replace(/^#/, "");
    if (!h || h.indexOf("token=") < 0) return false;
    var got = {};
    h.split("&").forEach(function (part) {
      var i = part.indexOf("=");
      if (i > 0) got[part.slice(0, i)] = decodeURIComponent(part.slice(i + 1));
    });
    if (!got.token) return false;
    token = got.token;
    port = parseInt(got.hub, 10) || DEFAULT_PORT;
    save();
    try {
      history.replaceState(null, "", location.pathname + location.search);
    } catch (e) { location.hash = ""; }
    return true;
  }

  /* ── Canned answers, used whenever no hub is driving the page ─────── */

  function payload(path) {
    if (path === "/api/status") {
      // `running` drives buildCards(); the booleans feed the status pills,
      // which stay hidden while offline.
      return {
        python: null, model_present: false, face_model_present: false,
        opencv: false, mediapipe: false, analysis_present: false, running: {}
      };
    }
    if (path === "/api/sessions") return { sessions: [] };
    if (path === "/api/glove/ports") return { pyserial: false, ports: [] };
    if (path === "/api/glove/samples") return { samples: [], seq: -1 };
    // /api/launch, /api/stop, /api/dev/*, /api/glove/* …
    return { ok: false, message: note(), running: {} };
  }

  function canned(path) {
    return new Response(JSON.stringify(payload(path)), {
      status: 200, headers: { "Content-Type": "application/json" }
    });
  }

  /* ── fetch bridge ─────────────────────────────────────────────────── */

  var realFetch = window.fetch && window.fetch.bind(window);

  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var path, query = "";
    try {
      var parsed = new URL(url, location.href);
      path = parsed.pathname;
      query = parsed.search;
    } catch (e) {
      path = String(url).split("?")[0];
    }

    if (path.indexOf("/api/") !== 0) {
      return realFetch ? realFetch(input, init)
                       : Promise.reject(new Error("fetch unavailable"));
    }
    if (state !== "connected" || !realFetch) return Promise.resolve(canned(path));

    var opts = {};
    for (var k in (init || {})) opts[k] = init[k];
    opts.headers = Object.assign({}, (init && init.headers) || {},
                                 { "X-Hub-Token": token });

    return realFetch(hub() + path + query, opts).then(function (r) {
      if (r.status === 403) {            // token rejected — pair again
        token = "";
        save();
        setState("unpaired");
        return canned(path);
      }
      return r;
    }, function () {                     // hub went away mid-session
      setState("offline");
      return canned(path);
    });
  };

  /* ── State ────────────────────────────────────────────────────────── */

  function show(el, on) { if (el) el.style.display = on ? "" : "none"; }

  function paint() {
    if (!document.body) return;
    document.body.dataset.hub = state;
    var live = state === "connected";

    show(document.getElementById("status"), live);

    // Pages that only mean something with a hub behind them: Developer (glove
    // over a serial port) and Remote (mints invite links against this
    // machine's ledger, and files what comes back into results/).
    ["dev", "remote"].forEach(function (page) {
      show(document.querySelector('.nav-link[data-page="' + page + '"]'), live);
      var node = document.getElementById("page-" + page);
      if (node && !live && node.classList.contains("active") &&
          typeof window.showPage === "function") {
        // Never strand the visitor on a page they can no longer reach.
        window.showPage("home");
      }
    });

    /* The generated cards call act() through an inline onclick, so swapping
       the global is what turns Launch into an explanation while offline. */
    if (realAct || typeof window.act === "function") {
      if (!realAct) realAct = window.act;
      window.act = live ? realAct : function () {
        if (typeof window.toast === "function") window.toast(note(), "info");
      };
    }

  }

  /* Real numbers on the download button, from what build_release.py wrote. */
  function fillSize() {
    var el = document.getElementById("get-size");
    if (!el || !realFetch) return;
    realFetch("/download/latest.json")
      .then(function (r) { return r.json(); })
      .then(function (m) {
        if (m && m.bytes) el.textContent = "(" + (m.bytes / 1048576).toFixed(1) + " MB)";
      })
      .catch(function () { /* no manifest: the button still works */ });
  }

  function setState(next) {
    if (next === state) return;
    state = next;
    paint();
    // Repopulate from the real hub the moment we connect.
    if (state === "connected" && typeof window.refresh === "function") window.refresh();
  }

  /* ── Probe ────────────────────────────────────────────────────────── */

  function probe() {
    if (!realFetch) return;
    var stop = null, ctrl = null;
    try {
      ctrl = new AbortController();
      stop = setTimeout(function () { ctrl.abort(); }, PROBE_MS);
    } catch (e) { /* no AbortController: rely on the browser's own timeout */ }

    realFetch(hub() + "/api/hub", ctrl ? { signal: ctrl.signal } : {})
      .then(function (r) {
        if (stop) clearTimeout(stop);
        if (!r.ok) throw new Error("hub replied " + r.status);
        setState(token ? "connected" : "unpaired");
      })
      .catch(function () {
        if (stop) clearTimeout(stop);
        setState("offline");
      });
  }

  /* ── Hooks for the download card ──────────────────────────────────── */

  // One click, no typing: a top-level navigation to the hub, which redirects
  // straight back here carrying the token.
  window.hubConnect = function () {
    location.href = hub() + "/pair?return=" + encodeURIComponent(location.origin);
  };

  // Fallback for anyone who would rather paste the code from the hub console.
  window.hubPairManual = function () {
    var el = document.getElementById("hub-code");
    var v = el && el.value.trim();
    if (!v) return;
    token = v;
    save();
    el.value = "";
    probe();
  };

  window.hubState = function () { return state; };

  /* ── Boot ─────────────────────────────────────────────────────────── */

  if (!readHash()) load();   // a fresh pairing wins over the stored one
  probe();
  setInterval(function () { if (state !== "connected") probe(); }, RETRY_MS);

  if (document.body) paint();
  document.addEventListener("DOMContentLoaded", function () {
    paint();
    fillSize();
  });
})();
