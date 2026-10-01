/* Patient profiles — who the next test records for, and who an already-saved
   session belongs to.

   A classic script like dev.js / remote.js / report.js, loaded after app.js so
   it shares that file's `I` (icons), `t()` (i18n), `toast()` and `showPage`
   bindings. Never shadow `t` — it is the translator.

   Four surfaces:

     the switcher  one [data-profile-nav] control in the navbar: the active
                   person's avatar and name, folding open into the roster. The
                   active profile rides down on /api/status, so it follows the
                   3 s poll the page already makes — same trick as the camera
                   chip. It replaced a small pill repeated beside every camera
                   chip, which read as a device setting and was easy to miss.

     the picker    Launch with nobody set (and a roster to pick from) asks
                   "Who is taking this test?" first, as a sheet of large
                   tiles. The pick rides in the launch request itself
                   (profile_id), so it cannot lose a race with the POST that
                   would otherwise persist it.

     the form      a centred sheet, shared by the switcher and the Analysis
                   page's Add / Edit buttons.

     the card      after a run finishes, an inline card above the readings
                   strip naming the session just written and who it was filed
                   under, with one click to move it. Not a toast: a prompt that
                   disappears on a timer is a prompt nobody answers.

   A profile is a person or a **group**. A group is a guest pool (a screening
   day, a care home's visitors): its runs are kept together but are never one
   person's trend, so it has no sex/age/hand and the Analysis page draws it
   without a line (core/profiles.py).

   Nothing here decides anything at test time. launcher.py hands the active
   profile to the spawned tool through HAND3D_PROFILE and core/session.py stamps
   a snapshot onto the record, so the test scripts know nothing about profiles
   and a profile edited later never rewrites what a past session said. */
