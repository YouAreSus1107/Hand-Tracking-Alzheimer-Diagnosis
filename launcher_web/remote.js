/* Remote Sessions page — mint a link, watch what comes back.
   docs/REMOTE_SESSION_PLAN.md

   A classic script like dev.js, loaded after app.js so it shares that file's
   `I` (icons), `t`/`tMsg` (i18n) and `toast()` bindings. app.js's showPage()
   starts and stops the poll, so nothing here runs while the page is off
   screen. Never shadow `t` — it is the translator. */
(function () {
  "use strict";

  var ICON_LINK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>';
  var ICON_INBOX = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h5l2 3h4l2-3h5"/><path d="M5.5 5h13l2.5 7v7H3v-7z"/></svg>';

  var state = null;        // last /api/remote/state payload
  var timer = null;
  var signature = "";      // rebuild the list only when it actually changed
  var draft = { test: "iiv", mode: "max", lang: "en", participant: "", ttl_hours: 48, uses: 1 };

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
      esc(t("Links can be created and the results path can be tested locally, but nothing is pulled from the cloud until these are set:")) +
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
      '<button class="btn btn-primary rs-create" onclick="remoteCreate()">' + ICON_LINK +
        "<span>" + esc(t("Create link")) + "</span></button>";
  }

  /* ── Sent links ─────────────────────────────────────────────────── */

  var STATE_WORD = {
    live: "Live", spent: "Used", expired: "Expired", revoked: "Cancelled"
  };

  function when(stamp) {
    var d = new Date(stamp);
    return isNaN(d) ? String(stamp || "") : d.toLocaleString();
  }

  function renderLinks() {
    var items = (state && state.invites) || [];
    var live = items.filter(function (i) { return i.state === "live"; }).length;
    el("remote-links-note").textContent = items.length
      ? t("{live} live of {total}", { live: live, total: items.length }) : "";

    if (!items.length) {
      el("remote-links").innerHTML = '<div class="rs-empty">' +
        esc(t("No links yet. Create one above and send it however you normally message that person.")) +
        "</div>";
      return;
    }

    el("remote-links").innerHTML = items.map(function (inv) {
      var word = t(STATE_WORD[inv.state] || inv.state);
      var got = (inv.sessions || []).length;
      return '<div class="rs-row rs-' + esc(inv.state) + '">' +
        '<div class="rs-row-head">' +
          '<span class="rs-badge">' + esc(word) + "</span>" +
          '<b>' + esc(t(inv.test_label)) + "</b>" +
          (inv.participant ? '<span class="rs-who">' + esc(inv.participant) + "</span>" : "") +
          '<span class="rs-meta">' + esc(t("expires")) + " " + esc(when(inv.expires_at)) + "</span>" +
        "</div>" +
        '<div class="rs-link"><code>' + esc(inv.link) + "</code>" +
          '<button class="btn btn-ghost" onclick="remoteCopy(\'' + esc(inv.token) + '\')">' +
            esc(t("Copy")) + "</button>" +
          (inv.state === "live"
            ? '<button class="btn btn-ghost rs-danger" onclick="remoteRevoke(\'' + esc(inv.token) +
              '\')">' + esc(t("Cancel")) + "</button>"
            : "") +
        "</div>" +
        (got ? '<div class="rs-got">' + I.check + " " +
          esc(t("{n} result(s) received", { n: got })) + "</div>" : "") +
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
    var sig = JSON.stringify(state.tests) + "|" + draft.test + "|" + draft.mode + "|" + draft.lang;
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
    await post("invite", draft);
  };

  window.remoteRevoke = function (token) { post("revoke", { token: token }); };
  window.remotePull = function () { post("pull", {}); };

  window.remoteCopy = function (token) {
    var inv = ((state && state.invites) || []).find(function (i) { return i.token === token; });
    if (!inv) return;
    navigator.clipboard.writeText(inv.link).then(
      function () { toast(t("Link copied."), "ok"); },
      function () { toast(t("Could not copy — select the link and copy it."), "fail"); }
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
    onLang(function () { signature = ""; if (timer) render(); });
  }
})();
