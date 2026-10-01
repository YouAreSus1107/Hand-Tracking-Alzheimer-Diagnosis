"""
Contract tests: the participant's page, firestore.rules, and the hub's ingest
guard all describe the same upload, in three different languages. Nothing makes
them agree automatically, and a mismatch fails at runtime in a way that is very
hard to see — the write is simply refused, on someone else's phone.

So these read the actual files and check them against each other.

Run:  python -m pytest screening_tests/tests/test_remote_contract.py
 or:  python screening_tests/tests/test_remote_contract.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core.remote import ingest, invites, relay

RULES = (_REPO_ROOT / "firestore.rules").read_text(encoding="utf-8")
APP_JS = (_REPO_ROOT / "participant" / "app.js").read_text(encoding="utf-8")
CLOUD_JS = (_REPO_ROOT / "participant" / "cloud.js").read_text(encoding="utf-8")

# The session object participant/app.js actually builds, transcribed. If this
# drifts from the page, test_app_js_builds_exactly_these_session_keys fails.
PAGE_SESSION = {
    "session_id": "11111111-2222-4333-8444-555555555555",
    "timestamp": "2026-08-24T13:05:00.000Z",
    "test": "finger_tapping",
    "mode": "big_and_fast",
    "hand": "right",
    "duration_s": 20.0,
    "participant": "Mrs Chen",
    "device": {
        "ua": "Mozilla/5.0 (iPhone)",
        "platform": "ios",
        "fps_sustained": 28.6,
        "app_version": "participant-0.2",
        "lang": "zh",
        "delegate": "GPU",
        "frame_w": 480,
        "frame_h": 640,
        "hand_detected": "right",
    },
    "metrics": {
        "scoreable": True,
        "taps": 42,
        "frequency_hz": 4.2,
        "mean_iti_ms": 238.1,
        "iiv_ms": 19.4,
        "cv_pct": 8.15,
        "amplitude_cv_pct": 12.0,
        "decrement_pct_per_s": -1.4,
        "missed_tap_forgiven": 0,
        "pause_count": 1,
        "paused_s": 2.3,
        "edge_clipped_pct": 4.1,
    },
}

VECTORS = json.loads((_REPO_ROOT / "participant" / "tests" / "vectors.json")
                     .read_text(encoding="utf-8"))


def _js_list(src: str, name: str) -> list[str]:
    block = src[src.index(f"const {name} = ["):]
    return re.findall(r'"(\w+)"', block[:block.index("];")])


def _has_only(block: str) -> set[str]:
    """The key list from a `keys().hasOnly([...])` clause in firestore.rules."""
    m = re.search(r"hasOnly\(\s*\[([^\]]*)\]", block, re.S)
    assert m, f"no hasOnly() found in:\n{block[:200]}"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def _rules_section(name: str) -> str:
    start = RULES.index(f"match /{name}/")
    return RULES[start:RULES.index("allow get, list", start)] if name == "remote_results" \
        else RULES[start:start + 1200]


# ── The upload envelope ───────────────────────────────────────────────────

def test_page_sends_exactly_the_envelope_the_rules_allow():
    section = _rules_section("remote_results")
    allowed = _has_only(section.split("request.resource.data.session.keys()")[0])
    # Slice from the body literal to the fetch that follows it — `index()`
    # from 0 would find the earlier fetch in fetchInvite and give an empty span.
    start = CLOUD_JS.index("const body = {")
    end = CLOUD_JS.index("await fetch", start)
    sent = set(re.findall(r"^\s{6}(\w+):", CLOUD_JS[start:end], re.M))
    assert sent, "could not read the upload envelope out of cloud.js"
    assert sent == allowed, f"page sends {sorted(sent)}, rules allow {sorted(allowed)}"


def test_session_keys_match_the_rules():
    section = _rules_section("remote_results")
    allowed = _has_only(section.split("request.resource.data.session.keys()")[1])
    assert set(PAGE_SESSION) == allowed, \
        f"page session {sorted(PAGE_SESSION)}, rules allow {sorted(allowed)}"


def test_app_js_builds_exactly_these_session_keys():
    """PAGE_SESSION above is a transcription; keep it honest."""
    block = APP_JS[APP_JS.index("state.session = {"):APP_JS.index("renderResult(m);")]
    keys = set(re.findall(r"^\s{4}(\w+):", block, re.M))
    assert keys == set(PAGE_SESSION), \
        f"app.js builds {sorted(keys)}, fixture has {sorted(PAGE_SESSION)}"


# ── The hub accepts what the page sends ───────────────────────────────────

def test_ingest_accepts_the_page_payload_unchanged():
    invite = invites.make_invite(test="iiv", mode="big_and_fast",
                                 participant="Mrs Chen", helper="Adam")
    record = ingest.validate(PAGE_SESSION, invite)
    assert record["session_id"] == PAGE_SESSION["session_id"]
    assert record["metrics"]["cv_pct"] == 8.15
    assert record["device"]["fps_sustained"] == 28.6


def test_app_js_sends_exactly_the_fixture_device_fields():
    block = APP_JS[APP_JS.index("    device: {"):]
    keys = set(re.findall(r"^\s{6}(\w+):", block[:block.index("    },")], re.M))
    assert keys == set(PAGE_SESSION["device"]),         f"app.js device {sorted(keys)}, fixture {sorted(PAGE_SESSION['device'])}"


def test_every_metric_the_page_sends_is_a_number_the_engine_makes():
    """METRIC_KEYS in app.js must name real compute_metrics() outputs, and
    every one must be a number or null -- ingest refuses text."""
    sent = _js_list(APP_JS, "METRIC_KEYS")
    scored = [c["metrics"] for c in VECTORS["cases"] if c["metrics"]["scoreable"]]
    assert scored
    for key in sent:
        assert key in scored[0], f"{key} is not a compute_metrics() output"
        for m in scored:
            v = m[key]
            assert v is None or isinstance(v, (int, float)), f"{key}={v!r} is not a number"
    for extra in ("status", "missed_tap_forgiven", "cv_pct_unrepaired",
                  "interruptions", "opening_shrink_ratio", "amplitude_mean"):
        assert extra == "status" or extra in sent, f"{extra} not sent"
    assert "status" not in sent and "label" not in sent and "reason" not in sent


def test_the_hub_works_out_the_verdict_itself():
    invite = invites.make_invite(test="iiv", mode="big_and_fast")
    record = ingest.validate(PAGE_SESSION, invite)
    assert record["metrics"]["status"] == "success"      # 8.15% < 15%
    assert record["metrics"]["label"] == "Within typical range"
    bad = dict(PAGE_SESSION, metrics=dict(PAGE_SESSION["metrics"], status="success"))
    try:
        ingest.validate(bad, invite)
    except ingest.Rejected:
        return
    raise AssertionError("a text metric from the phone was accepted")


def test_ema_weights_match_the_desktop():
    """The desktop keeps them in the entry script, not the engine; a mismatch
    smooths the same hand differently on the two platforms."""
    desk = (_REPO_ROOT / "screening_tests" / "finger_tapping.py").read_text(encoding="utf-8")
    engine = (_REPO_ROOT / "participant" / "engine.js").read_text(encoding="utf-8")
    for name in ("EMA_ALPHA_PACED", "EMA_ALPHA_FAST"):
        py = re.search(rf"^{name} = ([\d.]+)", desk, re.M).group(1)
        js = re.search(rf"export const {name} = ([\d.]+);", engine).group(1)
        assert float(py) == float(js), f"{name}: desktop {py}, phone {js}"
    assert "EMA_ALPHA = emaAlpha(MODE)" in APP_JS


def test_resume_guard_matches_the_desktop():
    desk = (_REPO_ROOT / "screening_tests" / "finger_tapping.py").read_text(encoding="utf-8")
    py = re.search(r"^RESUME_GUARD_S = ([\d.]+)", desk, re.M).group(1)
    js = re.search(r"const RESUME_GUARD_S = ([\d.]+);", APP_JS).group(1)
    assert float(py) == float(js)


def test_every_device_field_the_page_sends_survives_the_allowlist():
    invite = invites.make_invite(test="iiv", mode="big_and_fast")
    record = ingest.validate(PAGE_SESSION, invite)
    for key in PAGE_SESSION["device"]:
        assert key in record["device"], f"{key} dropped by the device allowlist"


def test_page_mode_is_one_the_invite_can_carry():
    modes = invites.TESTS["iiv"]["modes"]
    assert PAGE_SESSION["mode"] in modes
    assert PAGE_SESSION["test"] == invites.session_test("iiv")


def test_every_mode_the_hub_offers_is_one_the_phone_can_score():
    """An invite for a mode engine.js does not have used to be run as Big &
    Fast tapping and filed under the invite's name (REMOTE_SESSION_PLAN §9)."""
    engine = (_REPO_ROOT / "participant" / "engine.js").read_text(encoding="utf-8")
    block = engine[engine.index("export const MODES = {"):]
    block = block[:block.index("\n};")]
    ported = set(re.findall(r"^  (\w+): \{", block, re.M))
    offered = {(k, m) for k, spec in invites.offered().items() for m in spec["modes"]}
    assert offered, "the hub offers nothing at all"
    for key, mode in offered:
        assert invites.session_test(key) == "finger_tapping",             f"{key} offered, but the page only runs finger tapping"
        assert mode in ported, f"{key}/{mode} offered, engine.js has {sorted(ported)}"


