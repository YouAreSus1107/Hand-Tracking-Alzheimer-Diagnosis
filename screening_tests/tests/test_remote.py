"""
Unit tests for the remote-session layer (REMOTE_SESSION_PLAN.md §3, §4):
invite lifecycle, the ingest guard, and Firestore's value-typed JSON — all
pure, no network, no Firebase project.

Run:  python -m pytest screening_tests/tests/test_remote.py
 or:  python screening_tests/tests/test_remote.py   (self-runs without pytest)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.remote import invites, relay
from core.remote.ingest import (BANNED_KEYS, MAX_METRICS, Rejected, validate)

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _invite(**kw):
    kw.setdefault("test", "iiv")
    kw.setdefault("mode", "big_and_fast")
    kw.setdefault("now", NOW)
    return invites.make_invite(**kw)


def _payload(**kw):
    base = {
        "session_id": "abc-123",
        "timestamp": "2026-08-24T12:30:00",
        "test": "finger_tapping",     # the session vocabulary, not the tool key
        "mode": "big_and_fast",
        "hand": "Right",
        "duration_s": 10.0,
        "participant": "Mrs Chen",
        "device": {"ua": "iPhone", "fps_sustained": 29.5},
        "metrics": {"cv_pct": 8.4, "taps": 42, "scoreable": True},
    }
    base.update(kw)
    return base


# ── Invites ───────────────────────────────────────────────────────────────

def test_token_is_128_bits_and_url_safe():
    token = invites.new_token()
    assert invites.valid_token_shape(token)
    assert "/" not in token and "+" not in token and "=" not in token


def test_bad_token_shapes_rejected():
    for bad in ("", "short", "has spaces here!!", None, 12, "x" * 200, "a/b"):
        assert not invites.valid_token_shape(bad)


def test_new_invite_is_live():
    inv = _invite()
    assert invites.state(inv, NOW) == invites.LIVE
    assert invites.refusal(inv, NOW) is None


def test_unknown_test_and_mode_refused():
    for kw in ({"test": "nope"}, {"test": "iiv", "mode": "sideways"},
               {"test": "iiv", "mode": "max", "lang": "fr"}):
        try:
            _invite(**kw)
        except ValueError:
            continue
        raise AssertionError(f"accepted {kw}")


def test_expiry_is_enforced():
    inv = _invite(ttl_hours=2)
    assert invites.is_live(inv, NOW + timedelta(hours=1))
    assert invites.state(inv, NOW + timedelta(hours=3)) == invites.EXPIRED
    assert "expired" in invites.refusal(inv, NOW + timedelta(hours=3)).lower()


def test_ttl_and_uses_are_clamped():
    inv = _invite(ttl_hours=99999, uses=99999)
    assert inv["uses_left"] == invites.MAX_USES
    expires = datetime.fromisoformat(inv["expires_at"])
    assert expires <= NOW + timedelta(hours=invites.MAX_TTL_HOURS)


def test_spend_consumes_one_use_and_records_the_session():
    inv = _invite(uses=2)
    once = invites.spend(inv, "s1", NOW)
    assert once["uses_left"] == 1 and once["sessions"] == ["s1"]
    twice = invites.spend(once, "s2", NOW)
    assert twice["uses_left"] == 0
    assert invites.state(twice, NOW) == invites.SPENT
    # The original is untouched — spend() returns a copy.
    assert inv["uses_left"] == 2


def test_spend_is_idempotent_for_a_repeated_session_id():
    once = invites.spend(_invite(uses=3), "s1", NOW)
    twice = invites.spend(once, "s1", NOW)
    assert twice["sessions"] == ["s1"]


def test_revocation_beats_exhaustion_and_expiry():
    inv = _invite(uses=1, ttl_hours=1)
    inv["revoked"] = True
    inv["uses_left"] = 0
    assert invites.state(inv, NOW + timedelta(hours=5)) == invites.REVOKED
    assert "cancelled" in invites.refusal(inv, NOW).lower()


def test_unknown_invite_refused_without_saying_why():
    message = invites.refusal(None, NOW)
    assert message and "not valid" in message.lower()


def test_link_shape():
    inv = _invite()
    assert invites.link(inv["token"], "https://x.app/") == f"https://x.app/s/{inv['token']}"


# ── Ingest: the §4 upload rule ────────────────────────────────────────────

def test_clean_payload_validates():
    record = validate(_payload(), _invite())
    assert record["session_id"] == "abc-123"
    assert record["metrics"]["cv_pct"] == 8.4
    assert record["participant"] == "Mrs Chen"


def test_every_banned_key_is_refused_at_any_depth():
    for key in sorted(BANNED_KEYS):
        for payload in (_payload(**{key: "x"}),
                        _payload(device={"ua": "iPhone", key: "x"}),
                        _payload(metrics={"cv_pct": 1.0, "nested": {key: [1, 2]}})):
            try:
                validate(payload, _invite())
            except Rejected:
                break
            else:
                raise AssertionError(f"{key!r} accepted")


def test_test_must_match_the_invite():
    for payload in (_payload(test="spiral"), _payload(mode="paced")):
        try:
            validate(payload, _invite(test="iiv", mode="big_and_fast"))
        except Rejected:
            continue
        raise AssertionError("mismatched test accepted")


def test_non_numeric_and_non_finite_metrics_refused():
    for metrics in ({"cv_pct": "8.4"}, {"cv_pct": float("nan")},
                    {"cv_pct": float("inf")}, {"cv_pct": [1, 2]}):
        try:
            validate(_payload(metrics=metrics), _invite())
        except Rejected:
            continue
        raise AssertionError(f"accepted {metrics}")


def test_empty_or_oversized_metrics_refused():
    for metrics in ({}, {f"m{i}": 1.0 for i in range(MAX_METRICS + 1)}):
        try:
            validate(_payload(metrics=metrics), _invite())
        except Rejected:
            continue
        raise AssertionError("bad metrics count accepted")


def test_implausible_duration_refused():
    for duration in (0, -5, 99999):
        try:
            validate(_payload(duration_s=duration), _invite())
        except Rejected:
            continue
        raise AssertionError(f"duration {duration} accepted")


def test_missing_session_id_refused():
    try:
        validate(_payload(session_id=""), _invite())
    except Rejected:
        return
    raise AssertionError("empty session id accepted")


def test_device_is_allowlisted_not_passed_through():
    record = validate(_payload(device={"ua": "iPhone", "gps": "51.5,0.1",
                                       "contacts": "x"}), _invite())
    assert "gps" not in record["device"] and "contacts" not in record["device"]
    assert record["device"]["ua"] == "iPhone"
    assert record["device"]["source"] == "remote"


def test_participant_falls_back_to_the_invite_name():
    record = validate(_payload(participant=""), _invite(participant="Mr Lee"))
    assert record["participant"] == "Mr Lee"


def test_bad_clock_does_not_lose_the_session():
    record = validate(_payload(timestamp="not-a-date"), _invite())
    assert isinstance(record["timestamp"], datetime)


def test_deeply_nested_payload_refused():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}}
    try:
        validate(_payload(metrics={"cv_pct": 1.0, "x": deep}), _invite())
    except Rejected:
        return
    raise AssertionError("deep nesting accepted")


# ── Ingest: filing, de-duplication, and filename collisions ───────────────
# Both of these were live bugs, caught by driving the flow end to end.

def test_duplicate_upload_is_flagged_not_filed(tmpdir=None):
    """A retry after a dropped connection must not spend a second use of the
    invite — `accept()` says so via record["filed"]."""
    import tempfile
    from pathlib import Path
    from core import session as ss
    from core.remote import ingest

    with tempfile.TemporaryDirectory() as tmp:
        original = ss.RESULTS_DIR
        ss.RESULTS_DIR = Path(tmp)
        try:
            inv = _invite()
            ok, _msg, first = ingest.accept(_payload(), inv)
            assert ok and first["filed"] is True
            ok, msg, again = ingest.accept(_payload(), inv)
            assert ok and again["filed"] is False
            assert "already" in msg.lower()
            assert len(list(Path(tmp).glob("*.json"))) == 1
        finally:
            ss.RESULTS_DIR = original


def test_two_remote_sessions_on_the_same_second_do_not_collide():
    """Remote records carry the participant's clock, so the filename cannot be
    timestamp-only or the second one silently overwrites the first."""
    import tempfile
    from pathlib import Path
    from core import session as ss
    from core.remote import ingest

    with tempfile.TemporaryDirectory() as tmp:
        original = ss.RESULTS_DIR
        ss.RESULTS_DIR = Path(tmp)
        try:
            inv = _invite(uses=5)
            ingest.accept(_payload(session_id="aaaa-1"), inv)
            ingest.accept(_payload(session_id="bbbb-2"), inv)   # same timestamp
            files = sorted(Path(tmp).glob("*.json"))
            assert len(files) == 2, [f.name for f in files]
            import json as _json
            ids = {_json.loads(f.read_text(encoding="utf-8"))["session_id"] for f in files}
            assert ids == {"aaaa-1", "bbbb-2"}
        finally:
            ss.RESULTS_DIR = original


def test_local_sessions_keep_their_original_filename_shape():
    """The remote suffix must not leak into locally run tests."""
    import tempfile
    from pathlib import Path
    from core import session as ss

    with tempfile.TemporaryDirectory() as tmp:
        original = ss.RESULTS_DIR
        ss.RESULTS_DIR = Path(tmp)
        try:
            path = ss.save_session(test="iiv", mode="max", hand="Right",
                                   duration_s=10.0, device={}, metrics={"cv_pct": 8.0},
                                   raw={})
            assert path.name.endswith("_iiv_max.json"), path.name
            rec = __import__("json").loads(path.read_text(encoding="utf-8"))
            assert rec["source"] == ss.LOCAL and rec["participant"] == ""
        finally:
            ss.RESULTS_DIR = original


# ── Relay: Firestore's value-typed JSON ───────────────────────────────────

def test_decode_scalar_values():
    assert relay.decode_value({"stringValue": "x"}) == "x"
    assert relay.decode_value({"integerValue": "42"}) == 42
    assert relay.decode_value({"doubleValue": 1.5}) == 1.5
    assert relay.decode_value({"booleanValue": True}) is True
    assert relay.decode_value({"nullValue": None}) is None
    assert relay.decode_value({"bogusValue": 1}) is None


def test_decode_nested_document():
    doc = {
        "name": "projects/p/databases/(default)/documents/remote_results/xyz",
        "fields": {
            "invite_token": {"stringValue": "tok"},
            "session": {"mapValue": {"fields": {
                "metrics": {"mapValue": {"fields": {
                    "cv_pct": {"doubleValue": 8.4}}}},
                "tags": {"arrayValue": {"values": [{"stringValue": "a"}]}},
            }}},
        },
    }
    out = relay.decode_document(doc)
    assert out["_id"] == "xyz"
    assert out["session"]["metrics"]["cv_pct"] == 8.4
    assert out["session"]["tags"] == ["a"]


def test_decode_documents_handles_both_response_shapes():
    doc = {"name": "a/b/c", "fields": {"x": {"integerValue": "1"}}}
    assert relay.decode_documents({"documents": [doc]})[0]["x"] == 1
    assert relay.decode_documents([{"document": doc}])[0]["x"] == 1
    assert relay.decode_documents({}) == []
    assert relay.decode_documents(None) == []


def test_encode_round_trips():
    record = {"token": "t", "uses_left": 2, "revoked": False,
              "meta": {"lang": "en"}, "tags": ["a", "b"]}
    decoded = {k: relay.decode_value(v)
               for k, v in relay.encode_fields(record)["fields"].items()}
    assert decoded == record


def test_relay_reports_what_is_missing_and_never_echoes_secrets():
    st = relay.status()
    assert set(st["missing"]) <= {"project_id", "api_key", "id_token"}
    assert "api_key" not in st and "id_token" not in st


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
