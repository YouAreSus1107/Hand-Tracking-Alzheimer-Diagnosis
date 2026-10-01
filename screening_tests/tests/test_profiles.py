"""
Unit tests for patient profiles: the roster (core/profiles.py) and the way a
profile reaches a saved session (core/session.py).

Everything here writes to a temporary directory — the real roster and the real
results/ folder are never touched.

Run:  python -m pytest screening_tests/tests/test_profiles.py
 or:  python screening_tests/tests/test_profiles.py   (self-runs without pytest)
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core import profiles, session as session_store


class _Sandbox:
    """Point both modules at a scratch directory for the length of a test."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._saved = (profiles.PROFILES_FILE, session_store.RESULTS_DIR)
        profiles.PROFILES_FILE = root / ".launcher_profiles.json"
        session_store.RESULTS_DIR = root / "results"
        return root

    def __exit__(self, *exc):
        profiles.PROFILES_FILE, session_store.RESULTS_DIR = self._saved
        self._tmp.cleanup()
        return False


def _save(**kw):
    kw.setdefault("test", "finger_tapping")
    kw.setdefault("mode", "big_and_fast")
    kw.setdefault("hand", "Right")
    kw.setdefault("duration_s", 10.0)
    kw.setdefault("device", {"camera_fps": 30.0})
    kw.setdefault("metrics", {"cv_pct": 8.4, "scoreable": True})
    kw.setdefault("raw", {})
    return session_store.save_session(**kw)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _index_rows(root):
    with open(root / "results" / "index.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ── Roster ─────────────────────────────────────────────────────────────────

def test_normalise_clamps_and_falls_back_to_the_known_vocabularies():
    p = profiles.normalise({"name": "  Jane Chen  ", "sex": "FEMALE",
                            "age_years": "68.7", "dominant_hand": "Left"})
    assert p["name"] == "Jane Chen"
    assert p["sex"] == "female" and p["dominant_hand"] == "left"
    assert p["age_years"] == 68
    junk = profiles.normalise({"name": "x", "sex": "yes", "age_years": "abc",
                               "dominant_hand": "sideways"})
    assert junk["sex"] == "unspecified" and junk["dominant_hand"] == "unknown"
    assert junk["age_years"] is None
    assert profiles.normalise({"name": "y", "age_years": 999})["age_years"] == 120
    assert profiles.normalise("not a dict")["name"] == ""


def test_a_nameless_profile_is_refused():
    with _Sandbox():
        ok, msg, made = profiles.upsert({"name": "   ", "sex": "male"})
        assert not ok and made is None and "name" in msg.lower()


def test_first_profile_becomes_active_and_edits_keep_the_id():
    with _Sandbox():
        ok, _, jane = profiles.upsert({"name": "Jane", "sex": "female",
                                       "age_years": 68})
        assert ok and profiles.active_id() == jane["id"]
        ok, _, wei = profiles.upsert({"name": "Wei", "sex": "male"})
        assert ok and profiles.active_id() == jane["id"]   # not stolen

        ok, _, edited = profiles.upsert(dict(jane, age_years=69))
        assert ok and edited["id"] == jane["id"] and edited["age_years"] == 69
        assert len(profiles.list_profiles()) == 2
        assert edited["created"] == jane["created"]
        assert wei["id"] != jane["id"]


def test_deleting_the_active_profile_leaves_the_hub_unassigned():
    with _Sandbox():
        _, _, jane = profiles.upsert({"name": "Jane"})
        ok, _ = profiles.delete(jane["id"])
        assert ok and profiles.active_id() == "" and profiles.list_profiles() == []
        assert not profiles.delete(jane["id"])[0]
        assert not profiles.set_active("gone")[0]


def test_snapshot_carries_the_clinical_fields_and_nothing_else():
    with _Sandbox():
        _, _, jane = profiles.upsert({"name": "Jane", "sex": "female",
                                      "age_years": 68, "dominant_hand": "right"})
        snap = profiles.snapshot(jane["id"])
        assert set(snap) == set(profiles.SNAPSHOT_FIELDS)
        assert "created" not in snap and "updated" not in snap
        assert profiles.snapshot("nobody") == {}


def test_env_codec_round_trips_and_survives_junk():
    with _Sandbox():
        _, _, jane = profiles.upsert({"name": "Jane", "sex": "female",
                                      "age_years": 68})
        profiles.set_active(jane["id"])
        env = {profiles.ENV_PROFILE: profiles.env_value()}
        assert profiles.from_env(env) == profiles.snapshot(jane["id"])
        for bad in ("", "   ", "not json", "[]", '{"name":"  "}'):
            assert profiles.from_env({profiles.ENV_PROFILE: bad}) == {}
        assert profiles.from_env({}) == {}


def test_a_group_has_no_person_details_and_says_so_in_its_snapshot():
    """A guest pool is many people: sex, age and hand are forced blank, and
    the kind rides onto the session so the tapping test can skip the
    personal baseline."""
    with _Sandbox():
        _, _, g = profiles.upsert({"name": "Screening day", "kind": "group",
                                   "sex": "female", "age_years": 70,
                                   "dominant_hand": "left", "note": "Hall B"})
        assert g["kind"] == "group" and g["note"] == "Hall B"
        assert g["sex"] == "unspecified" and g["age_years"] is None
        assert g["dominant_hand"] == "unknown" and g["age_set"] == ""
        snap = profiles.snapshot(g["id"])
        assert snap["kind"] == "group" and profiles.is_group(snap)
        profiles.set_active(g["id"])
        assert profiles.is_group(profiles.from_env(
            {profiles.ENV_PROFILE: profiles.env_value()}))
        assert not profiles.is_group({}) and not profiles.is_group({"name": "x"})


def test_unknown_kind_and_colour_fall_back():
    p = profiles.normalise({"name": "x", "kind": "team", "color": 42})
    assert p["kind"] == "person" and p["color"] == 0
    assert profiles.normalise({"name": "x", "color": "3"})["color"] == 3


def test_age_set_is_stamped_on_change_and_kept_otherwise():
    with _Sandbox():
        _, _, jane = profiles.upsert({"name": "Jane", "age_years": 68})
        assert jane["age_set"] == profiles._month()
        # An edit that leaves the age alone keeps its stamp, even an old one.
        stored = profiles._read()
        stored["profiles"][0]["age_set"] = "2024-01"
        profiles._write(stored)
        _, _, same = profiles.upsert(dict(jane, name="Jane C", age_set="2024-01"))
        assert same["age_set"] == "2024-01"
        _, _, older = profiles.upsert(dict(same, age_years=69))
        assert older["age_set"] == profiles._month()
        _, _, blank = profiles.upsert(dict(older, age_years=""))
        assert blank["age_set"] == ""


def test_a_profile_from_before_age_set_is_dated_by_its_last_edit():
    with _Sandbox():
        profiles._write({"profiles": [{"id": "a", "name": "Old", "age_years": 73,
                                       "created": "2026-08-26T00:05:41",
                                       "updated": "2026-08-27T12:00:00"}],
                         "active": ""})
        assert profiles.list_profiles()[0]["age_set"] == "2026-08"


# ── The session a test writes ──────────────────────────────────────────────

def test_a_local_session_picks_up_the_active_profile_from_the_environment():
    """The three test scripts pass no profile — this is the whole mechanism."""
    import os
    with _Sandbox() as root:
        _, _, jane = profiles.upsert({"name": "Jane", "sex": "female",
                                      "age_years": 68, "dominant_hand": "right"})
        os.environ[profiles.ENV_PROFILE] = profiles.env_value()
        try:
            record = _read(_save())
        finally:
            os.environ.pop(profiles.ENV_PROFILE, None)

        assert record["profile"]["id"] == jane["id"]
        assert record["profile"]["name"] == "Jane"
        row = _index_rows(root)[0]
        assert row["profile_name"] == "Jane" and row["sex"] == "female"
        assert row["age_years"] == "68" and row["dominant_hand"] == "right"


def test_no_active_profile_saves_an_unassigned_session():
    import os
    with _Sandbox() as root:
        os.environ.pop(profiles.ENV_PROFILE, None)
        record = _read(_save())
        assert record["profile"] == {}
        assert _index_rows(root)[0]["profile_name"] == ""


def test_a_remote_session_is_never_given_the_local_profile():
    """A record from a stranger's phone must not inherit whoever is set on this
    machine — it is assigned from the hub, by a human, afterwards."""
    import os
    from datetime import datetime
    with _Sandbox():
        _, _, jane = profiles.upsert({"name": "Jane"})
        profiles.set_active(jane["id"])
        os.environ[profiles.ENV_PROFILE] = profiles.env_value()
        try:
            record = _read(_save(source=session_store.REMOTE,
                                 participant="Mrs Chen",
                                 session_id="remote-1",
                                 timestamp=datetime(2026, 8, 24, 12, 0)))
        finally:
            os.environ.pop(profiles.ENV_PROFILE, None)
        assert record["profile"] == {}
        assert record["participant"] == "Mrs Chen"


def test_an_explicit_profile_beats_the_environment():
    import os
    with _Sandbox():
        _, _, jane = profiles.upsert({"name": "Jane"})
        os.environ[profiles.ENV_PROFILE] = profiles.env_value()
        try:
            record = _read(_save(profile={"id": "x", "name": "Wei"}))
        finally:
            os.environ.pop(profiles.ENV_PROFILE, None)
        assert record["profile"]["name"] == "Wei"
        assert jane["name"] == "Jane"


# ── Reassignment ───────────────────────────────────────────────────────────

def test_reassign_moves_both_the_json_and_the_index_row():
    with _Sandbox() as root:
        _, _, jane = profiles.upsert({"name": "Jane", "sex": "female",
                                      "age_years": 68})
        _, _, wei = profiles.upsert({"name": "Wei", "sex": "male",
                                     "age_years": 71})
        path = _save(profile=profiles.snapshot(jane["id"]))
        sid = _read(path)["session_id"]

        assert session_store.reassign(sid, profiles.snapshot(wei["id"]))
        assert _read(path)["profile"]["name"] == "Wei"
        row = _index_rows(root)[0]
        assert row["profile_name"] == "Wei" and row["age_years"] == "71"

        # ...and back to nobody.
        assert session_store.reassign(sid, {})
        assert _read(path)["profile"] == {}
        row = _index_rows(root)[0]
        assert row["profile_name"] == "" and row["sex"] == ""


def test_reassign_refuses_an_id_it_cannot_find():
    with _Sandbox():
        _save()
        assert not session_store.reassign("no-such-session", {})
        assert not session_store.reassign("", {})


def test_reassign_touches_only_the_session_it_was_given():
    with _Sandbox() as root:
        _, _, jane = profiles.upsert({"name": "Jane"})
        first = _read(_save(profile=profiles.snapshot(jane["id"])))
        second = _read(_save(mode="paced",
                             profile=profiles.snapshot(jane["id"])))
        session_store.reassign(second["session_id"], {})
        rows = {r["session_id"]: r for r in _index_rows(root)}
        assert rows[first["session_id"]]["profile_name"] == "Jane"
        assert rows[second["session_id"]]["profile_name"] == ""


def test_an_index_written_before_profiles_existed_gains_the_columns():
    """_migrate_index rewrites the header; old rows keep every value they had
    and simply have empty profile columns."""
    with _Sandbox() as root:
        results = root / "results"
        results.mkdir()
        legacy = [f for f in session_store._INDEX_FIELDS
                  if f not in ("profile_id", "profile_name", "sex",
                               "age_years", "dominant_hand")]
        with open(results / "index.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=legacy)
            w.writeheader()
            w.writerow({"session_id": "old-1", "test": "finger_tapping",
                        "mode": "paced", "cv_pct": 12.5})

        _save()
        rows = _index_rows(root)
        assert rows[0]["session_id"] == "old-1" and rows[0]["cv_pct"] == "12.5"
        assert rows[0]["profile_name"] == ""
        assert len(rows) == 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
