"""
Relay — the Firestore transport for the return channel
(REMOTE_SESSION_PLAN.md §3.3, §3.4).

The participant's phone cannot reach the helper's laptop: it is behind NAT
(plan §1). So the phone writes to Firestore and the hub *pulls*. This module is
that pull.

Split deliberately: `decode_document()` / `decode_documents()` are pure — they
turn Firestore's value-typed JSON into plain Python and are unit-tested against
fixtures — while `fetch()` is the one function that touches the network. Until
the helper fills in the relay settings, `status()` says exactly what is missing
and nothing here makes a request.

Stdlib only, matching `launcher.py`.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

from core.remote import store

API_ROOT = "https://firestore.googleapis.com/v1"
TIMEOUT_S = 15
MAX_PAGE = 50

# Collections, mirroring the names in firestore.rules.
INVITES = "invites"
RESULTS = "remote_results"

# Defaults for this project. A Firebase **web** API key identifies the project
# and is designed to ship in client code — the access control is
# firestore.rules, not this string, and the same key is already public in
# participant/cloud.js. Overridable from .remote_sessions.json for a fork.
DEFAULT_PROJECT = "hand-tracking-project"
DEFAULT_API_KEY = "AIzaSyCCXF8vc5u-bmS_HR-kVE6h4C0xYJvMUyU"

_REQUIRED = ("project_id", "api_key")
_HINTS = {
    "project_id": "Firebase project id (.firebaserc has it).",
    "api_key": "Firebase Web API key, from Project settings.",
}

_auth_lock = threading.Lock()


def config() -> dict:
    """Stored settings, with this project's defaults filled in."""
    cfg = dict(store.relay_config())
    cfg.setdefault("project_id", DEFAULT_PROJECT)
    cfg.setdefault("api_key", DEFAULT_API_KEY)
    return cfg


def missing(cfg: dict | None = None) -> list[str]:
    cfg = config() if cfg is None else cfg
    return [k for k in _REQUIRED if not str(cfg.get(k, "")).strip()]


def status() -> dict:
    """What the Remote page shows where the inbox controls would be."""
    cfg = config()
    gaps = missing(cfg)
    signed_in, note = _auth_state()
    return {
        "configured": (not gaps) and signed_in,
        "missing": gaps,
        "hints": [_HINTS[k] for k in gaps] + ([note] if note else []),
        "project_id": cfg.get("project_id", ""),
        "helper_uid": store.relay_config().get("helper_uid", ""),
        # Never echo the key or the tokens back to the page.
    }


# -- Identity --------------------------------------------------------------
# The helper's laptop needs *an* identity so firestore.rules can bind invites
# and results to it. Full Google sign-in is the plan (§3.2); for now the hub
# signs in anonymously and keeps the refresh token, which is enough to own its
# own documents and needs no browser flow. Swapping this for a real sign-in
# later changes only which token `_id_token()` returns.

_IDP = "https://identitytoolkit.googleapis.com/v1"
_SECURE_TOKEN = "https://securetoken.googleapis.com/v1/token"


def _post_json(url: str, payload: dict) -> tuple[bool, str, dict]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return True, "", json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            reason = str(body.get("error", {}).get("message", exc.code))
        except (ValueError, OSError):
            reason = str(exc.code)
        return False, reason, {}
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return False, str(exc), {}


def _auth_note(reason: str) -> str:
    """Turn an Identity Toolkit error into something actionable."""
    if "CONFIGURATION_NOT_FOUND" in reason:
        return ("Firebase Authentication is not set up yet - open the Firebase "
                "console, go to Authentication, and enable the Anonymous "
                "provider.")
    if "ADMIN_ONLY_OPERATION" in reason or "OPERATION_NOT_ALLOWED" in reason:
        return ("Anonymous sign-in is switched off - enable it under "
                "Authentication > Sign-in method in the Firebase console.")
    return f"Could not sign in to Firebase: {reason}"


def _auth_state() -> tuple[bool, str]:
    """(signed_in, note). Never raises; the Remote page polls this."""
    saved = store.relay_config()
    if saved.get("refresh_token"):
        return True, ""
    return False, saved.get("auth_note", "") or "Not signed in to Firebase yet."


def _id_token() -> tuple[str, str]:
    """A live ID token for the hub's identity, signing in if needed.
    Returns (token, error-note); the token is empty on failure."""
    with _auth_lock:
        cfg = config()
        saved = store.relay_config()
        key = cfg["api_key"]

        refresh = saved.get("refresh_token")
        if refresh:
            ok, reason, body = _post_json(
                f"{_SECURE_TOKEN}?key={key}",
                {"grant_type": "refresh_token", "refresh_token": refresh})
            if ok and body.get("id_token"):
                return body["id_token"], ""
            # A dead refresh token means start over rather than stay stuck.
            saved.pop("refresh_token", None)

        ok, reason, body = _post_json(
            f"{_IDP}/accounts:signUp?key={key}", {"returnSecureToken": True})
        if not ok:
            note = _auth_note(reason)
            saved["auth_note"] = note
            store.set_relay_config(saved)
            return "", note

        saved["refresh_token"] = body.get("refreshToken", "")
        saved["helper_uid"] = body.get("localId", "")
        saved.pop("auth_note", None)
        store.set_relay_config(saved)
        return body.get("idToken", ""), ""


def helper_uid() -> str:
    """The uid invites and results are bound to. Signs in on first use."""
    uid = store.relay_config().get("helper_uid", "")
    if uid:
        return uid
    _id_token()
    return store.relay_config().get("helper_uid", "")


