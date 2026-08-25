/* ── Bilingual UI: English / 繁體中文 ─────────────────────────────────
   Loaded before app.js (that file renders cards in a top-level IIFE and
   needs t() to exist already) and after i18n.zh.js, which supplies the
   dictionaries.

   Only Chinese is stored. English stays where it already lives — in the
   markup and in the JS source strings — so there is one copy of it, and an
   untranslated string degrades to English instead of printing a raw key.

   Three lookups, three kinds of text:
     tKey()  dotted keys  ("iiv.step2.body")  → static blocks in index.html
     t()     English keys ("Launch")          → strings rendered from JS
     tMsg()  server text  ("Connected to …")  → toasts + glove notes, which
             come from launcher.py / core/glove and are matched here rather
             than translated server-side. */

(function () {
  const LANGS = ["en", "zh"];
  const STORE = "hubLang";
  const ZH = window.ZH || {};
  const MSG = window.ZH_MSG || { exact: {}, rules: [], suffix: [] };

  const subs = [];
  let lang = initialLang();

  /* Stored choice wins; otherwise follow the browser on the first visit. */
  function initialLang() {
    try {
      const saved = localStorage.getItem(STORE);
      if (LANGS.indexOf(saved) >= 0) return saved;
    } catch (e) { /* private mode / storage disabled */ }
    return (navigator.language || "").toLowerCase().indexOf("zh") === 0 ? "zh" : "en";
  }

  function zh(key) { return lang === "zh" && ZH[key] != null ? ZH[key] : null; }

  /* English source string as its own key, with {name} substitution. */
  function t(str, params) {
    let out = zh(str);
    if (out == null) out = str == null ? "" : String(str);
    if (params) {
      out = out.replace(/\{(\w+)\}/g, (m, k) =>
        params[k] === undefined || params[k] === null ? m : params[k]);
    }
    return out;
  }

  /* Dotted key for a markup block; `fallback` is the English original. */
  function tKey(key, fallback) {
    const out = zh(key);
    return out == null ? (fallback == null ? "" : fallback) : out;
  }

  function expand(tpl, m) {
    return tpl.replace(/\$(\d)/g, (x, i) => (m[+i] == null ? x : m[+i]));
  }

  /* launcher.py appends fragments to some messages (the upload disconnect
     note, the COM-port-in-use hint). Peel a known tail off first, translate
     the head on its own, then re-attach the translated tail. */
  function tMsg(msg) {
    if (lang !== "zh" || msg == null) return msg;
    let s = String(msg), tail = "";
    for (const r of MSG.suffix) {
      const m = s.match(r.re);
      if (m) { s = s.slice(0, m.index); tail = expand(r.zh, m); break; }
    }
    return tHead(s) + tail;
  }
  function tHead(s) {
    if (MSG.exact[s] != null) return MSG.exact[s];
    for (const r of MSG.rules) {
      const m = s.match(r.re);
      if (m) return expand(r.zh, m);
    }
    return s;   // unknown server string: show it as sent, never a blank
  }

  /* For toLocaleDateString / toLocaleString. */
  function locale() { return lang === "zh" ? "zh-Hant" : "en-US"; }

  /* Static markup. The English original is snapshotted onto the element the
     first time it is seen, so switching back to English restores the exact
     markup — links, <strong>, <code> and all — with no English dictionary. */
  function applyStatic(root) {
    const sel = "[data-i18n],[data-i18n-title],[data-i18n-aria],[data-i18n-ph]";
    (root || document).querySelectorAll(sel).forEach(el => {
      let en = el.__i18nEn;
      if (!en) {
        en = el.__i18nEn = {
          html: el.dataset.i18n ? el.innerHTML : null,
          title: el.dataset.i18nTitle ? el.getAttribute("title") : null,
          aria: el.dataset.i18nAria ? el.getAttribute("aria-label") : null,
          ph: el.dataset.i18nPh ? el.getAttribute("placeholder") : null,
        };
      }
      if (el.dataset.i18n) el.innerHTML = tKey(el.dataset.i18n, en.html);
      if (el.dataset.i18nTitle) el.setAttribute("title", tKey(el.dataset.i18nTitle, en.title));
      if (el.dataset.i18nAria) el.setAttribute("aria-label", tKey(el.dataset.i18nAria, en.aria));
      if (el.dataset.i18nPh) el.setAttribute("placeholder", tKey(el.dataset.i18nPh, en.ph));
    });
  }

  function syncPicker() {
    document.querySelectorAll("[data-lang]").forEach(b => {
      const on = b.dataset.lang === lang;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function apply() {
    document.documentElement.lang = lang === "zh" ? "zh-Hant" : "en";
    // Guarded on its own: a throw in here used to take the picker and every
    // re-render hook down with it, which reads as a page that has stopped
    // responding rather than as one mistranslated block.
    try { applyStatic(); } catch (e) { console.error(e); }
    syncPicker();
    subs.forEach(fn => { try { fn(lang); } catch (e) { console.error(e); } });
  }

  function setLang(next) {
    if (LANGS.indexOf(next) < 0 || next === lang) return;
    lang = next;
    try { localStorage.setItem(STORE, lang); } catch (e) { /* ignore */ }
    apply();
  }

  /* Re-render hook. app.js and dev.js build most of their UI from JS, so a
     language switch has to ask them to redraw. */
  function onLang(fn) { if (typeof fn === "function") subs.push(fn); }

  window.t = t;
  window.tKey = tKey;
  window.tMsg = tMsg;
  window.i18nLocale = locale;
  window.getLang = () => lang;
  window.setLang = setLang;
  window.onLang = onLang;
  window.applyStaticI18n = applyStatic;

  document.querySelectorAll("[data-lang]").forEach(b =>
    b.addEventListener("click", () => setLang(b.dataset.lang)));

  apply();   // scripts sit at the end of <body>, so the DOM is already parsed
})();
