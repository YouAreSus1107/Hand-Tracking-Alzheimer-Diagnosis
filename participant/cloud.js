/* Firestore access for the participant's page (REMOTE_SESSION_PLAN.md §3.3).

   REST rather than the Firebase SDK: the calls are two, the payloads are
   small, and a 200 KB SDK download on a five-year-old phone over mobile data
   buys nothing here. It also keeps the value-typed JSON codec identical in
   shape to core/remote/relay.py, so the two ends can be read side by side.

   The API key below is a Firebase *web* key. It identifies the project, it is
   not a secret, and it is meant to ship in client code — the access control is
   firestore.rules, not this string. */

const CONFIG = {
  projectId: "hand-tracking-project",
  apiKey: "AIzaSyCCXF8vc5u-bmS_HR-kVE6h4C0xYJvMUyU",
};

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
  const r = await fetch(`${IDP}/accounts:signUp?key=${CONFIG.apiKey}`, {
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
      uploaded_at: { timestampValue: new Date().toISOString() },
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
// A finished test must never be lost to a dead connection (§3.3, §6). The
// result is parked in localStorage and retried; the participant is told it is
// saved, not that it has been delivered.

const PARK = "pending_session";

export function park(token, invite, session) {
  try {
    localStorage.setItem(PARK, JSON.stringify({ token, invite, session }));
  } catch (e) { /* private mode — nothing more we can do */ }
}

export function parked() {
  try { return JSON.parse(localStorage.getItem(PARK) || "null"); }
  catch (e) { return null; }
}

export function clearPark() {
  try { localStorage.removeItem(PARK); } catch (e) { /* ignore */ }
}

/** Retry whatever is parked. Safe to call on load and on reconnect: the hub
 *  de-duplicates by session_id, so a double send costs nothing. */
export async function flushParked() {
  const item = parked();
  if (!item) return false;
  await uploadResult(item.token, item.invite, item.session);
  clearPark();
  return true;
}
