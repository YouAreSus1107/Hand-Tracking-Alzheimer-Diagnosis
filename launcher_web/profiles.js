/* Patient profiles — who the next test records for, and who an already-saved
   session belongs to.

   A classic script like dev.js / remote.js / report.js, loaded after app.js so
   it shares that file's `I` (icons), `t()` (i18n), `toast()` and `showPage`
   bindings. Never shadow `t` — it is the translator.

   Two surfaces, both deliberately small:

     the chip   a [data-profile] slot beside the camera chip, in the dashboard's
                "Screening Tools" head and every test page's action row. It says
                who is being tested and folds open into the roster. The active
                profile rides down on /api/status, so the chip follows the 3 s
                poll the page already makes — same trick as the camera chip.

     the card   after a run finishes, an inline card above the readings strip
                naming the session just written and who it was filed under, with
                one click to move it. Not a toast: a prompt that disappears on a
                timer is a prompt nobody answers.

   Nothing here decides anything at test time. launcher.py hands the active
   profile to the spawned tool through HAND3D_PROFILE and core/session.py stamps
   a snapshot onto the record, so the test scripts know nothing about profiles
   and a profile edited later never rewrites what a past session said. */
(function () {
  "use strict";

  const SEX = {female:"Female", male:"Male", other:"Other", unspecified:"Not specified"};
  const HAND = {right:"Right-handed", left:"Left-handed",
                ambidextrous:"Ambidextrous", unknown:"Not specified"};

  let roster = [];            // /api/profiles
  let activeSnap = {};        // the snapshot /api/status reports
  let seq = 0;                // radio groups need a unique name per instance
  let view = {mode:"list", id:""};   // the open popover's list / edit form
  let lastIds = null;         // session ids seen before the current run
  let pending = null;         // the session the assign card is offering

  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));

  /* ── Reading the roster ─────────────────────────────────────────── */

  function byId(id){ return roster.find(p => p.id === id) || null; }

  function describe(p){
    if(!p) return "";
    const bits = [];
    if(p.sex && p.sex !== "unspecified") bits.push(t(SEX[p.sex] || p.sex));
    if(p.age_years != null && p.age_years !== "") bits.push(t("age {n}", {n:p.age_years}));
    if(p.dominant_hand && p.dominant_hand !== "unknown")
      bits.push(t(HAND[p.dominant_hand] || p.dominant_hand));
    return bits.join(" · ");
  }

  async function loadRoster(){
    try{
      const r = await fetch("/api/profiles");
      const data = await r.json();
      roster = data.profiles || [];
      if(data.active != null && !activeSnap.id) activeSnap = byId(data.active) || {};
    }catch(e){ roster = roster || []; }
    renderChips(true);
    // The Analysis page and the readings strip both key off the roster.
    try{ window.renderVitals?.(); }catch(e){}
    if(document.getElementById("page-analysis")?.classList.contains("active"))
      try{ window.renderAnalysis?.(); }catch(e){}
  }

  async function post(body){
    const r = await fetch("/api/profiles", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(body)
    });
    const data = await r.json();
    toast(tMsg(data.message) || t(data.ok ? "Done" : "Failed"), data.ok ? "ok" : "fail");
    if(data.profiles) roster = data.profiles;
    if(data.ok && data.active !== undefined) activeSnap = byId(data.active) || {};
    return data;
  }

  /* ── The chip ───────────────────────────────────────────────────── */

  function chipText(){
    return activeSnap && activeSnap.name ? activeSnap.name : t("No profile");
  }

  function listView(name){
    const rows = roster.map(p => {
      const on = activeSnap.id === p.id;
      const detail = describe(p);
      return `<div class="pf-row">
        <label class="pf-opt">
          <input type="radio" name="${name}" value="${esc(p.id)}" ${on?"checked":""}>
          <span class="pf-nm">${esc(p.name)}</span>
          ${detail ? `<span class="pf-sub">${esc(detail)}</span>` : ""}
        </label>
        <button class="pf-edit" type="button" data-edit="${esc(p.id)}"
          aria-label="${t("Edit {name}", {name: esc(p.name)})}">${t("Edit")}</button>
      </div>`;
    }).join("");
    return `<div class="pf-pop-title">${t("Who is being tested")}</div>
      <div class="pf-list">
        <div class="pf-row">
          <label class="pf-opt">
            <input type="radio" name="${name}" value="" ${activeSnap.id?"":"checked"}>
            <span class="pf-nm">${t("No profile")}</span>
            <span class="pf-sub">${t("Sessions save unassigned")}</span>
          </label>
        </div>
        ${rows}
      </div>
      <div class="pf-foot">
        <button class="pf-new btn-mini" type="button">${t("Add a person")}</button>
        <span class="pf-note">${t("Applies to the next launch.")}</span>
      </div>`;
  }

  function opts(map, chosen){
    return Object.keys(map).map(k =>
      `<option value="${k}" ${k===chosen?"selected":""}>${t(map[k])}</option>`).join("");
  }

  function formView(id){
    const p = byId(id) || {sex:"unspecified", dominant_hand:"unknown"};
    return `<div class="pf-pop-title">${id ? t("Edit person") : t("Add a person")}</div>
      <label class="pf-f"><span>${t("Name")}</span>
        <input class="pf-name" type="text" maxlength="60" value="${esc(p.name||"")}"
               placeholder="${t("Name or initials")}"></label>
      <label class="pf-f"><span>${t("Sex")}</span>
        <select class="pf-sex">${opts(SEX, p.sex)}</select></label>
      <label class="pf-f"><span>${t("Age")}</span>
        <input class="pf-age" type="number" min="0" max="120" step="1"
               value="${p.age_years == null ? "" : p.age_years}"></label>
      <label class="pf-f"><span>${t("Dominant hand")}</span>
        <select class="pf-hand">${opts(HAND, p.dominant_hand)}</select></label>
      <div class="pf-foot">
        ${id ? `<button class="pf-del btn-mini" type="button">${t("Remove")}</button>` : ""}
        <span class="pf-note pf-grow"></span>
        <button class="pf-cancel btn-mini" type="button">${t("Back")}</button>
        <button class="pf-save btn-mini" type="button">${t("Save")}</button>
      </div>`;
  }

  function build(root){
    const name = "pf-who-" + (++seq);
    const form = view.mode === "form" && root.classList.contains("open");
    const who = describe(activeSnap);
    const tip = t("Who the next test records for")
      + (activeSnap.name ? " — " + activeSnap.name + (who ? " · " + who : "") : "");
    root.innerHTML = `
      <button class="pf-chip${activeSnap.id?"":" pf-unset"}" type="button"
              aria-expanded="false" aria-haspopup="dialog" title="${esc(tip)}">
        ${I.person}<span class="pf-chip-text">${esc(chipText())}</span>${I.chevron}
      </button>
      <div class="pf-pop" role="dialog" aria-label="${t("Who is being tested")}" hidden>
        ${form ? formView(view.id) : listView(name)}
      </div>`;
    wire(root);
  }

  function wire(root){
    root.querySelector(".pf-chip").addEventListener("click", e => {
      e.stopPropagation();
      toggle(root, !root.classList.contains("open"));
    });
    root.addEventListener("click", e => e.stopPropagation());
    root.addEventListener("keydown", e => {
      if(e.key === "Escape"){ toggle(root, false); root.querySelector(".pf-chip").focus(); }
      if(e.key === "Enter" && e.target.tagName === "INPUT" && view.mode === "form"){
        e.preventDefault();
        save(root);
      }
    });

    // Picking a person is the whole interaction — no Save step for it.
    root.querySelectorAll(".pf-opt input").forEach(input =>
      input.addEventListener("change", () => activate(input.value)));
    root.querySelectorAll("[data-edit]").forEach(b =>
      b.addEventListener("click", () => { view = {mode:"form", id:b.dataset.edit}; rebuild(root); }));
    root.querySelector(".pf-new")?.addEventListener("click",
      () => { view = {mode:"form", id:""}; rebuild(root); });
    root.querySelector(".pf-cancel")?.addEventListener("click",
      () => { view = {mode:"list", id:""}; rebuild(root); });
    root.querySelector(".pf-save")?.addEventListener("click", () => save(root));
    root.querySelector(".pf-del")?.addEventListener("click", () => remove(root));
  }

  /* Rebuild one open popover in place: the chip stays open and focused, which
     is what an Edit / Cancel / Save step inside it needs. */
  function rebuild(root){
    const open = root.classList.contains("open");
    root.classList.add("open");         // build() renders the form only for it
    build(root);
    root.classList.toggle("open", open);
    delete root.dataset.pfSig;      // force the next poll to agree with the DOM
    if(open) toggle(root, true, true);
  }

  /* Signature-guarded like renderCamChips(): the setting *and* its rendered
     text, so a language switch rebuilds but the 3 s poll does not churn the
     DOM — and never a chip the person has open, which would wipe the form. */
  function renderChips(force){
    const sig = [activeSnap.id || "", activeSnap.name || "", roster.length,
                 chipText()].join("|");
    // Only reset the view when nothing is open: a rebuild of a hidden chip on
    // another page must not drop the form somebody is typing into here.
    if(!document.querySelector("[data-profile].open")) view = {mode:"list", id:""};
    document.querySelectorAll("[data-profile]").forEach(root => {
      if(root.classList.contains("open")) return;
      if(!force && root.dataset.pfSig === sig) return;
      build(root);
      root.dataset.pfSig = sig;
    });
  }

  function toggle(root, open, keepView){
    if(open) closeAll(root);
    if(!open && !keepView && view.mode === "form"){
      view = {mode:"list", id:""};      // a closed form starts fresh next time
      build(root);
    }
    root.classList.toggle("open", open);
    root.querySelector(".pf-pop").hidden = !open;
    root.querySelector(".pf-chip").setAttribute("aria-expanded", String(open));
    if(open){
      const first = root.querySelector(".pf-name") || root.querySelector(".pf-opt input");
      first?.focus();
    }
  }

  function closeAll(except){
    document.querySelectorAll("[data-profile].open").forEach(r => {
      if(r !== except) toggle(r, false);
    });
  }
  document.addEventListener("click", () => closeAll());
  document.addEventListener("keydown", e => { if(e.key === "Escape") closeAll(); });

  /* ── Editing ────────────────────────────────────────────────────── */

  async function activate(id){
    const data = await post({action:"activate", id});
    if(!data.ok) return;
    closeAll();
    renderChips(true);
    refreshViews();
  }

  /* The two form actions, shared by the chip's popover and the Analysis
     page's editor: same fields, same validation, one round trip. Each caller
     decides only what to do with the answer. */
  function commit(root, id){
    return post({action:"save", profile:{
      id,
      name: root.querySelector(".pf-name").value.trim(),
      sex: root.querySelector(".pf-sex").value,
      age_years: root.querySelector(".pf-age").value,
      dominant_hand: root.querySelector(".pf-hand").value,
    }});
  }

  /* Two clicks, not a browser confirm(): removing a person is worth a pause,
     and a native modal blocks the whole page to say so. */
  function armed(btn){
    if(btn.classList.contains("armed")) return true;
    btn.classList.add("armed");
    btn.textContent = t("Confirm removal");
    btn.title = t("Their saved sessions stay, and keep the name they were recorded under.");
    return false;
  }

  async function save(root){
    const isNew = !view.id;
    const data = await commit(root, view.id);
    if(!data.ok) return;                  // leave the form open to be fixed
    // Somebody who just added a person is about to test them.
    if(isNew && data.profile && data.profile.id) return activate(data.profile.id);
    view = {mode:"list", id:""};
    rebuild(root);
    refreshViews();
  }

  async function remove(root){
    if(!armed(root.querySelector(".pf-del"))) return;
    const data = await post({action:"delete", id: view.id});
    if(!data.ok) return;
    view = {mode:"list", id:""};
    rebuild(root);
    refreshViews();
  }

  /* Everything that reads the roster or the person filter. */
  function refreshViews(){
    try{ renderVitals(); }catch(e){ console.error(e); }
    if(document.getElementById("page-analysis")?.classList.contains("active"))
      try{ renderAnalysis(); }catch(e){ console.error(e); }
  }

  /* ── The Analysis page's editor ─────────────────────────────────── */

  /* The chip is where you say who is being tested; the Analysis page is where
     you read a person's history, and that is where you notice their details
     are wrong. Same form, mounted inline instead of in a popover — a chip on
     that page would mean "who is being tested", which is not what this is. */
  let editing = "";              // "" while closed; "new" or a profile id

  function openEditor(id){
    const el = document.getElementById("analysis-editor");
    if(!el) return;
    editing = id || "new";
    el.innerHTML = `<div class="pf-editor">${formView(id || "")}</div>`;
    el.hidden = false;
    wireEditor(el);
    el.querySelector(".pf-name")?.focus();
  }

  function closeEditor(){
    const el = document.getElementById("analysis-editor");
    editing = "";
    if(el){ el.hidden = true; el.innerHTML = ""; }
  }

  function wireEditor(el){
    const id = editing === "new" ? "" : editing;
    el.querySelector(".pf-cancel").addEventListener("click", closeEditor);
    el.querySelector(".pf-save").addEventListener("click", () => saveEditor(el, id));
    el.querySelector(".pf-del")?.addEventListener("click", () => removeEditor(el, id));
    el.addEventListener("keydown", e => {
      if(e.key === "Escape") closeEditor();
      if(e.key === "Enter" && e.target.tagName === "INPUT"){
        e.preventDefault();
        saveEditor(el, id);
      }
    });
  }

  async function saveEditor(el, id){
    const data = await commit(el, id);
    if(!data.ok) return;                  // leave the form open to be fixed
    closeEditor();
    // Adding somebody here means the same thing it means on the chip: they are
    // the person you are about to test.
    if(!id && data.profile && data.profile.id) return activate(data.profile.id);
    renderChips(true);
    refreshViews();
  }

  async function removeEditor(el, id){
    if(!armed(el.querySelector(".pf-del"))) return;
    const data = await post({action:"delete", id});
    if(!data.ok) return;
    closeEditor();
    renderChips(true);
    // profileFilter() drops a pin whose person no longer has sessions, so the
    // page cannot strand itself on the profile that was just removed.
    refreshViews();
  }

  /* ── After a run ────────────────────────────────────────────────── */

  /* app.js spots the moment a tool exits. The session it wrote is whichever id
     is new since the last look, which is also how this stays right when a run
     is stopped before it saved anything: nothing new, nothing to offer. */
  async function afterRun(){
    const before = new Set((analysisSessions || []).map(s => s.session_id));
    await loadVitals(true);
    const fresh = (analysisSessions || []).filter(s => !before.has(s.session_id));
    refreshViews();
    if(!fresh.length) return;
    pending = fresh[fresh.length - 1];
    renderAssign();
  }

  function renderAssign(){
    const el = document.getElementById("run-assign");
    if(!el) return;
    if(!pending){ el.hidden = true; el.innerHTML = ""; return; }

    const cfg = TREND[pending.test] || {label: pending.test, icon: "chart"};
    const who = pending.profile && pending.profile.name;
    const chosen = (pending.profile && pending.profile.id) || "";
    const options = [`<option value="">${t("No profile")}</option>`].concat(
      roster.map(p => `<option value="${esc(p.id)}" ${p.id===chosen?"selected":""}
        >${esc(p.name)}</option>`)).join("");

    el.innerHTML = `<span class="ra-ic">${I.check}</span>
      <div class="ra-text">
        <b>${t("{name} saved", {name: t(cfg.label)})}</b>
        <span>${who ? t("Recorded for {name}", {name: esc(who)})
                    : t("Saved with no profile set.")}</span>
      </div>
      <label class="ra-pick">
        <span>${t("Who took this test?")}</span>
        <select class="ra-sel">${options}</select>
      </label>
      <button class="ra-keep btn-mini" type="button">${t("Keep")}</button>
      <button class="ra-x" type="button" aria-label="${t("Dismiss")}">${I.x}</button>`;
    el.hidden = false;

    const done = () => { pending = null; renderAssign(); };
    el.querySelector(".ra-keep").addEventListener("click", done);
    el.querySelector(".ra-x").addEventListener("click", done);
    el.querySelector(".ra-sel").addEventListener("change", async ev => {
      const ok = await assign(pending.session_id, ev.target.value);
      if(ok) done();
    });
  }

  /* ── Moving a saved session ─────────────────────────────────────── */

  /* Used by the card above and by the report panel. Patches the session in
     place rather than refetching the lot: /api/sessions is the whole history,
     and one field changed. */
  async function assign(sessionId, profileId){
    try{
      const r = await fetch("/api/session/profile", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({id: sessionId, profile_id: profileId || ""})
      });
      const data = await r.json();
      toast(tMsg(data.message) || t(data.ok ? "Done" : "Failed"), data.ok ? "ok" : "fail");
      if(!data.ok) return false;
      const snap = data.profile || {};
      (analysisSessions || []).forEach(s => {
        if(s.session_id === sessionId) s.profile = snap;
      });
      if(pending && pending.session_id === sessionId) pending.profile = snap;
      window.forgetReport?.(sessionId);
      refreshViews();
      return true;
    }catch(e){
      toast(t("Request failed"), "fail");
      return false;
    }
  }

  /* ── Exports ────────────────────────────────────────────────────── */

  // app.js owns the status poll; the snapshot it reports is the source of
  // truth for which profile is active, exactly as it is for the camera.
  window.setActiveProfile = function (snap) {
    const next = snap && snap.id ? snap : {};
    if((activeSnap.id || "") !== (next.id || "") || activeSnap.name !== next.name){
      const moved = (activeSnap.id || "") !== (next.id || "");
      activeSnap = next;
      renderChips(true);
      // The readings strip defaults to whoever is being tested, so it follows.
      if(moved) refreshViews();
    } else {
      renderChips(false);
    }
  };
  window.renderProfileChips = renderChips;
  window.profileList = () => roster;
  window.activeProfileId = () => activeSnap.id || "";
  window.profileById = id => byId(id);
  window.describeProfile = describe;
  window.assignSession = assign;
  window.reloadProfiles = loadRoster;
  window.openProfileEditor = openEditor;
  window.closeProfileEditor = closeEditor;
  window.afterRun = afterRun;

  loadRoster();
})();
