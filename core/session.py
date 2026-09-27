"""
Session persistence — the shared results schema every test writes to
(FINGER_TAPPING_REVISION_PLAN.md §C4). One JSON per session in results/,
plus an append-only CSV index for quick longitudinal views. The same schema
is intended for the spiral test and the future glove validation stream.
"""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path

from core import profiles

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

_INDEX_FIELDS = [
    "session_id", "timestamp", "test", "mode", "hand", "duration_s",
    "scoreable", "taps", "frequency_hz", "mean_iti_ms", "iiv_ms", "cv_pct",
    "amplitude_cv_pct", "decrement_pct_per_s", "sync_sd_ms", "hits", "misses",
    "n_intervals", "cv_ci_low_pct", "cv_ci_high_pct", "confidence_pct",
    "band_edge", "taps_w10", "frequency_hz_w10", "cv_pct_w10",
    "near_miss_taps",
    # oculomotor (pro/anti-saccade) columns
    "error_rate_pct", "antisaccade_latency_ms", "prosaccade_latency_ms",
    "anti_minus_pro_ms", "valid_trials",
    "error_ci_low_pct", "error_ci_high_pct", "anticipatory_rate_pct",
    # oculomotor fixation-stability columns
    "fixation_rms_pct", "fixation_bcea", "intrusion_rate_per_min",
    # spiral-tracing columns (self-paced smoothness/jitter)
    "sparc", "smoothness_index", "vel_cv_pct", "norm_jerk",
    "tremor_power_frac", "tremor_dominant_hz", "mean_dev_pct",
    "vel_mean_px_s", "completion_pct", "active_ratio_pct",
    # speech rhythm (DDK) columns — decrement_pct_per_s, n_intervals and the
    # confidence columns above are shared with tapping (same definitions)
    "syllables", "syllable_rate_hz", "rhythm_cv_pct", "npvi", "snr_db",
    "sequence_error_pct", "count_agreement_pct",
    # sustained phonation columns — snr_db above is shared with DDK
    "jitter_pct", "shimmer_pct", "hnr_db", "f0_mean_hz", "f0_sd_hz",
    "vocal_tremor_hz", "voiced_pct",
    # hand tremor columns (TREMOR_TEST_PLAN.md) — confidence_pct is shared
    "tremor_amp_pct", "tremor_peak_hz", "rest_amp_left_pct",
    "rest_amp_right_pct", "rest_peak_hz", "count_amp_pct", "postural_amp_pct",
    "postural_peak_hz", "asymmetry_ratio", "emergence_ratio",
    "glove_rest_peak_hz", "cam_glove_hz_diff",
    # provenance — "local" for a test run on this machine, "remote" for one
    # that arrived from a participant's phone (REMOTE_SESSION_PLAN.md §3.4).
    "source", "participant",
    # who the session belongs to — a snapshot of the profile that was active
    # when it was recorded (core/profiles.py), not a live lookup.
    "profile_id", "profile_name", "sex", "age_years", "dominant_hand",
]

LOCAL, REMOTE = "local", "remote"


def _migrate_index(index: Path) -> None:
    """Rewrite index.csv under the current header when columns were added.
    Old rows keep their values; new columns stay empty."""
    with open(index, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == _INDEX_FIELDS:
            return
        rows = list(reader)
    with open(index, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_INDEX_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _round(v, nd=2):
    return round(v, nd) if isinstance(v, float) else v


def save_session(*, test: str, mode: str, hand: str | None, duration_s: float,
                 device: dict, metrics: dict, raw: dict,
                 source: str = LOCAL, participant: str = "",
                 profile: dict | None = None,
                 session_id: str | None = None,
                 timestamp: datetime | None = None) -> Path:
    """Write one session JSON + append the CSV index row. Returns the JSON path.

    `source`/`participant`/`session_id`/`timestamp` exist for remote sessions
    (REMOTE_SESSION_PLAN.md §3.4): a record that arrives from a participant's
    phone already has its own id and its own clock, and overwriting either
    would break de-duplication on a retried upload. Local callers pass none of
    them and get the old behaviour.

    `profile` says who was tested. A local caller passes nothing and the active
    profile is read from the environment the launcher set (core/profiles.py),
    which is why the test scripts need to know nothing about profiles. What is
    stored is a snapshot, so editing or deleting the profile later never
    rewrites what this recording said. Remote records are never given one here:
    they arrive from a stranger's phone and are assigned from the hub.
    """
    if profile is None:
        profile = profiles.from_env() if source == LOCAL else {}
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = timestamp or datetime.now()
    record = {
        "session_id": session_id or str(uuid.uuid4()),
        "timestamp": ts.isoformat(timespec="seconds"),
        "test": test,
        "mode": mode,
        "hand": hand,
        # Hand labels from here on use core/hand_utils.true_hand(); older
        # records carry the reversed label until tools/fix_hand_labels.py runs.
        "hand_label_fixed": True,
        "duration_s": _round(duration_s),
        "source": source,
        "participant": participant,
        "profile": profile,
        "device": device,
        "metrics": {k: _round(v) for k, v in metrics.items()},
        "raw": raw,
    }

    stem = f"{ts:%Y%m%d_%H%M%S}_{test}_{mode}"
    if source != LOCAL:
        # A remote record carries the participant's clock, so two of them can
        # land on the same second and silently overwrite each other. The id is
        # what actually distinguishes them, so part of it goes in the name.
        stem = f"{stem}_{source}_{record['session_id'][:8]}"
    path = RESULTS_DIR / f"{stem}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1)

    index = RESULTS_DIR / "index.csv"
    new = not index.exists()
    if not new:
        _migrate_index(index)
    with open(index, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_INDEX_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        row = {"session_id": record["session_id"], "timestamp": record["timestamp"],
               "test": test, "mode": mode, "hand": hand,
               "duration_s": record["duration_s"],
               "source": source, "participant": participant}
        row.update(_profile_row(profile))
        row.update({k: _round(metrics.get(k)) for k in _INDEX_FIELDS
                    if k in metrics})
        w.writerow(row)
    return path


def _profile_row(profile: dict | None) -> dict:
    """The profile's columns in index.csv. An unassigned session leaves them
    empty rather than absent, so a reassignment can clear them again."""
    p = profile or {}
    return {"profile_id": p.get("id", ""), "profile_name": p.get("name", ""),
            "sex": p.get("sex", ""), "age_years": p.get("age_years", ""),
            "dominant_hand": p.get("dominant_hand", "")}


def reassign(session_id: str, profile: dict | None) -> bool:
    """Move one already-saved session to a different profile (or to none).

    The JSON and the index row have to move together, so both live here. The id
    is matched against the `session_id` *inside* each file rather than used to
    build a path — same reason as launcher.session_payload(): on the published
    dashboard that value is attacker-controlled.
    """
    if not session_id or not RESULTS_DIR.is_dir():
        return False
    snap = profile or {}
    found = False
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("session_id") != session_id:
            continue
        record["profile"] = snap
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(record, fh, indent=1)
        except OSError:
            return False
        found = True
        break
    if not found:
        return False

    index = RESULTS_DIR / "index.csv"
    if index.exists():
        _migrate_index(index)
        with open(index, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            if row.get("session_id") == session_id:
                row.update(_profile_row(snap))
        with open(index, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=_INDEX_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return True
