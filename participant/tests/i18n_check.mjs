/* Chinese coverage for the participant page.

     node participant/tests/i18n_check.mjs

   Every string a participant can see must have a Chinese entry in i18n.js,
   because an untranslated line inside a Chinese page is exactly what the
   desktop's test_i18n.py exists to prevent there. Checks:

     - every t("…") literal in app.js,
     - every [data-t] element's English markup in index.html, as the browser
       will read it back (entities decoded, whitespace collapsed),
     - every edge hint the engine can return and every `reason` computeMetrics
       can produce, through translate() -- the formatted ones via ZH_RULES,
     - that a Chinese entry keeps the same {params} as its English key,
     - that app.js never calls t() with anything but a plain string literal,
       which this check could not see. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { ZH, lookup, keyOf, setLang, translate } from "../i18n.js";
import { EDGES, hint, MODES, computeMetrics } from "../engine.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = readFileSync(join(HERE, "..", "app.js"), "utf-8");
const HTML = readFileSync(join(HERE, "..", "index.html"), "utf-8");

let failures = 0;
let checks = 0;
function fail(msg) { failures += 1; console.log(`  FAIL  ${msg}`); }

function need(en, where) {
  checks += 1;
  if (lookup(en) === null) fail(`no Chinese for ${JSON.stringify(en)}  (${where})`);
}

/* ── app.js: t("…") ─────────────────────────────────────────────────────── */
const literal = /\bt\(\s*"((?:[^"\\]|\\.)*)"/g;
for (const m of APP.matchAll(literal)) need(JSON.parse(`"${m[1]}"`), "app.js t()");
// A t( whose argument is not a double-quoted literal (a template, a variable)
// would be invisible to the scan above.
for (const m of APP.matchAll(/\bt\(\s*([^"\s)])/g)) {
  checks += 1;
  fail(`t() with a non-literal argument near: ${APP.slice(m.index, m.index + 60)}`);
}

/* ── index.html: [data-t] ───────────────────────────────────────────────── */
const ENTITIES = { "&mdash;": "—", "&hellip;": "…", "&amp;": "&", "&nbsp;": " ",
                   "&#39;": "'", "&quot;": '"' };
const decode = (s) => s.replace(/&[a-z#0-9]+;/g, (e) => ENTITIES[e] ?? e);
const tagged = /<(\w+)\b[^>]*\bdata-t\b[^>]*>([\s\S]*?)<\/\1>/g;
let tagCount = 0;
for (const m of HTML.matchAll(tagged)) {
  tagCount += 1;
  need(keyOf(decode(m[2])), "index.html data-t");
  if (/\bid="/.test(m[2])) {
    checks += 1;
    fail(`data-t element holds an element with an id (translation would replace it): ${m[0].slice(0, 80)}`);
  }
}
checks += 1;
if (tagCount < 20) fail(`only ${tagCount} data-t elements found — is the scan broken?`);

/* ── engine output ──────────────────────────────────────────────────────── */
setLang("zh");
const combos = [[], ...EDGES.map((e) => [e]), ["left", "top"], ["right", "bottom"]];
for (const edges of combos) {
  for (const tracing of [false, true]) {
    const en = hint(edges, tracing);
    checks += 1;
    if (translate(en) === en) fail(`edge hint not translated: ${en}`);
  }
}

// Drive computeMetrics() into each refusal it can make, and translate it.
const mode = MODES.big_and_fast;
const flat = (n) => Array.from({ length: 200 }, (_, i) => [i / 30, 1.0]);
const reasons = [
  computeMetrics(mode, [1, 2, 3], flat(), 0, 20, null, 0.5).reason,          // out of view
  computeMetrics(mode, [1, 2, 3], flat(), 0, 20, null, 1.0, 30, 5).reason,   // shallow
  computeMetrics(mode, [1, 2, 3], flat(), 0, 20).reason,                      // only N taps
  // steady, then long gaps: too few intervals survive the 3x-median cutoff
  computeMetrics(mode, [0, 0.5, 1, 1.5, 2, 2.5, 3, 20, 40, 60], flat(), 0, 60).reason, // irregular
  computeMetrics(mode, Array.from({ length: 12 }, (_, i) => i * 2.5), flat(), 0, 30).reason, // too slow
];
for (const reason of reasons) {
  checks += 1;
  if (!reason) { fail("a refusal case did not produce a reason — update this list"); continue; }
  if (translate(reason) === reason) fail(`engine reason not translated: ${reason}`);
}
checks += 1;
// Compared with the numbers taken out: two cases that differ only in a count
// are the same refusal, and one of the five would go untested.
const shapes = reasons.map((r) => String(r).replace(/\d+(\.\d+)?/g, "#"));
if (new Set(shapes).size !== shapes.length) fail(`refusal cases overlap: ${reasons.join(" | ")}`);

/* ── params survive translation ─────────────────────────────────────────── */
for (const [en, zh] of Object.entries(ZH)) {
  checks += 1;
  const keys = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
  if (keys(en) !== keys(zh)) fail(`params differ: ${en}  →  ${zh}`);
}

console.log(`\n${checks - failures}/${checks} i18n checks passed` +
            (failures ? ` — ${failures} FAILED` : ""));
process.exit(failures ? 1 : 0);