# ── Firestore's value-typed JSON ───────────────────────────────────────────
# Every field arrives wrapped: {"stringValue": "x"}, {"integerValue": "3"},
# {"mapValue": {"fields": {...}}}. These two functions unwrap it. Pure, so the
# tests can exercise the shape without a project.

def decode_value(value):
    if not isinstance(value, dict) or len(value) != 1:
        return None
    (kind, raw), = value.items()
    if kind == "nullValue":
        return None
    if kind == "booleanValue":
        return bool(raw)
    if kind == "integerValue":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if kind == "doubleValue":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    if kind in ("stringValue", "timestampValue", "bytesValue", "referenceValue"):
        return str(raw)
    if kind == "arrayValue":
        return [decode_value(v) for v in (raw or {}).get("values", [])]
    if kind == "mapValue":
        return {k: decode_value(v)
                for k, v in ((raw or {}).get("fields") or {}).items()}
    return None


def decode_document(doc) -> dict:
    """One Firestore document → plain dict, with its id under `_id`."""
    if not isinstance(doc, dict):
        return {}
    out = {k: decode_value(v) for k, v in (doc.get("fields") or {}).items()}
    name = str(doc.get("name", ""))
    if name:
        out["_id"] = name.rsplit("/", 1)[-1]
    return out


def decode_documents(body) -> list[dict]:
    """A `documents.list` / `runQuery` response → list of plain dicts."""
    if isinstance(body, dict):
        docs = body.get("documents")
        if isinstance(docs, list):
            return [decode_document(d) for d in docs]
        return []
    if isinstance(body, list):          # runQuery returns a bare array
        return [decode_document(row.get("document"))
                for row in body if isinstance(row, dict) and row.get("document")]
    return []


def encode_value(value):
    """Plain Python → Firestore's value-typed JSON. Used when publishing an
    invite so the participant's page can validate the token offline."""
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [encode_value(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {str(k): encode_value(v)
                                        for k, v in value.items()}}}
    return {"stringValue": str(value)}


def encode_fields(record: dict) -> dict:
    return {"fields": {str(k): encode_value(v) for k, v in record.items()}}


# ── The one function that talks to the network ─────────────────────────────

def _url(cfg: dict, path: str, params: dict | None = None) -> str:
    query = dict(params or {})
    query["key"] = cfg["api_key"]
    return (f"{API_ROOT}/projects/{cfg['project_id']}/databases/(default)/"
            f"documents/{path}?{urllib.parse.urlencode(query)}")


def fetch(path: str, *, method: str = "GET", body: dict | None = None,
          params: dict | None = None) -> tuple[bool, str, object]:
    """One Firestore REST call. Returns (ok, message, decoded-body).

    Every failure is a message rather than an exception: the inbox poll runs
    on a timer and a flaky network must not take the hub down.
    """
    cfg = config()
    gaps = missing(cfg)
    if gaps:
        return False, f"Remote inbox is not set up yet (missing: {', '.join(gaps)}).", None

    token, note = _id_token()
    if not token:
        return False, note, None

    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        _url(cfg, path, params), data=data, method=method,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return True, "", json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "Sign-in expired — connect the remote inbox again.", None
        return False, f"Firestore refused the request ({exc.code}).", None
    except urllib.error.URLError as exc:
        return False, f"Could not reach Firestore: {exc.reason}", None
    except (ValueError, OSError) as exc:
        return False, f"Remote inbox error: {exc}", None


def pull_results(after: str = "") -> tuple[bool, str, list[dict]]:
    """Fetch result documents the hub has not seen. Ordered by upload time so
    `after` can be a simple high-water mark."""
    params = {"pageSize": MAX_PAGE, "orderBy": "uploaded_at"}
    if after:
        params["startAfter"] = after
    ok, message, body = fetch(RESULTS, params=params)
    if not ok:
        return False, message, []
    return True, "", decode_documents(body)


def publish_invite(invite: dict) -> tuple[bool, str]:
    """Mirror a freshly minted invite into Firestore so the participant's page
    can check it. Only the fields the page needs — never the helper's notes."""
    public = {k: invite[k] for k in
              ("token", "test", "session_test", "mode", "lang", "expires_at",
               "uses_left", "helper", "participant")
              if k in invite}
    public["revoked"] = bool(invite.get("revoked"))
    public["helper_uid"] = helper_uid()

    fields = encode_fields(public)
    # `expires_at` is compared against request.time in firestore.rules, so it
    # has to arrive as a timestampValue, not the ISO string encode_value would
    # produce. Firestore wants RFC 3339 with a Z, not "+00:00".
    stamp = str(public.get("expires_at", ""))
    if stamp:
        if stamp.endswith("+00:00"):
            stamp = stamp[:-6] + "Z"
        elif not stamp.endswith("Z"):
            stamp += "Z"
        fields["fields"]["expires_at"] = {"timestampValue": stamp}
    ok, message, _ = fetch(f"{INVITES}?documentId={invite['token']}",
                           method="POST", body=fields)
    return ok, message or "Link published."


def delete_result(doc_id: str) -> tuple[bool, str]:
    """Remove a pulled result from the relay. The helper's copy in `results/`
    is the durable one; leaving cloud copies around is a retention problem
    (§5), so the inbox clears what it has stored."""
    ok, message, _ = fetch(f"{RESULTS}/{doc_id}", method="DELETE")
    return ok, message
