"""
Invite persistence — the helper's side of the ledger.

One JSON file beside the launcher's other local state, same shape of code as
`launcher._read_settings()`: stdlib only, tolerant of a corrupt or missing
file, guarded by a lock because the hub is a ThreadingHTTPServer.

Kept out of `results/` on purpose: `results/` is the sessions themselves and is
what the Analysis view reads. This file is bookkeeping.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.remote import invites

_REPO_ROOT = Path(__file__).resolve().parents[2]
STORE_FILE = _REPO_ROOT / ".remote_sessions.json"

# Dead invites are kept for a while so the helper can see what happened to a
# link they sent, then swept so the file cannot grow without bound.
KEEP_DEAD_DAYS = 30
MAX_INVITES = 200

_lock = threading.Lock()


def _read() -> dict:
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    """Write via a temp file + replace: a half-written ledger would lose every
    live invite, and os.replace is atomic on both platforms we run on."""
    tmp = STORE_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, STORE_FILE)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _all(data: dict) -> list[dict]:
    items = data.get("invites")
    return [i for i in items if isinstance(i, dict) and "token" in i] \
        if isinstance(items, list) else []


def _sweep(items: list[dict], now: datetime | None = None) -> list[dict]:
    """Drop long-dead invites, newest first, capped."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=KEEP_DEAD_DAYS)
    kept = []
    for inv in items:
        if invites.state(inv, now) != invites.LIVE:
            try:
                created = datetime.fromisoformat(str(inv.get("created")))
                created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
                if created < cutoff:
                    continue
            except (TypeError, ValueError):
                pass
        kept.append(inv)
    kept.sort(key=lambda i: str(i.get("created", "")), reverse=True)
    return kept[:MAX_INVITES]


def list_invites(now: datetime | None = None) -> list[dict]:
    with _lock:
        return _sweep(_all(_read()), now)


def get(token: str) -> dict | None:
    if not invites.valid_token_shape(token):
        return None
    with _lock:
        for inv in _all(_read()):
            if inv.get("token") == token:
                return inv
    return None


def add(invite: dict) -> dict:
    with _lock:
        data = _read()
        items = _sweep(_all(data))
        items.insert(0, invite)
        data["invites"] = items[:MAX_INVITES]
        _write(data)
    return invite


def replace(invite: dict) -> None:
    """Write back one invite, matched by token. Silently does nothing if the
    token is gone — a swept invite is not an error worth surfacing."""
    with _lock:
        data = _read()
        items = _all(data)
        for i, existing in enumerate(items):
            if existing.get("token") == invite.get("token"):
                items[i] = invite
                break
        else:
            return
        data["invites"] = items
        _write(data)


def revoke(token: str) -> tuple[bool, str]:
    with _lock:
        data = _read()
        items = _all(data)
        for inv in items:
            if inv.get("token") == token:
                if inv.get("revoked"):
                    return False, "That link was already cancelled."
                inv["revoked"] = True
                data["invites"] = items
                _write(data)
                return True, "Link cancelled."
    return False, "No such link."


def relay_config() -> dict:
    """Firestore settings, when the helper has filled them in (§3.3)."""
    with _lock:
        cfg = _read().get("relay")
    return cfg if isinstance(cfg, dict) else {}


def set_relay_config(cfg: dict) -> None:
    with _lock:
        data = _read()
        data["relay"] = cfg
        _write(data)
