/* Firestore access for the participant's page (REMOTE_SESSION_PLAN.md §3.3).

   REST rather than the Firebase SDK: the calls are two, the payloads are
   small, and a 200 KB SDK download on a five-year-old phone over mobile data
   buys nothing here. It also keeps the value-typed JSON codec identical in
   shape to core/remote/relay.py, so the two ends can be read side by side.

   The Firebase *web* API key identifies the project rather than authenticating
   anyone — the access control is firestore.rules, not the key — so the built
   page does carry it in the clear, and that is by design. What it must not do
   is sit in the repository: an AIza... literal in a tracked file is what every
   secret scanner reads as a leaked Google credential. So it arrives from
   firebase-config.js, which tools/build_web.py writes into the build from the
   git-ignored .remote_sessions.json. That file is absent in a fresh checkout;
   the page then says so instead of failing at the first fetch. */

const CONFIG = {
  projectId: "hand-tracking-project",
  apiKey: "",
  ...((typeof window !== "undefined" && window.HS_FIREBASE) || {}),
};

/** Throws the one error the screens know how to explain (see app.js). */
function requireKey() {
  const key = String(CONFIG.apiKey || "").trim();
  if (!key) throw new Error("NO_FIREBASE_KEY");
  return key;
}

const FS = `https://firestore.googleapis.com/v1/projects/${CONFIG.projectId}/databases/(default)/documents`;
const IDP = "https://identitytoolkit.googleapis.com/v1";

let idToken = null;
let uid = null;

/* ── Value-typed JSON (mirrors core/remote/relay.py) ───────────────────── */

export function decodeValue(v) {
  if (!v || typeof v !== "object") return null;
  const kind = Object.keys(v)[0];
  const raw = v[kind];
  switch (kind) {
    case "nullValue": return null;
    case "booleanValue": return !!raw;
    case "integerValue": return parseInt(raw, 10);
    case "doubleValue": return Number(raw);
    case "stringValue":
    case "timestampValue": return String(raw);
    case "arrayValue": return (raw.values || []).map(decodeValue);
    case "mapValue": {
      const out = {};
      for (const [k, val] of Object.entries(raw.fields || {})) out[k] = decodeValue(val);
      return out;
    }
    default: return null;
  }
}

export function encodeValue(v) {
  if (v === null || v === undefined) return { nullValue: null };
  if (typeof v === "boolean") return { booleanValue: v };
  if (typeof v === "number") {
    return Number.isInteger(v) ? { integerValue: String(v) } : { doubleValue: v };
  }
  if (Array.isArray(v)) return { arrayValue: { values: v.map(encodeValue) } };
  if (typeof v === "object") {
    const fields = {};
    for (const [k, val] of Object.entries(v)) fields[k] = encodeValue(val);
    return { mapValue: { fields } };
  }
  return { stringValue: String(v) };
}

function decodeDoc(doc) {
  const out = {};
  for (const [k, v] of Object.entries((doc && doc.fields) || {})) out[k] = decodeValue(v);
  return out;
}

/* ── Anonymous sign-in ─────────────────────────────────────────────────── */

/** The participant never makes an account (§3.2). Anonymous auth exists only
 *  so firestore.rules has a uid to bind the upload to. */
export async function signIn() {
  if (idToken) return idToken;
  const r = await fetch(`${IDP}/accounts:signUp?key=${requireKey()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ returnSecureToken: true }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const reason = (data.error && data.error.message) || `HTTP ${r.status}`;
    // The most likely cause by far, and the one with a one-click fix.
    if (String(reason).includes("ADMIN_ONLY_OPERATION") ||
        String(reason).includes("OPERATION_NOT_ALLOWED")) {
      throw new Error("ANON_AUTH_DISABLED");
    }
    throw new Error(reason);
  }
  idToken = data.idToken;
  uid = data.localId;
  return idToken;
}

export function currentUid() { return uid; }

/* ── The two calls the page makes ──────────────────────────────────────── */

/** Read the invite this link names. Returns null when there is no such doc. */
export async function fetchInvite(token) {
  await signIn();
  const r = await fetch(`${FS}/invites/${encodeURIComponent(token)}`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (r.status === 404 || r.status === 403) return null;
  if (!r.ok) throw new Error(`Could not check the link (HTTP ${r.status}).`);
  return decodeDoc(await r.json());
}

/** Upload one finished session. Field names and nesting must match
 *  firestore.rules exactly, or the write is refused. */
export async function uploadResult(token, invite, session) {
  await signIn();
  const body = {
    fields: {
      invite_token: { stringValue: token },
      helper_uid: { stringValue: invite.helper_uid || "" },
      // No upload time from the phone: its clock can be anything. The hub
      // reads Firestore's own createTime (relay.decode_document).
      session: encodeValue(session),
    },
  };
  const r = await fetch(`${FS}/remote_results`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new Error((data.error && data.error.message) || `Upload failed (HTTP ${r.status}).`);
  }
  return true;
}

/* ── Offline buffer ────────────────────────────────────────────────────── */
// A finished test must never be lost to a dead connection (§3.3, §6). Each
// result is parked in localStorage under its session id and retried; the
// participant is told it is saved, not that it has been delivered. One slot
// used to hold one result, so a second offline session overwrote the first.

const PARK = "pending_sessions";
const OLD_PARK = "pending_session";          // the single slot, before 0.2
const DONE = "done:";

function readParked() {
  let all = {};
  try { all = JSON.parse(localStorage.getItem(PARK) || "{}") || {}; }
  catch (e) { all = {}; }
  try {
    const old = JSON.parse(localStorage.getItem(OLD_PARK) || "null");
    if (old && old.session && old.session.session_id) all[old.session.session_id] = old;
  } catch (e) { /* ignore */ }
  return all;
}

function writeParked(all) {
  try {
    if (Object.keys(all).length) localStorage.setItem(PARK, JSON.stringify(all));
    else localStorage.removeItem(PARK);
    localStorage.removeItem(OLD_PARK);
  } catch (e) { /* private mode — nothing more we can do */ }
}

export function park(token, invite, session) {
  const all = readParked();
  all[session.session_id] = { token, invite, session };
  writeParked(all);
}

export function parked() { return Object.values(readParked()); }

export function clearPark(sessionId) {
  const all = readParked();
  delete all[sessionId];
  writeParked(all);
}

/** Retry whatever is parked. Safe to call on load and on reconnect: the hub
 *  de-duplicates by session_id, so a double send costs nothing. One failure
 *  does not stop the rest. Returns how many went. */
export async function flushParked() {
  let sent = 0;
  for (const item of parked()) {
    try {
      await uploadResult(item.token, item.invite, item.session);
      clearPark(item.session.session_id);
      sent += 1;
    } catch (e) { /* stays parked for the next try */ }
  }
  return sent;
}

/* ── Links already done on this phone ──────────────────────────────────── */
// Reopening a finished link used to run the test again: the use count only
// falls when the helper's hub next pulls, so the invite still read as live.

export function markDone(token) {
  try { localStorage.setItem(DONE + token, String(doneCount(token) + 1)); }
  catch (e) { /* ignore */ }
}

export function doneCount(token) {
  try { return Number(localStorage.getItem(DONE + token) || 0) || 0; }
  catch (e) { return 0; }
}
