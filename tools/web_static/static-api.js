/* Hub connector — injected into the published build by tools/build_web.py.
   The local launcher never loads this file.

   launcher_web/ was written against launcher.py's /api/* endpoints, and the
   published copy has no server behind it. The tests are Python (OpenCV,
   MediaPipe, the engines in core/), so a browser cannot run them — but it can
   drive the hub the visitor installed on their own machine. This file is that
   bridge, and it has four states:

     probing   — the first ~1.5 s, before the hub has answered or timed out.
     offline   — no hub. Canned /api/* answers keep the dashboard rendering as
                 a preview, the machine-only UI is hidden, and the connection
                 panel shows the setup rail.
     unpaired  — a hub is there but has not handed this page a token yet. The
                 Connect button navigates to the hub's /pair, which bounces
                 back here with the token in the fragment.
     connected — a paired hub answered on 127.0.0.1. Every /api/* call is
                 forwarded to it with the pairing token, so the page works in
                 full: status pills, Launch/Stop, camera chip, Analysis charts
                 off the local results/, Developer page. Results travel from
                 the visitor's machine to the visitor's browser; the host never
                 sees them.

   The state lives on document.body.dataset.hub, which is what styles.css keys
   the connection panel and the connected chip off. The local hub never sets
   it, so neither can appear there.

   Two rules the UI here exists to enforce:

     * Connecting never navigates blind. `location.href = <hub>/pair` used to
       fire on a click alone; with no hub running that is a browser error page
       and the whole dashboard is gone, with nothing on it to come back to. It
       now pre-flights /api/hub and reports failure *in the page*.
     * Every state has a way out. "Check again" re-probes on demand, "Forget
       the stored pairing code" drops the token, and both are reachable while
       connected through the chip in the Screening Tools head. */