(function () {
  "use strict";

  const SEX = {female:"Female", male:"Male", other:"Other", unspecified:"Not specified"};
  const HAND = {right:"Right-handed", left:"Left-handed",
                ambidextrous:"Ambidextrous", unknown:"Not specified"};
  // Shorter labels for the segmented buttons in the form.
  const HAND_SEG = {right:"Right", left:"Left", ambidextrous:"Both", unknown:"Not specified"};
  const AV_COLORS = 8;                // --av-1..8 in styles.css
  const SEARCH_FROM = 9;              // a search box once the roster is this long
  const STALE_MONTHS = 12;            // an age entered longer ago is flagged
  const SKIP_KEY = "hand3d.pf.skipPicker";

  // Icons only this file uses; the shared set lives in app.js's `I`.
  const svg = (body, w = 2) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true">${body}</svg>`;
  const PI = {
    users: svg('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20v-.5A5.5 5.5 0 0 1 8 14h2a5.5 5.5 0 0 1 5.5 5.5v.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18 14a5.5 5.5 0 0 1 3.5 5.5v.5"/>'),
    pencil: svg('<path d="M17 3a2.1 2.1 0 0 1 3 3L7.5 18.5 3 20l1.5-4.5Z"/>'),
    plus: svg('<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>', 2.4),
    alert: svg('<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
    search: svg('<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>'),
    check: svg('<polyline points="20 6 9 17 4 12"/>', 2.6),
    user: svg('<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>'),
  };

  let roster = [];            // /api/profiles
  let activeSnap = {};        // the snapshot /api/status reports
  let pending = null;         // the session the assign card is offering

  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));

  /* ── Reading the roster ─────────────────────────────────────────── */

  function byId(id){ return roster.find(p => p.id === id) || null; }
  const isGroup = p => !!p && p.kind === "group";

  /* Months since a "YYYY-MM" stamp, or null. */
  function monthsSince(stamp){
    const m = /^(\d{4})-(\d{2})$/.exec(stamp || "");
    if(!m) return null;
    const now = new Date();
    return (now.getFullYear() - +m[1]) * 12 + (now.getMonth() + 1 - +m[2]);
  }

  /* One short tag for a roster row: the age, or "Group". A stale age says
     which year it was entered, so "73" a year on does not pass for today. */
  function tag(p){
    if(!p) return "";
    if(isGroup(p)) return t("Group");
    if(p.age_years == null || p.age_years === "") return "";
    const age = t("age {n}", {n: p.age_years});
    const old = monthsSince(p.age_set);
    return old != null && old >= STALE_MONTHS ? `${age} (${p.age_set.slice(0, 4)})` : age;
  }

  /* The full line (Analysis page, tooltips): sex · age · hand. */
  function describe(p){
    if(!p) return "";
    if(isGroup(p)) return [t("Group"), p.note].filter(Boolean).join(" · ");
    const bits = [];
    if(p.sex && p.sex !== "unspecified") bits.push(t(SEX[p.sex] || p.sex));
    if(p.age_years != null && p.age_years !== "") bits.push(t("age {n}", {n:p.age_years}));
    if(p.dominant_hand && p.dominant_hand !== "unknown")
      bits.push(t(HAND[p.dominant_hand] || p.dominant_hand));
    return bits.join(" · ");
  }

  /* ── Avatars ────────────────────────────────────────────────────── */

  const CJK = /[㐀-鿿豈-﫿぀-ヿ가-힯]/;

  /* Two Latin initials ("Jane Chen" → "JC", "testing" → "TE"), or the first
     character of a CJK name, which is already a whole syllable (股公 → 股). */
  function initials(name){
    const s = String(name || "").trim();
    if(!s) return "?";
    if(CJK.test(s[0])) return s[0];
    const words = s.split(/\s+/).filter(Boolean);
    const out = words.length > 1 ? words[0][0] + words[1][0] : s.slice(0, 2);
    return out.toUpperCase();
  }

  /* The profile's own hue, else one derived from its id so it never changes
     between visits. The palette avoids the status colours on purpose. */
  function hue(p){
    const c = +(p && p.color) || 0;
    if(c >= 1 && c <= AV_COLORS) return c;
    let h = 0;
    for(const ch of String((p && (p.id || p.name)) || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return (h % AV_COLORS) + 1;
  }

  /* size: "xs" 18 · "sm" 28 · "md" 34 · "lg" 52. Decorative: the name always
     sits beside it, so it is hidden from assistive tech. */
  function avatar(p, size){
    const cls = `pf-av pf-av-${size || "sm"}`;
    if(!p || !p.name)
      return `<span class="${cls} pf-av-none" aria-hidden="true">${PI.user}</span>`;
    const style = `style="--av:var(--av-${hue(p)})"`;
    if(isGroup(p))
      return `<span class="${cls} pf-av-group" ${style} aria-hidden="true">${PI.users}</span>`;
    return `<span class="${cls}" ${style} aria-hidden="true">${esc(initials(p.name))}</span>`;
  }

  /* ── Server ─────────────────────────────────────────────────────── */

  async function loadRoster(){
    try{
      const r = await fetch("/api/profiles");
      const data = await r.json();
      roster = data.profiles || [];
      if(data.active != null && !activeSnap.id) activeSnap = byId(data.active) || {};
    }catch(e){ roster = roster || []; }
    renderChips(true);
    refreshLaunch();
    // The Analysis page and the readings strip both key off the roster.
    try{ window.renderVitals?.(); }catch(e){}
    if(document.getElementById("page-analysis")?.classList.contains("active"))
      try{ window.renderAnalysis?.(); }catch(e){}
  }

  async function post(body, quiet){
    const r = await fetch("/api/profiles", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(body)
    });
    const data = await r.json();
    if(!quiet || !data.ok)
      toast(tMsg(data.message) || t(data.ok ? "Done" : "Failed"), data.ok ? "ok" : "fail");
    if(data.profiles) roster = data.profiles;
    if(data.ok && data.active !== undefined) activeSnap = byId(data.active) || {};
    return data;
  }

  /* The Launch buttons name the person, so they follow every change of who. */
  function refreshLaunch(){ try{ window.refreshLaunchButtons?.(); }catch(e){ console.error(e); } }

  /* ── The navbar switcher ────────────────────────────────────────── */

  function whoButton(){
    const on = !!activeSnap.id;
    const nobody = !on && roster.length;
    // Unset with people on the roster is the case that files runs wrongly, so
    // it is the one that stands out: amber, an icon and words, never colour alone.
    const cls = on ? "" : nobody ? " pf-unset" : " pf-empty";
    const face = on ? avatar(activeSnap, "sm")
      : nobody ? `<span class="pf-alert">${PI.alert}</span>`
      : `<span class="pf-alert pf-alert-add">${PI.plus}</span>`;
    const label = on ? (isGroup(activeSnap) ? t("Group") : t("Testing"))
      : nobody ? t("Who is testing?") : t("Profiles");
    const name = on ? esc(activeSnap.name) : nobody ? t("Choose a person") : t("Add a person");
    const tip = t("Who the next test records for")
      + (on ? ": " + activeSnap.name + (describe(activeSnap) ? " · " + describe(activeSnap) : "") : "");
    return `<button class="pf-who${cls}" type="button" aria-haspopup="dialog"
        aria-expanded="false" title="${esc(tip)}">
        ${face}
        <span class="pf-who-text"><span class="pf-who-lbl">${label}</span>
          <span class="pf-who-nm">${name}</span></span>${I.chevron}
      </button>`;
  }

  function row(p){
    const on = activeSnap.id === p.id;
    const tg = tag(p);
    return `<div class="pf-row${on ? " on" : ""}" data-name="${esc(String(p.name).toLowerCase())}">
        <button class="pf-pick" type="button" data-pick="${esc(p.id)}" aria-pressed="${on}">
          ${avatar(p, "md")}
          <span class="pf-row-text"><span class="pf-nm">${esc(p.name)}</span>
            ${tg ? `<span class="pf-tag">${esc(tg)}</span>` : ""}</span>
          ${on ? `<span class="pf-on">${PI.check}</span>` : ""}
        </button>
        <button class="pf-edit" type="button" data-edit="${esc(p.id)}"
          aria-label="${esc(t("Edit {name}", {name: p.name}))}" title="${esc(t("Edit"))}">${PI.pencil}</button>
      </div>`;
  }

  function rosterView(){
    const people = roster.filter(p => !isGroup(p));
    const groups = roster.filter(isGroup);
    const none = !activeSnap.id;
    return `<div class="pf-pop-head">
        <span class="pf-pop-title">${t("Who is being tested")}</span>
        <span class="pf-pop-note">${t("Applies to the next launch.")}</span>
      </div>
      ${roster.length >= SEARCH_FROM ? `<label class="pf-search">${PI.search}
        <input type="search" placeholder="${esc(t("Find a person"))}"
               aria-label="${esc(t("Find a person"))}"></label>` : ""}
      <div class="pf-list">
        ${people.map(row).join("")}
        ${groups.length ? `<div class="pf-sec">${t("Groups")}</div>${groups.map(row).join("")}` : ""}
        ${roster.length ? `<div class="pf-row pf-row-none${none ? " on" : ""}" data-name="">
          <button class="pf-pick" type="button" data-pick="" aria-pressed="${none}">
            ${avatar(null, "md")}
            <span class="pf-row-text"><span class="pf-nm">${t("No profile")}</span>
              <span class="pf-tag">${t("Sessions save unassigned")}</span></span>
            ${none ? `<span class="pf-on">${PI.check}</span>` : ""}
          </button></div>`
          : `<p class="pf-empty-note">${t("Add the people you test, so each one gets their own history.")}</p>`}
      </div>
      <div class="pf-foot">
        <button class="pf-new" type="button" data-new="person">${PI.plus}${t("Add a person")}</button>
        <button class="pf-new" type="button" data-new="group">${PI.plus}${t("Add a group")}</button>
      </div>`;
  }

  function build(root){
    root.innerHTML = `${whoButton()}
      <div class="pf-pop" role="dialog" aria-label="${esc(t("Who is being tested"))}" hidden>
        ${rosterView()}
      </div>`;
    wire(root);
  }

  function wire(root){
    root.querySelector(".pf-who").addEventListener("click", e => {
      e.stopPropagation();
      toggle(root, !root.classList.contains("open"));
    });
    root.addEventListener("click", e => e.stopPropagation());
    root.addEventListener("keydown", e => {
      if(e.key === "Escape"){ toggle(root, false); root.querySelector(".pf-who").focus(); }
    });
    // Picking a person is the whole interaction — no Save step for it.
    root.querySelectorAll("[data-pick]").forEach(b =>
      b.addEventListener("click", () => activate(b.dataset.pick)));
    root.querySelectorAll("[data-edit]").forEach(b =>
      b.addEventListener("click", () => { toggle(root, false); openForm(b.dataset.edit); }));
    root.querySelectorAll("[data-new]").forEach(b =>
      b.addEventListener("click", () => { toggle(root, false); openForm("", {kind: b.dataset.new}); }));
    // Filters in place: a rebuild would drop the focus from the box.
    root.querySelector(".pf-search input")?.addEventListener("input", e => {
      const q = e.target.value.trim().toLowerCase();
      root.querySelectorAll(".pf-row").forEach(r => {
        r.hidden = !!q && !(r.dataset.name || "").includes(q);
      });
      root.querySelectorAll(".pf-sec").forEach(s => { s.hidden = !!q; });
    });
  }

  /* Signature-guarded like renderCamChips(): the setting *and* its rendered
     text, so a language switch rebuilds but the 3 s poll does not churn the
     DOM — and never a switcher the person has open. */
  function renderChips(force){
    const sig = [activeSnap.id || "", activeSnap.name || "",
                 roster.map(p => [p.id, p.name, p.kind, p.color, p.age_years, p.age_set].join(":")).join(","),
                 t("Who is being tested")].join("|");
    document.querySelectorAll("[data-profile-nav]").forEach(root => {
      if(root.classList.contains("open")){
        // Caught up when it closes (toggle()), not under the person's cursor.
        if(root.dataset.pfSig !== sig) root.dataset.pfStale = "1";
        return;
      }
      if(!force && root.dataset.pfSig === sig) return;
      build(root);
      root.dataset.pfSig = sig;
    });
  }

  function toggle(root, open){
    if(open) closeAll(root);
    root.classList.toggle("open", open);
    root.querySelector(".pf-pop").hidden = !open;
    root.querySelector(".pf-who").setAttribute("aria-expanded", String(open));
    if(open){
      const first = root.querySelector(".pf-search input")
        || root.querySelector(".pf-row.on .pf-pick") || root.querySelector(".pf-pick");
      first?.focus();
    } else if(root.dataset.pfStale){
      // A change landed while it was open; catch up now it is closed.
      delete root.dataset.pfStale;
      renderChips(true);
    }
  }

  function closeAll(except){
    document.querySelectorAll("[data-profile-nav].open").forEach(r => {
      if(r !== except) toggle(r, false);
    });
  }
  document.addEventListener("click", () => closeAll());
  document.addEventListener("keydown", e => { if(e.key === "Escape") closeAll(); });

  async function activate(id){
    const data = await post({action:"activate", id});
    if(!data.ok) return;
    closeAll();
    renderChips(true);
    refreshLaunch();
    refreshViews();
  }

  /* ── The sheet (form and launch picker share it) ────────────────── */

  let sheetEl = null, backEl = null, sheetClose = null, sheetReturn = null;

  function openSheet(html, onClose, label){
    closeSheet();
    sheetReturn = document.activeElement;
    backEl = document.createElement("div");
    backEl.className = "pf-backdrop";
    sheetEl = document.createElement("div");
    sheetEl.className = "pf-sheet";
    sheetEl.setAttribute("role", "dialog");
    sheetEl.setAttribute("aria-modal", "true");
    sheetEl.setAttribute("aria-label", label || "");
    sheetEl.innerHTML = html;
    document.body.append(backEl, sheetEl);
    sheetClose = onClose || null;
    backEl.addEventListener("click", closeSheet);
    sheetEl.addEventListener("click", e => e.stopPropagation());
    sheetEl.addEventListener("keydown", e => {
      if(e.key === "Escape"){ e.stopPropagation(); closeSheet(); }
      if(e.key === "Tab") trapFocus(e);
    });
    requestAnimationFrame(() => { backEl?.classList.add("on"); sheetEl?.classList.add("on"); });
    return sheetEl;
  }

  function closeSheet(){
    if(!sheetEl) return;
    const s = sheetEl, b = backEl, done = sheetClose, back = sheetReturn;
    sheetEl = backEl = sheetClose = sheetReturn = null;
    s.remove(); b.remove();
    try{ back?.focus?.(); }catch(e){}
    done?.();
  }

  function trapFocus(e){
    const f = [...sheetEl.querySelectorAll("button,input,select,textarea,[tabindex]")]
      .filter(el => !el.disabled && el.offsetParent !== null && el.tabIndex >= 0);
    if(!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if(e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
    else if(!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
  }

  /* ── The form ───────────────────────────────────────────────────── */

  function seg(field, map, chosen, label){
    return `<div class="pf-f"><span class="pf-f-lbl" id="pf-l-${field}">${label}</span>
      <div class="pf-seg" role="radiogroup" aria-labelledby="pf-l-${field}" data-field="${field}">
        ${Object.keys(map).map(k => `<button type="button" role="radio"
            aria-checked="${k === chosen}" data-v="${k}">${t(map[k])}</button>`).join("")}
      </div></div>`;
  }

  function swatches(p){
    const cur = hue(p);
    let out = "";
    for(let i = 1; i <= AV_COLORS; i++)
      out += `<button type="button" role="radio" aria-checked="${i === cur}" data-v="${i}"
        style="--av:var(--av-${i})" aria-label="${esc(t("Colour {n}", {n: i}))}"></button>`;
    return `<div class="pf-f"><span class="pf-f-lbl" id="pf-l-color">${t("Colour")}</span>
      <div class="pf-swatches" role="radiogroup" aria-labelledby="pf-l-color" data-field="color">${out}</div></div>`;
  }

  function monthLabel(stamp){
    const m = /^(\d{4})-(\d{2})$/.exec(stamp || "");
    if(!m) return "";
    try{
      return new Date(+m[1], +m[2] - 1, 1).toLocaleDateString(
        getLang() === "zh" ? "zh-TW" : "en-GB", {year:"numeric", month:"short"});
    }catch(e){ return stamp; }
  }

  function ageHint(p){
    if(p.age_years == null || !p.age_set) return "";
    const old = monthsSince(p.age_set);
    const when = t("Entered {when}", {when: monthLabel(p.age_set)});
    return old != null && old >= STALE_MONTHS
      ? `<span class="pf-hint pf-hint-warn">${PI.alert}${when}. ${t("Check the age is still right.")}</span>`
      : `<span class="pf-hint">${when}</span>`;
  }

  function formView(id, preset){
    const p = byId(id) || Object.assign({sex:"unspecified", dominant_hand:"unknown",
                                         kind:"person", id:"", name:""}, preset || {});
    const group = isGroup(p);
    const title = id ? (group ? t("Edit group") : t("Edit person"))
                     : (group ? t("Add a group") : t("Add a person"));
    return `<div class="pf-sheet-head">
        <span class="pf-preview">${avatar(Object.assign({}, p, {name: p.name || "?"}), "lg")}</span>
        <div><h2 class="pf-sheet-title">${title}</h2>
          <p class="pf-sheet-sub">${group
            ? t("Runs from different people, kept together. They are never charted as one person's trend.")
            : t("Each person gets their own history on the Analysis page.")}</p></div>
      </div>
      <div class="pf-sheet-body">
        ${seg("kind", {person:"Person", group:"Group"}, group ? "group" : "person", t("Type"))}
        <label class="pf-f"><span class="pf-f-lbl">${t("Name")}</span>
          <input class="pf-name" type="text" maxlength="60" value="${esc(p.name || "")}"
                 placeholder="${esc(group ? t("e.g. Screening day, Hall B") : t("Name or initials"))}"></label>
        <div class="pf-person"${group ? " hidden" : ""}>
          ${seg("sex", SEX, p.sex || "unspecified", t("Sex"))}
          <div class="pf-f"><label class="pf-f-lbl" for="pf-age">${t("Age")}</label>
            <div class="pf-age-wrap">
              <input class="pf-age" id="pf-age" type="number" min="0" max="120" step="1"
                     inputmode="numeric" value="${p.age_years == null ? "" : p.age_years}">
              ${ageHint(p)}
            </div></div>
          ${seg("hand", HAND_SEG, p.dominant_hand || "unknown", t("Dominant hand"))}
        </div>
        <label class="pf-f pf-group"${group ? "" : " hidden"}><span class="pf-f-lbl">${t("Note")}</span>
          <input class="pf-note-in" type="text" maxlength="120" value="${esc(p.note || "")}"
                 placeholder="${esc(t("Where or when, e.g. Community centre, October"))}"></label>
        ${swatches(p)}
      </div>
      <div class="pf-sheet-foot">
        ${id ? `<button class="pf-del btn-mini" type="button">${t("Remove")}</button>` : ""}
        <span class="pf-grow"></span>
        <button class="pf-cancel btn-mini" type="button">${t("Cancel")}</button>
        <button class="pf-save btn btn-primary" type="button">${t("Save")}</button>
      </div>`;
  }

  /* opts.then(profile): what to do after a new profile is saved. Default:
     make them active, since somebody who just added a person is about to
     test them. */
  function openForm(id, opts){
    opts = opts || {};
    const p = byId(id);
    // An existing profile keeps "auto" (0) until a swatch is touched; a new one
    // is dealt the next colour round, so a fresh roster is not all one hue.
    let color = p ? (+p.color || 0) : (roster.length % AV_COLORS) + 1;
    const el = openSheet(formView(id, {kind: opts.kind || "person", color}), null,
      id ? t("Edit person") : t("Add a person"));

    const preview = () => {
      const kind = segVal(el, "kind");
      el.querySelector(".pf-preview").innerHTML = avatar({
        id: id || "new", kind, color: color || hue(p),
        name: el.querySelector(".pf-name").value || "?"}, "lg");
    };
    el.querySelectorAll(".pf-seg, .pf-swatches").forEach(g => {
      g.querySelectorAll("[role=radio]").forEach(b => b.addEventListener("click", () => {
        g.querySelectorAll("[role=radio]").forEach(x =>
          x.setAttribute("aria-checked", String(x === b)));
        if(g.dataset.field === "color") color = +b.dataset.v;
        if(g.dataset.field === "kind"){
          const group = b.dataset.v === "group";
          el.querySelector(".pf-person").hidden = group;
          el.querySelector(".pf-group").hidden = !group;
          el.querySelector(".pf-sheet-sub").textContent = group
            ? t("Runs from different people, kept together. They are never charted as one person's trend.")
            : t("Each person gets their own history on the Analysis page.");
        }
        preview();
      }));
      // Arrow keys move within a group, as a radiogroup should.
      g.addEventListener("keydown", e => {
        if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(e.key)) return;
        const bs = [...g.querySelectorAll("[role=radio]")];
        const i = bs.indexOf(document.activeElement);
        if(i < 0) return;
        e.preventDefault();
        const next = bs[(i + (e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1) + bs.length) % bs.length];
        next.focus(); next.click();
      });
    });
    el.querySelector(".pf-name").addEventListener("input", preview);
    el.querySelector(".pf-cancel").addEventListener("click", closeSheet);
    el.querySelector(".pf-save").addEventListener("click", () => save(el, id, () => color, opts));
    el.querySelector(".pf-del")?.addEventListener("click", ev => remove(ev.currentTarget, id));
    el.addEventListener("keydown", e => {
      if(e.key === "Enter" && e.target.tagName === "INPUT"){
        e.preventDefault();
        save(el, id, () => color, opts);
      }
    });
    el.querySelector(".pf-name").focus();
  }

  function segVal(el, field){
    return el.querySelector(`[data-field="${field}"] [aria-checked="true"]`)?.dataset.v || "";
  }

  async function save(el, id, color, opts){
    const kind = segVal(el, "kind") || "person";
    const prev = byId(id) || {};
    const data = await post({action:"save", profile:{
      id,
      kind,
      name: el.querySelector(".pf-name").value.trim(),
      sex: segVal(el, "sex"),
      age_years: el.querySelector(".pf-age").value,
      dominant_hand: segVal(el, "hand"),
      note: el.querySelector(".pf-note-in").value.trim(),
      color: color() || prev.color || 0,
      age_set: prev.age_set || "",
    }});
    if(!data.ok) return;                  // leave the sheet open to be fixed
    closeSheet();
    if(!id && data.profile && data.profile.id){
      if(opts.then) return opts.then(data.profile);
      return activate(data.profile.id);
    }
    renderChips(true);
    refreshLaunch();
    refreshViews();
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

  async function remove(btn, id){
    if(!armed(btn)) return;
    const data = await post({action:"delete", id});
    if(!data.ok) return;
    closeSheet();
    renderChips(true);
    refreshLaunch();
    // profileFilter() drops a pin whose person no longer has sessions, so the
    // page cannot strand itself on the profile that was just removed.
    refreshViews();
  }

  /* Everything that reads the roster or the person filter. */
  function refreshViews(){
    try{ renderVitals(); }catch(e){ console.error(e); }
    if(document.getElementById("page-analysis")?.classList.contains("active"))
      try{ renderAnalysis(); }catch(e){ console.error(e); }
  }

  /* ── The launch picker ──────────────────────────────────────────── */

  function skipPicker(){
    try{ return localStorage.getItem(SKIP_KEY) === "1"; }catch(e){ return false; }
  }
  function setSkipPicker(on){
    try{ on ? localStorage.setItem(SKIP_KEY, "1") : localStorage.removeItem(SKIP_KEY); }catch(e){}
  }

  /* Ask only when it can matter: there is somebody to pick, nobody is picked,
     and this browser has not said unassigned runs are fine. */
  function needsPick(){
    return roster.length > 0 && !activeSnap.id && !skipPicker();
  }

  function tile(p){
    const tg = p ? tag(p) : t("Sessions save unassigned");
    return `<button class="pf-tile${p ? "" : " pf-tile-none"}" type="button" data-launch="${p ? esc(p.id) : ""}">
        ${avatar(p, "lg")}
        <span class="pf-nm">${p ? esc(p.name) : t("No profile")}</span>
        ${tg ? `<span class="pf-tag">${esc(tg)}</span>` : ""}
      </button>`;
  }

  /* go(profileId) launches; "" means unassigned. */
  function pickThenLaunch(testLabel, go){
    const people = roster.filter(p => !isGroup(p));
    const groups = roster.filter(isGroup);
    const el = openSheet(`<div class="pf-sheet-head pf-sheet-head-plain">
        <div><h2 class="pf-sheet-title">${t("Who is taking this test?")}</h2>
          ${testLabel ? `<p class="pf-sheet-sub">${esc(testLabel)}</p>` : ""}</div>
      </div>
      <div class="pf-sheet-body">
        <div class="pf-tiles">
          ${people.map(tile).join("")}
          <button class="pf-tile pf-tile-add" type="button" data-add>
            <span class="pf-av pf-av-lg pf-av-add" aria-hidden="true">${PI.plus}</span>
            <span class="pf-nm">${t("Add a person")}</span></button>
        </div>
        ${groups.length ? `<div class="pf-sec">${t("Groups")}</div>
          <div class="pf-tiles">${groups.map(tile).join("")}</div>` : ""}
        <div class="pf-tiles pf-tiles-none">${tile(null)}</div>
      </div>
      <div class="pf-sheet-foot">
        <label class="pf-skip"><input type="checkbox"> ${t("Don't ask again when nobody is chosen")}</label>
        <span class="pf-grow"></span>
        <button class="pf-cancel btn-mini" type="button">${t("Cancel")}</button>
      </div>`, null, t("Who is taking this test?"));

    const skip = el.querySelector(".pf-skip input");
    el.querySelectorAll("[data-launch]").forEach(b => b.addEventListener("click", () => {
      const id = b.dataset.launch;
      // The box only means something for the unassigned choice.
      if(!id && skip.checked) setSkipPicker(true);
      if(id){ activeSnap = byId(id) || {}; renderChips(true); refreshLaunch(); refreshViews(); }
      closeSheet();
      go(id);
    }));
    el.querySelector("[data-add]").addEventListener("click", () => {
      closeSheet();
      openForm("", {kind:"person", then: p => {
        activeSnap = p; renderChips(true); refreshLaunch(); refreshViews();
        go(p.id);
      }});
    });
    el.querySelector(".pf-cancel").addEventListener("click", closeSheet);
    (el.querySelector("[data-launch]") || el.querySelector("[data-add]"))?.focus();
  }

  /* ── The Analysis page's editor ─────────────────────────────────── */

  /* The switcher is where you say who is being tested; the Analysis page is
     where you read a person's history, and that is where you notice their
     details are wrong. Same sheet. */
  function openEditor(id){ openForm(id || ""); }

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
    const snap = pending.profile || {};
    const who = snap.name;
    const group = isGroup(snap);
    const chosen = snap.id || "";
    const opt = p => `<option value="${esc(p.id)}" ${p.id===chosen?"selected":""}>${esc(p.name)}</option>`;
    const people = roster.filter(p => !isGroup(p)), groups = roster.filter(isGroup);
    const options = `<option value="">${t("No profile")}</option>`
      + people.map(opt).join("")
      + (groups.length ? `<optgroup label="${esc(t("Groups"))}">${groups.map(opt).join("")}</optgroup>` : "");

    el.innerHTML = `<span class="ra-ic">${I.check}</span>
      <div class="ra-text">
        <b>${t("{name} saved", {name: t(cfg.label)})}</b>
        <span>${group ? t("Recorded in the group {name}. Who was it?", {name: esc(who)})
              : who ? t("Recorded for {name}", {name: esc(who)})
              : t("Saved with no profile set.")}</span>
      </div>
      ${who ? avatar(snap, "sm") : ""}
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
    // A group run is the one most likely to need a name put on it.
    if(group) el.querySelector(".ra-sel").focus();
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
      // The roster copy carries color/age_set; the status snapshot does not.
      activeSnap = byId(next.id) || next;
      renderChips(true);
      refreshLaunch();
      // The readings strip defaults to whoever is being tested, so it follows.
      if(moved) refreshViews();
    } else {
      renderChips(false);
    }
  };
  window.renderProfileChips = renderChips;
  window.profileList = () => roster;
  window.activeProfileId = () => activeSnap.id || "";
  window.activeProfile = () => activeSnap;
  window.profileById = id => byId(id);
  window.isGroupProfile = p => isGroup(typeof p === "string" ? byId(p) : p);
  window.describeProfile = describe;
  window.profileAvatar = avatar;
  window.assignSession = assign;
  window.reloadProfiles = loadRoster;
  window.openProfileEditor = openEditor;
  window.closeProfileEditor = closeSheet;
  window.needsProfilePick = needsPick;
  window.pickThenLaunch = pickThenLaunch;
  window.afterRun = afterRun;

  loadRoster();
})();
