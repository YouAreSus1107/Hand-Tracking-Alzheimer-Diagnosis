"""
Patient profiles — who a session belongs to.

Sessions used to be anonymous: results/ held one pooled history, so two people
sharing a machine got their trends interleaved into a single line. A profile is
a small local record (name, sex, age, dominant hand) and the roster lives here.

A profile is either a **person** or a **group**. A group is a guest pool - a
screening day, a care home's visitors - whose runs are kept together but are
never one person's trend: it has no sex/age/hand, the Analysis page draws its
sessions without a line, and the tapping test builds no personal baseline from
it (strangers do not have a "usual").

It rides the same rails as the camera source and the overlay language:

    .launcher_profiles.json   the roster + which profile is active
    HAND3D_PROFILE            the active profile's snapshot, set by launcher.py
                              on the spawned tool's environment

core.session.save_session() reads that env var when the caller passes no
profile, which is why the three test scripts need to know nothing about any of
this. What lands in the session file is a **snapshot** — name/sex/age as they
were at the time — so editing or deleting a profile later never rewrites what a
past recording said.

Its own file rather than a key in .launcher_settings.json: that one holds a
camera index and a pairing token and is harmless to open; this one holds
patient names and ages, and is git-ignored for the same reason results/ is.

Stdlib-only and import-cheap, like core.camera and core.i18n — it is imported
from core.session, which sits under every entry script.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path

PROFILES_FILE = Path(__file__).resolve().parents[1] / ".launcher_profiles.json"

# Set by launcher.py on the spawned tool's environment: the active profile's
# snapshot as compact JSON, or absent/empty for an unassigned run.
ENV_PROFILE = "HAND3D_PROFILE"

# Vocabularies. "unspecified"/"unknown" are real answers, not missing data — a
# helper who does not know is different from one who has not reached the field.
SEXES = ("female", "male", "other", "unspecified")
HANDS = ("right", "left", "ambidextrous", "unknown")
KINDS = ("person", "group")

# Avatar hue: an index into the dashboard's --av-1..8 palette, 0 = derive one
# from the id. Presentation only, but kept here so every page agrees.
AVATAR_COLORS = 8
MAX_NOTE = 120

MAX_NAME = 60
MAX_AGE = 120
MAX_PROFILES = 200


def _month() -> str:
    return datetime.now().strftime("%Y-%m")

# The keys copied onto a session. Deliberately not the whole record: `created`
# and `updated` describe the roster entry, not the recording.
SNAPSHOT_FIELDS = ("id", "name", "kind", "sex", "age_years", "dominant_hand")

_lock = threading.Lock()


# ── Disk ───────────────────────────────────────────────────────────────────

def _read() -> dict:
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"profiles": [], "active": ""}
    if not isinstance(data, dict):
        return {"profiles": [], "active": ""}
    raw = data.get("profiles")
    profiles = [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []
    active = data.get("active")
    return {"profiles": profiles,
            "active": active if isinstance(active, str) else ""}


def _write(data: dict) -> tuple[bool, str]:
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        return False, f"Could not save the profile: {exc}"
    return True, ""


# ── Validation ─────────────────────────────────────────────────────────────

def _clean_age(raw) -> int | None:
    """An age or None. Blank is a legitimate answer — the field is optional."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        age = int(float(raw))
    except (TypeError, ValueError):
        return None
    return max(0, min(MAX_AGE, age))


def _clean_color(raw) -> int:
    try:
        c = int(raw)
    except (TypeError, ValueError):
        return 0
    return c if 0 <= c <= AVATAR_COLORS else 0


def _clean_month(raw) -> str:
    """A "YYYY-MM" stamp or ""."""
    s = str(raw or "").strip()[:7]
    try:
        datetime.strptime(s, "%Y-%m")
    except ValueError:
        return ""
    return s


def normalise(raw) -> dict:
    """Coerce anything off the wire (or off disk) into a valid profile."""
    src = raw if isinstance(raw, dict) else {}
    kind = str(src.get("kind", "")).strip().lower()
    kind = kind if kind in KINDS else "person"
    sex = str(src.get("sex", "")).strip().lower()
    hand = str(src.get("dominant_hand", "")).strip().lower()
    age = _clean_age(src.get("age_years"))
    group = kind == "group"
    return {
        "id": str(src.get("id", "")).strip()[:32],
        "name": str(src.get("name", "")).strip()[:MAX_NAME],
        "kind": kind,
        # A group is many people: it has no sex, age or hand to describe.
        "sex": "unspecified" if group or sex not in SEXES else sex,
        "age_years": None if group else age,
        "dominant_hand": "unknown" if group or hand not in HANDS else hand,
        "color": _clean_color(src.get("color")),
        "note": str(src.get("note", "")).strip()[:MAX_NOTE],
        # When the age was last entered. An age is only true for a while, so
        # the dashboard says how old the number is rather than trusting it.
        "age_set": "" if age is None or group else _clean_month(src.get("age_set")),
    }


