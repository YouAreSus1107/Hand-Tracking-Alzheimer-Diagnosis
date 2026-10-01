/* Remote Sessions page — mint a QR code, watch what comes back.
   docs/platform/REMOTE_SESSION_PLAN.md

   A classic script like dev.js, loaded after app.js so it shares that file's
   `I` (icons), `t`/`tMsg` (i18n) and `toast()` bindings. app.js's showPage()
   starts and stops the poll, so nothing here runs while the page is off
   screen. Never shadow `t` — it is the translator.

   An invite is handed over as a QR code, never as text: the token is 22
   random characters with O/0/Q in the mix, and the first real phone test
   failed on a retyped link. The QR is drawn here by vendor/qrcode.js (MIT,
   Kazuhiko Arase), so nothing about the invite goes to a third party. */
(function () {
  "use strict";

  var ICON_QR = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/></svg>';
  var ICON_SAVE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 10l5 5 5-5M4 21h16"/></svg>';
  var ICON_COPY = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
  var ICON_INBOX = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h5l2 3h4l2-3h5"/><path d="M5.5 5h13l2.5 7v7H3v-7z"/></svg>';

  var state = null;        // last /api/remote/state payload
  var timer = null;
  var signature = "";      // rebuild the form only when its options changed
  var linksSig = "";       // ...and the QR list only when an invite changed
  var draft = { test: "iiv", mode: "big_and_fast", lang: "en", participant: "", ttl_hours: 48, uses: 1 };

  function el(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ── Fetch ──────────────────────────────────────────────────────── */

  async function load() {
    try {
      var r = await fetch("/api/remote/state");
      state = await r.json();
      render();
    } catch (e) { /* hub restarting — the next tick retries */ }
  }

  async function post(path, body) {
    try {
      var r = await fetch("/api/remote/" + path, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      });
      var data = await r.json();
      toast(tMsg(data.message) || t(data.ok ? "Done" : "Failed"), data.ok ? "ok" : "fail");
      await load();
      return data;
    } catch (e) {
      toast(t("Request failed"), "fail");
      return { ok: false };
    }
  }

  /* ── Stage banner — what works right now, stated plainly ─────────── */

  function renderStage() {
    var relay = (state && state.relay) || {};
    var box = el("remote-stage");
    if (relay.configured) {
      box.className = "rs-note rs-note-ok";
      box.innerHTML = ICON_INBOX + "<div><b>" + esc(t("Remote inbox connected.")) + "</b> " +
        esc(t("Results uploaded by a participant are pulled into results/ and appear in Analysis.")) +
        "</div>";
      return;
    }
    box.className = "rs-note";
    var missing = (relay.hints || []).map(function (h) { return "<li>" + esc(h) + "</li>"; }).join("");
    box.innerHTML = I.info + "<div><b>" + esc(t("The inbox is not connected yet.")) + "</b> " +
      esc(t("QR codes can be created and the results path can be tested locally, but nothing is pulled from the cloud until these are set:")) +
      "<ul>" + missing + "</ul></div>";
  }

  /* ── Create-a-link form ─────────────────────────────────────────── */

  function renderForm() {
    if (!state) return;
    var tests = state.tests || {};
    var d = state.defaults || {};
    var modes = (tests[draft.test] && tests[draft.test].modes) || [];
    if (modes.indexOf(draft.mode) < 0) draft.mode = modes[0] || "";

    var testOpts = Object.keys(tests).map(function (key) {
      return '<option value="' + esc(key) + '"' + (key === draft.test ? " selected" : "") +
        ">" + esc(t(tests[key].label)) + "</option>";
    }).join("");
    var modeOpts = modes.map(function (m) {
      return '<option value="' + esc(m) + '"' + (m === draft.mode ? " selected" : "") +
        ">" + esc(t(m)) + "</option>";
    }).join("");

    el("remote-form").innerHTML =
      '<label class="rs-field"><span>' + esc(t("Test")) + '</span>' +
        '<select id="rs-test" onchange="remoteDraft(\'test\',this.value)">' + testOpts + '</select></label>' +
      '<label class="rs-field"><span>' + esc(t("Mode")) + '</span>' +
        '<select id="rs-mode" onchange="remoteDraft(\'mode\',this.value)">' + modeOpts + '</select></label>' +
      '<label class="rs-field"><span>' + esc(t("Language")) + '</span>' +
        '<select id="rs-lang" onchange="remoteDraft(\'lang\',this.value)">' +
          '<option value="en"' + (draft.lang === "en" ? " selected" : "") + '>English</option>' +
          '<option value="zh"' + (draft.lang === "zh" ? " selected" : "") + '>繁體中文</option>' +
        '</select></label>' +
      '<label class="rs-field"><span>' + esc(t("Who is it for?")) + '</span>' +
        '<input id="rs-who" type="text" maxlength="60" placeholder="' + esc(t("First name")) + '" ' +
        'value="' + esc(draft.participant) + '" oninput="remoteDraft(\'participant\',this.value)"></label>' +
      '<label class="rs-field rs-narrow"><span>' + esc(t("Expires in (hours)")) + '</span>' +
        '<input id="rs-ttl" type="number" min="1" max="' + (d.max_ttl_hours || 168) + '" ' +
        'value="' + draft.ttl_hours + '" oninput="remoteDraft(\'ttl_hours\',this.value)"></label>' +
      '<label class="rs-field rs-narrow"><span>' + esc(t("Times it can be used")) + '</span>' +
        '<input id="rs-uses" type="number" min="1" max="' + (d.max_uses || 5) + '" ' +
        'value="' + draft.uses + '" oninput="remoteDraft(\'uses\',this.value)"></label>' +
      '<button class="btn btn-primary rs-create" onclick="remoteCreate()">' + ICON_QR +
        "<span>" + esc(t("Create QR code")) + "</span></button>" +
      '<p class="rs-for">' + esc(forWhom()) + "</p>";
  }

  // The profile chip decides whose history the results join.
  function forWhom() {
    var id = (window.activeProfileId && window.activeProfileId()) || "";
    var who = id && window.profileById ? window.profileById(id) : null;
    return who && who.name
      ? t("Results will be filed under {name}.", { name: who.name })
      : t("No profile is chosen, so results will need assigning by hand.");
  }

  /* ── Sent links ─────────────────────────────────────────────────── */

  var STATE_WORD = {
    live: "Live", spent: "Used", expired: "Expired", revoked: "Cancelled"
  };

  function when(stamp) {
    var d = new Date(stamp);
    return isNaN(d) ? String(stamp || "") : d.toLocaleString();
  }

  /* ── QR ─────────────────────────────────────────────────────────── */

  // Error correction M: survives a smudged screen or a forwarded photo of
  // the code at a size a phone camera still reads from arm's length.
  function qrMatrix(url) {
    var qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    return qr;
  }

  /** Always dark-on-white with a 4-module quiet zone, whatever the theme:
   *  phone cameras read inverted or borderless codes unreliably. */
  function qrSvg(url, label) {
    var qr = qrMatrix(url);
    var n = qr.getModuleCount(), q = 4, size = n + q * 2, d = "";
    for (var r = 0; r < n; r++) {
      for (var c = 0; c < n; c++) {
        if (qr.isDark(r, c)) d += "M" + (c + q) + " " + (r + q) + "h1v1h-1z";
      }
    }
    return '<svg class="rs-qr-svg" viewBox="0 0 ' + size + " " + size +
      '" shape-rendering="crispEdges" role="img" aria-label="' + esc(label) + '">' +
      '<rect width="' + size + '" height="' + size + '" fill="#fff"/>' +
      '<path d="' + d + '" fill="#000"/></svg>';
  }

  /** The image the helper sends: the code plus who it is for and what it
   *  runs, so a forwarded picture still says what it is. */
  function qrPng(inv) {
    var qr = qrMatrix(inv.link);
    var n = qr.getModuleCount(), cell = 10, q = 4;
    var side = (n + q * 2) * cell, foot = 96;
    var cv = document.createElement("canvas");
    cv.width = side; cv.height = side + foot;
    var g = cv.getContext("2d");
    g.fillStyle = "#fff"; g.fillRect(0, 0, cv.width, cv.height);
    g.fillStyle = "#000";
    for (var r = 0; r < n; r++) {
      for (var c = 0; c < n; c++) {
        if (qr.isDark(r, c)) g.fillRect((c + q) * cell, (r + q) * cell, cell, cell);
      }
    }
    g.textAlign = "center";
    g.font = "600 26px system-ui, 'Microsoft JhengHei', sans-serif";
    g.fillText(inv.participant ? inv.participant + " · " + t(inv.test_label) : t(inv.test_label),
               side / 2, side + 30);
    g.fillStyle = "#555";
    g.font = "20px system-ui, 'Microsoft JhengHei', sans-serif";
    g.fillText(t("Scan with your phone's camera"), side / 2, side + 64);
    return new Promise(function (resolve) { cv.toBlob(resolve, "image/png"); });
  }

  function invite(token) {
    return ((state && state.invites) || []).find(function (i) { return i.token === token; });
  }

  /* ── Sent codes ─────────────────────────────────────────────────── */

  function renderLinks() {
    var items = (state && state.invites) || [];
    var live = items.filter(function (i) { return i.state === "live"; }).length;
    el("remote-links-note").textContent = items.length
      ? t("{live} live of {total}", { live: live, total: items.length }) : "";

    // The poll runs every 10 s; rebuilding every QR each time would flicker
    // the codes and drop focus from their buttons.
    var sig = items.map(function (i) {
      return i.token + ":" + i.state + ":" + (i.sessions || []).length;
    }).join("|");
    if (sig === linksSig) return;
    linksSig = sig;

    if (!items.length) {
      el("remote-links").innerHTML = '<div class="rs-empty">' +
        esc(t("No QR codes yet. Create one above, then show it to the person or send them the image.")) +
        "</div>";
      return;
    }

    el("remote-links").innerHTML = items.map(function (inv) {
      var word = t(STATE_WORD[inv.state] || inv.state);
      var got = (inv.sessions || []).length;
      var isLive = inv.state === "live";
      var tok = esc(inv.token);
      return '<div class="rs-row rs-' + esc(inv.state) + (isLive ? " rs-has-qr" : "") + '">' +
        (isLive ? '<div class="rs-qr">' +
          qrSvg(inv.link, t("QR code for {who}", { who: inv.participant || t(inv.test_label) })) +
          "</div>" : "") +
        '<div class="rs-row-body">' +
          '<div class="rs-row-head">' +
            '<span class="rs-badge">' + esc(word) + "</span>" +
            "<b>" + esc(t(inv.test_label)) + "</b>" +
            (inv.participant ? '<span class="rs-who">' + esc(inv.participant) + "</span>" : "") +
            '<span class="rs-meta">' + esc(t("expires")) + " " + esc(when(inv.expires_at)) + "</span>" +
          "</div>" +
          (isLive
            ? '<p class="rs-qr-hint">' +
                esc(t("Have them scan it with their phone's camera, or save the image and send it.")) +
              "</p>" +
              '<div class="rs-actions">' +
                '<button class="btn btn-ghost" onclick="remoteSaveQr(\'' + tok + '\')">' + ICON_SAVE +
                  "<span>" + esc(t("Save image")) + "</span></button>" +
                '<button class="btn btn-ghost" onclick="remoteCopyQr(\'' + tok + '\')">' + ICON_COPY +
                  "<span>" + esc(t("Copy image")) + "</span></button>" +
                '<button class="btn btn-ghost rs-danger" onclick="remoteRevoke(\'' + tok + '\')">' +
                  esc(t("Cancel")) + "</button>" +
              "</div>"
            : "") +
          (got ? '<div class="rs-got">' + I.check + " " +
            esc(t("{n} result(s) received", { n: got })) + "</div>" : "") +
        "</div>" +
        "</div>";
    }).join("");
  }

  /* ── Inbox ──────────────────────────────────────────────────────── */

  function renderInbox() {
    var relay = (state && state.relay) || {};
    el("remote-inbox").innerHTML =
      '<button class="btn btn-primary" onclick="remotePull()"' +
        (relay.configured ? "" : " disabled") + ">" + ICON_INBOX +
        "<span>" + esc(t("Check for new results")) + "</span></button>" +
      '<span class="rs-inbox-note">' +
        esc(relay.configured
          ? t("Filed results appear in Analysis.")
          : t("Connect the inbox to pull results from the cloud.")) + "</span>";
  }

  function render() {
    if (!state) return;
    renderStage();
    renderInbox();
    // The form holds focus and typed text; only rebuild it when the option
    // sets actually change, never on the poll.
    var sig = JSON.stringify(state.tests) + "|" + draft.test + "|" + draft.mode + "|" + draft.lang +
      "|" + ((window.activeProfileId && window.activeProfileId()) || "");
    if (sig !== signature) { signature = sig; renderForm(); }
    renderLinks();
  }

  /* ── Actions (global, for the inline handlers) ──────────────────── */

  window.remoteDraft = function (field, value) {
    draft[field] = value;
    if (field === "test") { draft.mode = ""; render(); }
  };

  window.remoteCreate = async function () {
    if (!draft.participant.trim()) {
      toast(t("Add a first name so you can tell the results apart."), "fail");
      return;
    }
    // Results join this person's history when they arrive (ingest._profile).
    var body = Object.assign({}, draft, {
      profile_id: (window.activeProfileId && window.activeProfileId()) || ""
    });
    await post("invite", body);
  };

  window.remoteRevoke = function (token) { post("revoke", { token: token }); };
  window.remotePull = function () { post("pull", {}); };

  function fileName(inv) {
    var who = String(inv.participant || "invite").replace(/[^\w\u4e00-\u9fff-]+/g, "_");
    return "qr-" + who + "-" + String(inv.test || "test") + ".png";
  }

  window.remoteSaveQr = async function (token) {
    var inv = invite(token);
    if (!inv) return;
    var blob = await qrPng(inv);
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fileName(inv);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  };

  window.remoteCopyQr = function (token) {
    var inv = invite(token);
    if (!inv) return;
    var failed = function () { toast(t("Could not copy the image — use Save image instead."), "fail"); };
    if (!navigator.clipboard || typeof ClipboardItem === "undefined") { failed(); return; }
    // The blob goes in as a promise so the write stays inside the click's
    // user activation (Safari refuses it otherwise).
    navigator.clipboard.write([new ClipboardItem({ "image/png": qrPng(inv) })]).then(
      function () { toast(t("QR code copied — paste it into a message."), "ok"); },
      failed
    );
  };

  /* ── Lifecycle, driven by app.js showPage() ─────────────────────── */

  window.startRemote = function () {
    var icon = el("remote-icon");
    if (icon && !icon.innerHTML) icon.innerHTML = I.broadcast;
    load();
    clearInterval(timer);
    // Slower than the dashboard's 3 s: nothing here changes without a click,
    // except an inbox pull the helper triggered.
    timer = setInterval(load, 10000);
  };

  window.stopRemote = function () { clearInterval(timer); timer = null; };

  if (typeof onLang === "function") {
    onLang(function () { signature = ""; linksSig = ""; if (timer) render(); });
  }
})();
