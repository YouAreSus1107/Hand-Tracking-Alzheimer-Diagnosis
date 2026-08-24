"""
Invites — the participant's only credential (REMOTE_SESSION_PLAN.md §3.2).

Pure logic: minting, validating, and spending a token. No file I/O, no clock
tricks — every function that needs "now" takes it as an argument so the tests
can pin it. `store.py` owns persistence; `launcher.py` owns the HTTP surface.

The token is 128 bits of randomness carried in the URL path (`/s/<token>`).
There is no participant account: holding an unexpired token with uses left is
the whole of the authorisation, which is why expiry is short and the use count
is low (plan §6, "link forwarding").
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

# 128 bits, URL-safe. token_urlsafe(16) is 22 characters of base64url.
TOKEN_BYTES = 16
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")

# Short by design. A link that lives forever in a family group chat is the
# failure mode §6 warns about.
DEFAULT_TTL_HOURS = 48
MAX_TTL_HOURS = 168          # one week, the outer limit worth offering
DEFAULT_USES = 1
MAX_USES = 5

# Tests the participant can be sent to. Mirrors launcher.TOOLS minus the
# tracking demo, which is not a scored test.
#
# Two different names are in play and conflating them silently rejects every
# real upload: the **tool key** ("iiv") is what launcher.TOOLS and the
# dashboard use, while the **session test name** ("finger_tapping") is what the
# test writes into results/ via core.session and what the Analysis view groups
# on. Invites carry the tool key; the record carries the session name.
TESTS = {
    "iiv": {
        "label": "Finger Tapping",
        "session_test": "finger_tapping",
        "modes": ("big_and_fast", "paced"),
    },
    "spiral": {
        "label": "Spiral Tracing",
        "session_test": "spiral",
        "modes": ("air_spiral",),
    },
    "oculomotor": {
        "label": "Eye Movement",
        "session_test": "oculomotor",
        "modes": ("pro_anti",),
    },
}


def session_test(tool_key: str) -> str:
    """The `test` value the stored record must carry for this tool."""
    return TESTS[tool_key]["session_test"]


LANGS = ("en", "zh")

# States an invite can be in, in the order the UI shows them.
LIVE, SPENT, EXPIRED, REVOKED = "live", "spent", "expired", "revoked"


def _utc(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def valid_token_shape(token) -> bool:
    """Cheap syntactic gate, so a malformed token never reaches the store."""
    return isinstance(token, str) and bool(TOKEN_RE.match(token))


def make_invite(*, test: str, mode: str = "", lang: str = "en",
                participant: str = "", ttl_hours: int = DEFAULT_TTL_HOURS,
                uses: int = DEFAULT_USES, helper: str = "",
                now: datetime | None = None) -> dict:
    """Mint one invite record. Raises ValueError on anything unrecognised —
    the caller turns that into a message for the dashboard."""
    if test not in TESTS:
        raise ValueError(f"Unknown test: {test}")
    spec = TESTS[test]
    mode = mode or spec["modes"][0]
    if mode not in spec["modes"]:
        raise ValueError(f"{spec['label']} has no mode {mode!r}.")
    if lang not in LANGS:
        raise ValueError(f"Unknown language: {lang}")

    try:
        ttl_hours = max(1, min(MAX_TTL_HOURS, int(ttl_hours)))
    except (TypeError, ValueError):
        ttl_hours = DEFAULT_TTL_HOURS
    try:
        uses = max(1, min(MAX_USES, int(uses)))
    except (TypeError, ValueError):
        uses = DEFAULT_USES

    created = _utc(now)
    return {
        "token": new_token(),
        "test": test,                     # tool key
        "session_test": spec["session_test"],
        "mode": mode,
        "lang": lang,
        # Self-entered, never verified. §6: a remote session is not identity
        # evidence, so this is a label the helper recognises, nothing more.
        "participant": str(participant).strip()[:60],
        "helper": str(helper).strip()[:60],
        "created": created.isoformat(timespec="seconds"),
        "expires_at": (created + timedelta(hours=ttl_hours)).isoformat(timespec="seconds"),
        "uses_left": uses,
        "revoked": False,
        "sessions": [],      # session_ids received against this invite
    }


def _parse(stamp) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def state(invite: dict, now: datetime | None = None) -> str:
    """Which of LIVE / SPENT / EXPIRED / REVOKED an invite is in.

    Revocation wins over everything, then expiry, then exhaustion — an invite
    the helper killed should never read as merely 'used up'.
    """
    if invite.get("revoked"):
        return REVOKED
    expires = _parse(invite.get("expires_at"))
    if expires is not None and _utc(now) >= expires:
        return EXPIRED
    if int(invite.get("uses_left", 0)) <= 0:
        return SPENT
    return LIVE


def is_live(invite: dict, now: datetime | None = None) -> bool:
    return state(invite, now) == LIVE


def refusal(invite: dict | None, now: datetime | None = None) -> str | None:
    """The message to send back when an invite cannot be used, or None if it
    can. Deliberately vague about *why* a token is unknown."""
    if invite is None:
        return "That link is not valid."
    st = state(invite, now)
    if st == REVOKED:
        return "That link was cancelled."
    if st == EXPIRED:
        return "That link has expired. Ask for a new one."
    if st == SPENT:
        return "That link has already been used."
    return None


def spend(invite: dict, session_id: str, now: datetime | None = None) -> dict:
    """Return a copy of the invite with one use consumed. Caller must have
    checked `refusal()` first; this does not re-check."""
    used = dict(invite)
    used["uses_left"] = max(0, int(invite.get("uses_left", 0)) - 1)
    used["last_used"] = _utc(now).isoformat(timespec="seconds")
    sessions = list(invite.get("sessions") or [])
    if session_id and session_id not in sessions:
        sessions.append(session_id)
    used["sessions"] = sessions
    return used


def link(token: str, base_url: str) -> str:
    """The URL the helper sends. `/s/<token>` per plan §3.2."""
    return f"{base_url.rstrip('/')}/s/{token}"


def summarise(invite: dict, base_url: str, now: datetime | None = None) -> dict:
    """Invite as the dashboard wants it: state resolved, link built."""
    out = dict(invite)
    out["state"] = state(invite, now)
    out["link"] = link(invite["token"], base_url)
    out["test_label"] = TESTS.get(invite.get("test", ""), {}).get("label", "Unknown")
    out["session_test"] = TESTS.get(invite.get("test", ""), {}).get("session_test", "")
    return out