# ── Roster ─────────────────────────────────────────────────────────────────

def list_profiles() -> list[dict]:
    out = []
    for p in _read()["profiles"]:
        row = dict(normalise(p), created=p.get("created", ""),
                   updated=p.get("updated", ""))
        # Profiles made before age_set existed: the age was true when the
        # record was last touched, which is the best date there is.
        if row["age_years"] is not None and not row["age_set"]:
            row["age_set"] = _clean_month(row["updated"] or row["created"])
        out.append(row)
    return out


def get(pid: str) -> dict | None:
    if not pid:
        return None
    for p in list_profiles():
        if p["id"] == pid:
            return p
    return None


def upsert(raw) -> tuple[bool, str, dict | None]:
    """Add a profile or edit one in place. Returns (ok, message, profile)."""
    profile = normalise(raw)
    if not profile["name"]:
        return False, "Give the profile a name.", None

    now = datetime.now().isoformat(timespec="seconds")
    with _lock:
        data = _read()
        rows = data["profiles"]
        for i, existing in enumerate(rows):
            if profile["id"] and str(existing.get("id")) == profile["id"]:
                old = normalise(existing)
                if profile["age_years"] is None:
                    profile["age_set"] = ""
                elif profile["age_years"] != old["age_years"] or not old["age_set"]:
                    profile["age_set"] = _month()
                else:
                    profile["age_set"] = old["age_set"]
                rows[i] = dict(profile, created=existing.get("created", now),
                               updated=now)
                ok, msg = _write(data)
                return (ok, msg or "Profile saved.", rows[i] if ok else None)

        if len(rows) >= MAX_PROFILES:
            return False, "That is as many profiles as this hub keeps.", None
        profile["id"] = secrets.token_hex(8)
        profile["age_set"] = _month() if profile["age_years"] is not None else ""
        profile["created"] = profile["updated"] = now
        rows.append(profile)
        # The first profile added becomes the active one: somebody who has just
        # created one is about to test that person.
        if not data["active"]:
            data["active"] = profile["id"]
        ok, msg = _write(data)
        return (ok, msg or "Profile saved.", profile if ok else None)


def delete(pid: str) -> tuple[bool, str]:
    """Remove a profile from the roster.

    Saved sessions are left exactly as they are - each holds its own snapshot,
    so a person's history survives their profile being tidied away; those
    sessions simply stop matching a roster entry and read as unassigned.
    """
    with _lock:
        data = _read()
        rows = [p for p in data["profiles"] if str(p.get("id")) != pid]
        if len(rows) == len(data["profiles"]):
            return False, "That profile no longer exists."
        data["profiles"] = rows
        if data["active"] == pid:
            data["active"] = ""
        ok, msg = _write(data)
        return ok, msg or "Profile removed."


def active_id() -> str:
    data = _read()
    active = data["active"]
    if active and any(str(p.get("id")) == active for p in data["profiles"]):
        return active
    return ""


def set_active(pid: str) -> tuple[bool, str]:
    """Choose who the next launched test is recording. An empty id means
    "unassigned", which is a valid choice - not every run is a patient run."""
    pid = str(pid or "").strip()
    with _lock:
        data = _read()
        if pid and not any(str(p.get("id")) == pid for p in data["profiles"]):
            return False, "That profile no longer exists."
        data["active"] = pid
        ok, msg = _write(data)
    if not ok:
        return False, msg
    who = get(pid) if pid else None
    if who and who["kind"] == "group":
        return True, f"Recording into the group {who['name']}."
    return True, (f"Recording for {who['name']}." if who
                  else "Sessions will be saved unassigned.")


def snapshot(pid: str) -> dict:
    """What gets stamped onto a session. Empty dict for an unassigned run."""
    who = get(pid)
    return {k: who[k] for k in SNAPSHOT_FIELDS} if who else {}


def active_snapshot() -> dict:
    return snapshot(active_id())


def state() -> dict:
    """The whole roster, as the dashboard reads it."""
    return {"profiles": list_profiles(), "active": active_id()}


# ── Environment codec ──────────────────────────────────────────────────────

def env_value() -> str:
    """The active profile, encoded for the spawned tool's environment."""
    snap = active_snapshot()
    return json.dumps(snap, separators=(",", ":"), ensure_ascii=False) if snap else ""


def from_env(environ=None) -> dict:
    """The profile the launcher handed us, or {} when the tool was run straight
    from a terminal. Never raises: a malformed value must not take a test down
    at the moment it is trying to save its results."""
    raw = ((environ or os.environ).get(ENV_PROFILE) or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict) or not str(data.get("name", "")).strip():
        return {}
    clean = normalise(data)
    return {k: clean[k] for k in SNAPSHOT_FIELDS}


def is_group(snap: dict | None) -> bool:
    """True for a guest-pool snapshot, whose runs are not one person's."""
    return bool(snap) and snap.get("kind") == "group"