def test_page_refuses_invites_it_cannot_run():
    assert "supported(invite)" in APP_JS


def _node_check(script: str) -> None:
    """Run one of the participant page's Node checks. Skipped, loudly, where
    Node is not installed; it is a dependency of the page's tests only."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        print(f"  SKIP  {script}: node not found")
        return
    r = subprocess.run([node, str(_REPO_ROOT / "participant" / "tests" / script)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]


def test_participant_page_is_fully_translated():
    """An invite's lang="zh" must not reach an English line (i18n_check.mjs)."""
    _node_check("i18n_check.mjs")


def test_every_element_app_js_uses_exists_in_the_page():
    """A $("id") with no element throws on the phone, mid-flow, where nobody
    can see the console."""
    html = (_REPO_ROOT / "participant" / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([\w-]+)"', html))
    used = set(re.findall(r'\$\("([\w-]+)"\)', APP_JS))
    used |= set(re.findall(r'"(s-[\w-]+)"', APP_JS))
    used |= {f"btn-hand-{side}" for side in ("left", "right")}   # built in a loop
    assert used, "found no element lookups in app.js"
    assert not used - ids, f"app.js uses ids the page lacks: {sorted(used - ids)}"


def test_participant_engine_matches_python():
    """The golden vectors (parity.mjs) -- cheap enough to run with the rest."""
    _node_check("parity.mjs")


# ── Invite fields the page reads ──────────────────────────────────────────

def test_publish_invite_carries_every_field_the_page_reads():
    """participant/app.js reads these off the Firestore invite document."""
    needed = {"helper", "participant", "lang", "mode", "session_test",
              "expires_at", "uses_left", "revoked", "helper_uid"}
    src = relay.publish_invite.__doc__ or ""
    block = _REPO_ROOT / "core" / "remote" / "relay.py"
    text = block.read_text(encoding="utf-8")
    published = set(re.findall(r'"(\w+)"', text[text.index("def publish_invite"):
                                                text.index("def delete_result")]))
    missing = needed - published
    assert not missing, f"publish_invite does not send {sorted(missing)}"


def test_expires_at_is_published_as_a_timestamp_not_a_string():
    """firestore.rules compares expires_at with request.time, which only works
    on a timestampValue."""
    text = (_REPO_ROOT / "core" / "remote" / "relay.py").read_text(encoding="utf-8")
    block = text[text.index("def publish_invite"):text.index("def delete_result")]
    assert "timestampValue" in block
    assert "expires_at is timestamp" in RULES


def test_invite_expiry_round_trips_through_rfc3339():
    inv = invites.make_invite(test="iiv", now=datetime(2026, 8, 24, 12, 0,
                                                       tzinfo=timezone.utc))
    stamp = inv["expires_at"]
    rfc = stamp[:-6] + "Z" if stamp.endswith("+00:00") else stamp
    # Both ends must be able to read it: Python here, Date.parse() on the page.
    assert datetime.fromisoformat(rfc.replace("Z", "+00:00"))
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$", rfc)


# ── Collection names ──────────────────────────────────────────────────────

def test_collection_names_agree_across_all_three():
    assert f"match /{relay.INVITES}/" in RULES
    assert f"match /{relay.RESULTS}/" in RULES
    assert f"/{relay.INVITES}/" in CLOUD_JS
    assert f"/{relay.RESULTS}" in CLOUD_JS


def test_rules_never_let_a_participant_read_results():
    section = _rules_section("remote_results")
    assert "allow update: if false" in RULES
    # Read is restricted to the owning helper, not merely to any signed-in user.
    assert "resource.data.helper_uid == request.auth.uid" in RULES


def test_invites_cannot_be_enumerated():
    """Without a list rule the collection cannot be walked, so a token is only
    useful to whoever was sent it (§6, link forwarding)."""
    assert "allow list: if false" in RULES


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
