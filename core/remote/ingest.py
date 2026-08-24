"""
Ingest — turning what a phone uploaded into a row in `results/`
(REMOTE_SESSION_PLAN.md §3.3, §3.4, and the §4 upload rule).

`validate()` is pure and is the security boundary: it decides what a remote
payload is allowed to contain before anything touches disk. `accept()` is the
thin I/O wrapper that writes an accepted payload through `core.session`, so
remote and local sessions share one schema and one writer.

The §4 rule — **metrics only, never video and never per-frame arrays** — is
enforced here rather than trusted to the client, because a page can be modified
and a promise on a consent screen is only worth what the server refuses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core import session as session_store
from core.remote import invites

# A metrics-only record is small. Anything near this is carrying something it
# should not be (§4), so the size cap is a blunt second line of defence behind
# the key rejection below.
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_METRICS = 60

# Keys that must never arrive from a participant's device. `raw` holds the
# per-frame landmark arrays; the rest are the names a well-meaning client
# might reach for when it wants to "help" by attaching source media.
BANNED_KEYS = frozenset({
    "raw", "frames", "landmarks", "video", "image", "images", "media",
    "recording", "thumbnail", "photo", "clip", "audio", "blob",
})

MAX_NAME = 60


class Rejected(ValueError):
    """Payload refused. The message is safe to show a participant."""


def _walk_keys(obj, depth: int = 0):
    """Every mapping key in the payload, at any depth."""
    if depth > 6:
        raise Rejected("That result is nested too deeply.")
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from _walk_keys(value, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _walk_keys(item, depth + 1)


def _number(value):
    """Metrics must be plain finite numbers — not strings, not nested objects.
    Booleans are allowed through as-is (`scoreable` is one)."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            raise Rejected("That result contains a value that is not a number.")
        return value
    raise Rejected("That result contains a metric that is not a number.")


def _timestamp(raw) -> datetime:
    """The phone's clock, which may be wrong but is the participant's truth.
    Falls back to now rather than refusing — a good test should not be lost to
    a bad clock."""
    try:
        dt = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return datetime.now()
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def validate(payload, invite: dict) -> dict:
    """Check an uploaded session against the invite it claims. Returns the
    normalised record ready for `accept()`. Raises `Rejected` with a message
    fit to show the participant."""
    if not isinstance(payload, dict):
        raise Rejected("That result is not in a form we can read.")

    banned = sorted(set(_walk_keys(payload)) & BANNED_KEYS)
    if banned:
        # Not a polite refusal: this is the privacy promise in §4/§5.
        raise Rejected(f"Results may not include {banned[0]!r} — "
                       "only measurements are uploaded.")

    # The payload speaks the session vocabulary ("finger_tapping"); the invite
    # was minted in the tool vocabulary ("iiv"). Compare like with like.
    expected = invite.get("session_test") or invites.TESTS.get(
        invite.get("test", ""), {}).get("session_test")
    test = str(payload.get("test", "")).strip()
    if not expected or test != expected:
        raise Rejected("That result does not match the test that was sent.")
    # The invite's mode, not merely *a* valid mode for the test: an invite for
    # paced tapping must not come back scored as max-speed tapping.
    mode = str(payload.get("mode", "")).strip() or invite.get("mode", "")
    if mode != invite.get("mode"):
        raise Rejected("That result does not match the test that was sent.")

    metrics_in = payload.get("metrics")
    if not isinstance(metrics_in, dict) or not metrics_in:
        raise Rejected("That result has no measurements in it.")
    if len(metrics_in) > MAX_METRICS:
        raise Rejected("That result has more measurements than expected.")
    metrics = {str(k)[:40]: _number(v) for k, v in metrics_in.items()}

    duration = _number(payload.get("duration_s", 0)) or 0
    if not 0 < float(duration) < 3600:
        raise Rejected("That result has an implausible duration.")

    hand = payload.get("hand")
    hand = str(hand)[:16] if isinstance(hand, str) and hand else None

    device_in = payload.get("device")
    device = {}
    if isinstance(device_in, dict):
        # A fixed, known set — not whatever the client felt like sending.
        for key in ("ua", "platform", "fps_sustained", "screen", "app_version"):
            if key in device_in:
                device[key] = (str(device_in[key])[:200]
                               if isinstance(device_in[key], str)
                               else _number(device_in[key]))
    device["source"] = session_store.REMOTE

    session_id = str(payload.get("session_id", "")).strip()[:64]
    if not session_id:
        raise Rejected("That result has no session id.")

    participant = (str(payload.get("participant", "")).strip()[:MAX_NAME]
                   or str(invite.get("participant", "")).strip()[:MAX_NAME])

    return {
        "session_id": session_id,
        "timestamp": _timestamp(payload.get("timestamp")),
        "test": test,
        "mode": mode,
        "hand": hand,
        "duration_s": float(duration),
        "participant": participant,
        "device": device,
        "metrics": metrics,
    }


def already_have(session_id: str, results_dir: Path | None = None) -> bool:
    """True if this session id is already in `results/`.

    Uploads are retried after a dropped connection (§3.3/§6), so the same
    record can legitimately arrive twice. Duplicates are dropped silently
    rather than refused — the participant already did the test.
    """
    directory = results_dir or session_store.RESULTS_DIR
    if not directory.is_dir():
        return False
    needle = f'"session_id": "{session_id}"'
    for path in directory.glob("*.json"):
        try:
            if needle in path.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def accept(payload, invite: dict) -> tuple[bool, str, dict | None]:
    """Validate and store one uploaded session.

    Returns (ok, message, record). `ok` is True for a duplicate too — the
    participant's device should stop retrying, not keep trying forever — so
    callers must read `record["filed"]` to tell a new session from a repeat.
    """
    try:
        record = validate(payload, invite)
    except Rejected as exc:
        return False, str(exc), None

    if already_have(record["session_id"]):
        # A retry after a dropped connection (§3.3). The participant already
        # did this test, so it is a success — but `filed` stays False so the
        # caller does not spend a second use of the invite on it.
        record["filed"] = False
        return True, "Already received — thank you.", record

    session_store.save_session(
        test=record["test"], mode=record["mode"], hand=record["hand"],
        duration_s=record["duration_s"], device=record["device"],
        metrics=record["metrics"], raw={},          # §4: nothing per-frame
        source=session_store.REMOTE, participant=record["participant"],
        session_id=record["session_id"], timestamp=record["timestamp"],
    )
    record["filed"] = True
    return True, "Result received.", record