(function () {
  "use strict";

  var DEFAULT_PORT = 8770;
  var PROBE_MS = 1500;      // a local hub answers instantly or is not there
  var RETRY_MS = 10000;     // so starting the hub flips the page without a reload
  var WAKE_MS = 1200;       // debounce for the returned-to-this-tab re-probe

  window.__HOSTED_PREVIEW__ = true;

  // Starts as "probing" so the panel does not flash on a machine that does
  // have a hub; styles.css only reveals it for offline/unpaired.
  var state = "probing";
  var checking = false;     // a pre-flight is in flight (spinner, not a state)
  var errorKind = "";       // "" | "unreachable" | "badcode" | "blocked"
  var port = DEFAULT_PORT;
  var token = "";
  var info = null;          // last /api/hub answer: {hub, version}
  var realAct = null;
  var lastWake = 0;
  // Chrome's local-network-access permission, when the browser exposes it:
  // "granted" | "prompt" | "denied" | "unsupported" | "" (not yet asked).
  var perm = "";

  function hub() { return "http://127.0.0.1:" + port; }
  function addr() { return "127.0.0.1:" + port; }

  /* i18n. This file is injected ahead of i18n.zh.js, so t()/tKey() do not
     exist while it parses — but they do by the time anything here paints.
     Look them up per call and fall back to the English source. */
  function T(key, en) {
    var out = typeof window.tKey === "function" ? window.tKey(key, en) : en;
    // tKey takes no parameters, so the one runtime value these strings need —
    // the hub's address — travels as a placeholder the translation keeps.
    return String(out).replace(/\{addr\}/g, addr());
  }

  function note() {
    if (state === "unpaired")
      return T("get.msg.pairfirst", "Connect this page to your hub first.");
    // Not "download the app": the people who read this line most often are the
    // ones who already did, and telling them to download again is the whole
    // complaint. Say what is actually true — nothing is answering — and let
    // the panel's own rail decide whether the next step is install or start.
    if (errorKind === "blocked")
      return T("get.msg.blocked",
               "Your browser is blocking this page from reaching the hub on {addr}.");
    return T("get.msg.nohub", "No hub is answering on {addr} — start run_hub.bat on your machine.");
  }

  /* Is this page itself on loopback? Then it is not crossing into the local
     network at all, the local-network permission never applies, and its state
     says nothing about why a probe failed. Without this check a hub that is
     simply not running gets blamed on the browser — which is how the first cut
     of this fix behaved when the dashboard was served from 127.0.0.1. */
  function localPage() {
    var h = location.hostname;
    return h === "localhost" || h === "::1" || h === "[::1]" || /^127\./.test(h);
  }

  /* Chrome 138+ gates a public page reaching loopback behind the
     local-network-access permission. Knowing its state is what lets a failed
     probe say "your browser blocked this" instead of "no hub found" — the two
     are indistinguishable from the fetch rejection alone (both are a bare
     TypeError). Any browser without the permission API answers "unsupported",
     which is treated as "not the problem". */
  function readPerm() {
    if (!navigator.permissions || !navigator.permissions.query)
      return Promise.resolve("unsupported");
    try {
      return navigator.permissions.query({ name: "local-network-access" }).then(
        function (p) { return p.state; },
        function () { return "unsupported"; });   // name unknown to this browser
    } catch (e) {
      return Promise.resolve("unsupported");
    }
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
      // which stay hidden while offline. python:null reads as "not known
      // yet" rather than as a missing dependency (app.js pill()).
      return {
        python: null, model_present: false, face_model_present: false,
        opencv: false, mediapipe: false, analysis_present: false, running: {}
      };
    }
    if (path === "/api/sessions") return { sessions: [] };
    // The roster lives on the visitor's own hub, so with none paired there is
    // nobody to show — an empty one keeps the chip rendering as "No profile".
    if (path === "/api/profiles") return { profiles: [], active: "" };
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
        errorKind = "badcode";
        setState("unpaired");
        return canned(path);
      }
      return r;
    }, function () {                     // hub went away mid-session
      setState("offline");
      return canned(path);
    });
  };

  /* ── Painting ─────────────────────────────────────────────────────── */

  function el(id) { return document.getElementById(id); }
  function show(node, on) { if (node) node.style.display = on ? "" : "none"; }
  function toggle(node, on) { if (node) node.hidden = !on; }

  var WARN_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
    + '<path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

  function paint() {
    if (!document.body) return;
    document.body.dataset.hub = state;
    var live = state === "connected";

    show(el("status"), live);

    // Pages that only mean something with a hub behind them: Developer (glove
    // over a serial port) and Remote (mints invite links against this
    // machine's ledger, and files what comes back into results/).
    ["dev", "remote"].forEach(function (page) {
      show(document.querySelector('.nav-link[data-page="' + page + '"]'), live);
      var node = el("page-" + page);
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

    paintPanel();
    paintChip();
  }

  /* SVG <text> takes no innerHTML from the i18n layer, so the artwork's two
     captions are written here instead. */
  function artText(id, str) {
    var node = el(id);
    if (node && node.textContent !== str) node.textContent = str;
  }

  /* One beam down the wire per probe. Re-adding the class is not enough — the
     animation only restarts once the element has been reflowed without it. */
  function pulse() {
    var link = el("hub-link");
    if (!link) return;
    link.classList.remove("is-ping");
    void link.offsetWidth;
    link.classList.add("is-ping");
  }

  /* The connection panel: state chip, the illustrated stage, which actions
     are live, and the failure notice. Step 3 is `locked` until a hub actually
     answers — a Connect button that cannot be pressed early is the whole
     point of the stage. */
  function paintPanel() {
    var word = el("hub-state-word");
    if (!word) return;                       // local hub, or not parsed yet

    var words = {
      probing:   T("get.state.probing",   "Searching…"),
      offline:   T("get.state.offline",   "Not connected"),
      unpaired:  T("get.state.unpaired",  "Hub found"),
      connected: T("get.state.connected", "Connected")
    };
    word.textContent = words[state] || words.offline;

    var found = state === "unpaired" || state === "connected";
    var stage = el("hub-stage");
    if (stage) {
      // Two shapes, not three: while nothing answers the visitor is being
      // walked through an install; once something does, the only thing left
      // on the page is the link between here and there.
      stage.setAttribute("data-stage", found ? "link" : "install");
      var boards = stage.querySelectorAll(".hub-board");
      for (var i = 0; i < boards.length; i++) {
        var n = i + 1, st;
        if (state === "connected") st = "done";
        else if (found) st = n < 3 ? "done" : "current";
        else st = n === 1 ? "current" : "locked";
        boards[i].setAttribute("data-step-state", st);
      }
    }
    toggle(el("hub-chips"), found);

    // The handshake drawing is the status display, so it is painted from the
    // same three variables the words are: what state we are in, whether a
    // probe is in flight, and what the last failure was.
    var link = el("hub-link");
    if (link) {
      var art = "idle";
      if (state === "connected") art = "paired";
      else if (state === "unpaired") art = "found";
      else if (errorKind === "blocked") art = "blocked";
      link.setAttribute("data-art", art);
      // Both captions live inside the SVG, where data-i18n cannot reach them:
      // applyStatic() rewrites innerHTML and would erase the artwork.
      artText("art-cap-page", T("get.art.page", "this page"));
      artText("art-cap-machine", T("get.art.machine", "your machine"));
    }

    // Someone with a hub running has plainly already downloaded it.
    toggle(el("hub-dl"), !found);

    var connect = el("hub-connect");
    if (connect) {
      connect.disabled = !(state === "unpaired") || checking;
      connect.classList.toggle("is-busy", checking);
      connect.setAttribute("title", state === "unpaired"
        ? T("get.connect.tip", "Hand this page a pairing code from the hub")
        : T("get.connect.locked", "Start the hub on your machine first"));
    }
    var recheck = el("hub-recheck");
    if (recheck) recheck.classList.toggle("is-busy", checking);

    // The listening pulse is the page saying it has not given up. It is
    // replaced by the error notice, never stacked with it.
    toggle(el("hub-listen"), !found && !errorKind);

    var err = el("hub-error");
    if (err) {
      var msg = "";
      if (errorKind === "blocked") {
        // The one failure the visitor cannot fix by starting the hub. Chrome
        // will not say this for us: the fetch just fails, and every earlier
        // version of this page read that as "no hub installed" and told
        // someone who had already installed it to download it again.
        msg = T("get.err.blocked",
                "Your browser is blocking this page from reaching <code>{addr}</code>. "
                + "Chrome asks permission before a website may talk to your own computer — "
                + "choose <strong>Allow</strong> when it asks, or turn on "
                + "<strong>Local network access</strong> for this site in the padlock menu "
                + "beside the address bar, then try again.");
      } else if (errorKind === "unreachable") {
        msg = T("get.err.unreachable",
                "Could not reach the hub on <code>{addr}</code>. It may have stopped — "
                + "start <code>run_hub.bat</code> on your machine, then try again.");
        // A refused connection and a permission Chrome has not been asked for
        // are the same rejection here, so name the second possibility rather
        // than picking one and being confidently wrong about it.
        if (mightBeBlocked())
          msg += " " + T("get.err.maybeblocked",
                         "If it is already running, your browser may be withholding permission "
                         + "to reach your own computer — choose <strong>Allow</strong> when it "
                         + "asks, or turn on <strong>Local network access</strong> for this site "
                         + "in the padlock menu beside the address bar.");
      } else if (errorKind === "badcode") {
        msg = T("get.err.badcode",
                "That pairing code was not accepted. Copy it again from the hub console.");
      }
      err.hidden = !msg;
      if (msg) {
        var text = el("hub-error-text");
        if (text) text.innerHTML = msg;
        var ic = el("hub-error-ic");
        if (ic && !ic.firstChild) ic.innerHTML = WARN_SVG;
      }
    }

    toggle(el("hub-forget"), !!token);
  }

  /* Connected chip, rendered into the [data-hub-chip] slot beside the camera
     chip. Once paired the panel is hidden, so this is the only place the
     pairing can be inspected or undone. */
  function paintChip() {
    var slot = document.querySelector("[data-hub-chip]");
    if (!slot) return;
    if (state !== "connected") { slot.innerHTML = ""; slot.dataset.sig = ""; return; }

    var sig = [addr(), (info && info.version) || "", typeof window.getLang === "function"
      ? window.getLang() : ""].join("|");
    if (slot.dataset.sig === sig) return;    // the 3 s poll must not churn this

    slot.innerHTML =
      '<button class="hub-chip" type="button" aria-expanded="false" aria-haspopup="dialog">'
      + '<span class="hub-chip-dot"></span>' + T("get.chip", "Hub") + '</button>'
      + '<div class="hub-pop" role="dialog" hidden>'
      + '<div class="hub-pop-title">' + T("get.chip.title", "Paired hub") + '</div>'
      + '<div class="hub-pop-row"><span>' + T("get.chip.addr", "Address") + '</span><b>' + addr() + '</b></div>'
      + '<div class="hub-pop-row"><span>' + T("get.chip.ver", "Version") + '</span><b>'
      + ((info && info.version) || "—") + '</b></div>'
      + '<div class="hub-pop-foot">'
      + '<button class="btn-mini" type="button" data-recheck>' + T("get.recheck", "Check again") + '</button>'
      + '<button class="hub-forget" type="button" data-forget>' + T("get.forget", "Forget the stored pairing code") + '</button>'
      + '</div></div>';
    slot.dataset.sig = sig;

    var chip = slot.querySelector(".hub-chip");
    var pop = slot.querySelector(".hub-pop");
    chip.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = pop.hidden;
      closeChip();
      pop.hidden = !open;
      chip.setAttribute("aria-expanded", String(open));
    });
    slot.addEventListener("click", function (e) { e.stopPropagation(); });
    slot.querySelector("[data-recheck]").addEventListener("click", function () {
      window.hubRecheck();
    });
    slot.querySelector("[data-forget]").addEventListener("click", function () {
      closeChip();
      window.hubForget();
    });
  }

  function closeChip() {
    var pop = document.querySelector("[data-hub-chip] .hub-pop");
    var chip = document.querySelector("[data-hub-chip] .hub-chip");
    if (pop) pop.hidden = true;
    if (chip) chip.setAttribute("aria-expanded", "false");
  }
  document.addEventListener("click", closeChip);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeChip(); });

  /* Real numbers on the download button, from what build_release.py wrote. */
  function fillSize() {
    var node = el("get-size");
    if (!node || !realFetch) return;
    realFetch("/download/latest.json")
      .then(function (r) { return r.json(); })
      .then(function (m) {
        if (m && m.bytes) node.textContent = "(" + (m.bytes / 1048576).toFixed(1) + " MB)";
      })
      .catch(function () { /* no manifest: the button still works */ });
  }

  function setState(next) {
    if (next === state) { paintPanel(); return; }
    var was = state;
    state = next;
    if (state === "connected") errorKind = "";
    paint();
    // Everything the page cached while it had no hub — the canned status
    // payload, the empty session list — has to be thrown away, or the pills
    // and the readings strip keep reporting the preview after pairing.
    if (state === "connected" && was !== "connected") {
      if (typeof window.rehydrate === "function") window.rehydrate();
      else if (typeof window.refresh === "function") window.refresh();
    }
  }

  /* ── Probe ────────────────────────────────────────────────────────── */

  /* One /api/hub call with a hard timeout. Resolves true/false; never throws.
     The hub answers this one before pairing (launcher.py _authorised). */
  function ping() {
    if (!realFetch) return Promise.resolve(false);
    pulse();                                 // the wire shows every attempt
    var stop = null, ctrl = null;
    try {
      ctrl = new AbortController();
      stop = setTimeout(function () { ctrl.abort(); }, PROBE_MS);
    } catch (e) { /* no AbortController: rely on the browser's own timeout */ }

    // targetAddressSpace states the intent Chrome would otherwise have to
    // infer: this https page means to reach a plaintext loopback address.
    // Browsers that do not know the option ignore it.
    var opts = { targetAddressSpace: "loopback" };
    if (ctrl) opts.signal = ctrl.signal;

    return realFetch(hub() + "/api/hub", opts)
      .then(function (r) {
        if (stop) clearTimeout(stop);
        if (!r.ok) return false;
        return r.json().then(function (j) { info = j; return true; },
                             function () { return true; });
      }, function () {
        if (stop) clearTimeout(stop);
        return false;
      });
  }

  /* What to blame for a failed probe. Deliberately conservative: the page can
     prove the browser refused only when the permission is "denied". Everything
     else reads as "nothing answered", which is true whether the hub is not
     installed, not started, or on another port. */
  function classify() {
    if (!localPage() && perm === "denied") return "blocked";
    return "unreachable";
  }

  /* Could an ungranted permission plausibly be why this failed? Not proof —
     just enough to be worth mentioning alongside "start the hub". */
  function mightBeBlocked() {
    return !localPage() && (perm === "prompt" || perm === "denied");
  }

  /* `explicit` marks a probe the visitor asked for. Only those raise the error
     notice: the boot probe and the retry timer run on a first-time visitor who
     has installed nothing yet, and greeting them with a warning triangle that
     says to start run_hub.bat describes a problem they do not have. They get
     the quiet listening pulse and the download rail instead. The permission
     state is still recorded either way, so the copy is right the moment they
     do press something. */
  function probe(explicit) {
    return ping().then(function (ok) {
      if (ok) {
        // A hub answering clears a stale "could not reach it" and proves the
        // browser is not in the way; a rejected pairing code is a different
        // complaint and stands until it is retried.
        if (errorKind === "unreachable" || errorKind === "blocked") errorKind = "";
        perm = "granted";
        setState(token ? "connected" : "unpaired");
        return true;
      }
      // The probe failed. Before calling that "no hub", find out whether the
      // browser ever let the request leave: an ungranted local-network
      // permission looks exactly like a machine with nothing installed.
      return readPerm().then(function (p) {
        perm = p;
        // Only "denied" is proof. "prompt" is the state of every browser that
        // has never been asked, including one whose hub is simply not running,
        // so it earns a mention in the copy — not a diagnosis.
        if (explicit) errorKind = classify();
        setState("offline");
        paintPanel();
        return false;
      });
    });
  }

  /* ── Hooks the panel and the chip call ────────────────────────────── */

  /* One click, no typing: a top-level navigation to the hub, which redirects
     straight back here carrying the token. Pre-flighted, because that
     navigation cannot be taken back — with no hub listening the visitor lands
     on the browser's connection-refused page and the dashboard is gone. */
  window.hubConnect = function () {
    if (checking) return;
    checking = true;
    errorKind = "";
    paintPanel();
    ping().then(function (ok) {
      if (ok) {
        checking = false;
        location.href = hub() + "/pair?return=" + encodeURIComponent(location.origin);
        return;
      }
      // "It stopped" and "the browser would not let us ask" are the same
      // rejection to fetch, and only one of them is fixed by starting the hub.
      return readPerm().then(function (p) {
        checking = false;
        perm = p;
        errorKind = classify();
        setState("offline");
        paintPanel();
      });
    });
  };

  /* The way out of a permission block. Called straight from a click, so the
     probe it fires carries transient user activation — which is the condition
     under which Chrome will show the local-network prompt at all, rather than
     rejecting the request without asking. The boot probe can never do this,
     which is why a blocked visitor needs a button and not just a retry timer. */
  window.hubAllow = function () {
    if (checking) return;
    checking = true;
    paintPanel();
    probe(true).then(function () {
      checking = false;
      paintPanel();
      if (typeof window.toast !== "function") return;
      if (state !== "offline") {
        window.toast(state === "connected"
          ? T("get.toast.connected", "Connected to the hub on this machine.")
          : T("get.toast.found", "Hub found. Connect this page to finish."), "ok");
      } else {
        window.toast(errorKind === "blocked"
          ? T("get.toast.blocked",
              "Still blocked. Allow local network access for this site in the padlock menu.")
          : T("get.toast.nohub", "Still no hub answering on {addr}."), "info");
      }
    });
  };

  /* The error box's one button. With nothing answering, "try again" has to be
     the gesture-driven probe: it is the only path that can surface a permission
     prompt, and it re-pings for the ordinary "hub was not started yet" case at
     the same time. Only once a hub has answered does it mean "go and pair". */
  window.hubRetry = function () {
    if (state === "offline") window.hubAllow();
    else window.hubConnect();
  };

  /* "Check again" — the way back from any state without a reload. */
  window.hubRecheck = function () {
    if (checking) return;
    checking = true;
    errorKind = "";
    paintPanel();
    probe(true).then(function () {
      checking = false;
      paintPanel();
      if (typeof window.toast === "function") {
        window.toast(state === "connected"
          ? T("get.toast.connected", "Connected to the hub on this machine.")
          : state === "unpaired"
            ? T("get.toast.found", "Hub found. Connect this page to finish.")
            : errorKind === "blocked"
              ? T("get.toast.blocked",
                  "Still blocked. Allow local network access for this site in the padlock menu.")
              : T("get.toast.nohub", "Still no hub answering on {addr}."),
          state === "offline" ? "info" : "ok");
      }
    });
  };

  /* Drop the stored pairing. The guaranteed way back to a first-visit state:
     a token that the hub no longer recognises would otherwise sit in
     localStorage and keep failing silently. */
  window.hubForget = function () {
    token = "";
    try {
      localStorage.removeItem("hubToken");
      localStorage.removeItem("hubPort");
    } catch (e) { /* private mode: the in-memory clear is enough */ }
    errorKind = "";
    setState(state === "connected" ? "unpaired" : state);
    paintPanel();
    probe();
  };

  // Fallback for anyone who would rather paste the code from the hub console.
  window.hubPairManual = function () {
    var node = el("hub-code");
    var v = node && node.value.trim();
    if (!v) return;
    token = v;
    save();
    node.value = "";
    errorKind = "";
    paintPanel();
    probe().then(function () {
      // A hub that is there but rejects the code lands back on `unpaired`
      // through the 403 path in the fetch bridge; say so rather than looking
      // like nothing happened.
      if (state !== "connected" && typeof window.refresh === "function") window.refresh();
    });
  };

  window.hubState = function () { return state; };

  /* ── Boot ─────────────────────────────────────────────────────────── */

  if (!readHash()) load();   // a fresh pairing wins over the stored one
  probe();
  setInterval(function () { if (state !== "connected") probe(); }, RETRY_MS);

  /* Coming back to this tab re-probes at once instead of waiting out RETRY_MS.
     pageshow also fires on a bfcache restore, which is what a Back press from
     a browser error page looks like. */
  function wake() {
    var now = Date.now();
    if (state === "connected" || checking || now - lastWake < WAKE_MS) return;
    lastWake = now;
    probe();
  }
  window.addEventListener("pageshow", wake);
  window.addEventListener("focus", wake);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) wake();
  });

  if (document.body) paint();
  document.addEventListener("DOMContentLoaded", function () {
    paint();
    fillSize();
    // Almost every string above is rendered from JS, so a language switch has
    // to ask for a repaint (i18n.js onLang, same hook app.js and dev.js use).
    if (typeof window.onLang === "function") {
      window.onLang(function () {
        var slot = document.querySelector("[data-hub-chip]");
        if (slot) slot.dataset.sig = "";      // force the chip to rebuild
        paintPanel();
        paintChip();
      });
    }
  });
})();
