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

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

_INDEX_FIELDS = [
    "session_id", "timestamp", "test", "mode", "hand", "duration_s",
    "scoreable", "taps", "frequency_hz", "mean_iti_ms", "iiv_ms", "cv_pct",
    "amplitude_cv_pct", "decrement_pct_per_s", "sync_sd_ms", "hits", "misses",
    # oculomotor (pro/anti-saccade) columns
    "error_rate_pct", "antisaccade_latency_ms", "prosaccade_latency_ms",
    "anti_minus_pro_ms", "valid_trials",
    # oculomotor fixation-stability columns
    "fixation_rms_pct", "fixation_bcea", "intrusion_rate_per_min",
    # spiral-tracing columns (self-paced smoothness/jitter)
    "sparc", "smoothness_index", "vel_cv_pct", "norm_jerk",
    "tremor_power_frac", "tremor_dominant_hz", "mean_dev_pct",
    "vel_mean_px_s", "completion_pct", "active_ratio_pct",
    # provenance — "local" for a test run on this machine, "remote" for one
    # that arrived from a participant's phone (REMOTE_SESSION_PLAN.md §3.4).
    "source", "participant",
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
                 session_id: str | None = None,
                 timestamp: datetime | None = None) -> Path:
    """Write one session JSON + append the CSV index row. Returns the JSON path.

    `source`/`participant`/`session_id`/`timestamp` exist for remote sessions
    (REMOTE_SESSION_PLAN.md §3.4): a record that arrives from a participant's
    phone already has its own id and its own clock, and overwriting either
    would break de-duplication on a retried upload. Local callers pass none of
    them and get the old behaviour.
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = timestamp or datetime.now()
    record = {
        "session_id": session_id or str(uuid.uuid4()),
        "timestamp": ts.isoformat(timespec="seconds"),
        "test": test,
        "mode": mode,
        "hand": hand,
        "duration_s": _round(duration_s),
        "source": source,
        "participant": participant,
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
        row.update({k: _round(metrics.get(k)) for k in _INDEX_FIELDS
                    if k in metrics})
        w.writerow(row)
    return path
