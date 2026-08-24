/* Hosted-preview shim — injected into the static build by tools/build_web.py.
   The local launcher never loads this file.

   launcher_web/ was written against launcher.py's /api/* endpoints. On static
   hosting there is no server, so this answers those calls in the page and
   hides the parts that only mean something on the local machine:

     • the environment status pills (they describe *this* PC's Python/OpenCV)
     • the Developer page (glove hardware over a serial port)
     • Launch / Stop (they start a local subprocess)

   /api/sessions deliberately returns nothing: results/ is personal
   health-adjacent data and is never published. */
(function () {
  "use strict";

  window.__HOSTED_PREVIEW__ = true;

  var NOTE_EN = "Screening tests run in the desktop app — this page is an online preview.";
  var NOTE_ZH = "篩檢測驗需要電腦版應用程式，本頁為線上預覽。";

  function note() {
    var lang = null;
    try { lang = localStorage.getItem("hubLang"); } catch (e) { /* private mode */ }
    if (lang !== "en" && lang !== "zh") {
      lang = (navigator.language || "").toLowerCase().indexOf("zh") === 0 ? "zh" : "en";
    }
    return lang === "zh" ? NOTE_ZH : NOTE_EN;
  }

  /* ── Canned /api/* responses ──────────────────────────────────────── */

  function payload(path) {
    if (path === "/api/status") {
      // `running` drives buildCards(); the booleans feed the status pills,
      // which the DOM patch below hides.
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

  var realFetch = window.fetch && window.fetch.bind(window);

  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var path;
    try { path = new URL(url, location.href).pathname; }
    catch (e) { path = String(url).split("?")[0]; }

    if (path.indexOf("/api/") === 0) {
      return Promise.resolve(new Response(JSON.stringify(payload(path)), {
        status: 200, headers: { "Content-Type": "application/json" }
      }));
    }
    return realFetch ? realFetch(input, init)
                     : Promise.reject(new Error("fetch unavailable"));
  };

  /* ── DOM patches ──────────────────────────────────────────────────── */
  /* Scripts sit at the end of <body>, so this fires after app.js has
     defined its globals. */
  document.addEventListener("DOMContentLoaded", function () {
    var status = document.getElementById("status");
    if (status) status.style.display = "none";

    var devLink = document.querySelector('.nav-link[data-page="dev"]');
    if (devLink && devLink.parentNode) devLink.parentNode.removeChild(devLink);

    var devPage = document.getElementById("page-dev");
    if (devPage && devPage.parentNode) devPage.parentNode.removeChild(devPage);

    /* The generated cards call act() through an inline onclick, so replacing
       the global gives an informative toast instead of a failed request.
       The hand-page buttons close over the original act() and fall through
       to the fetch shim above, which returns the same message. */
    if (typeof window.act === "function") {
      window.act = function () {
        if (typeof window.toast === "function") window.toast(note(), "info");
      };
    }
  });
})();
