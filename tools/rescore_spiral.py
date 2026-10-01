"""
Rescore saved spiral sessions with the current spiral engine (3: noise-aware
SPARC cutoff; two scores, line accuracy and tremor).

Engine 1 found SPARC's adaptive cutoff with the canonical fixed 5 % threshold,
which the webcam's tracker-noise floor crossed at random: clean runs scored
-6 to -14 (smoothness index 0). core/spiral/metrics.sparc() has the details.
Every saved run keeps its raw fingertip samples, so the fields the engine changes
can be recomputed exactly: the FIELDS below. Engine 4 (2026-10-01) reports two
scores, line accuracy and tremor, and SPARC only as a reading; the
spiral's radius comes from raw.spiral, or the old fixed 0.40 x 480 px layout.
Everything else in the record is left alone.

The engine-1 values are kept under metrics["v1"] (never overwritten by a later
rescore), the record is stamped with the current engine_version, so a second
run changes nothing. The JSON and
its index.csv row move together (the pattern of core/session.reassign).
Frames that were never recorded (hand lost or at the edge) stay out, as they
were when the run was scored; only the short pre-roll the live run trimmed
before each edge blackout is back in, which is not a gap worth a field.

Dry run by default:

    .venv/Scripts/python tools/rescore_spiral.py
    .venv/Scripts/python tools/rescore_spiral.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from core.spiral import metrics as M              # noqa: E402
from core.session import _INDEX_FIELDS, _round   # noqa: E402

FIELDS = ("sparc", "smoothness_index", "status", "label", "tremor_dominant_hz",
          "mean_dev_pct", "accuracy_score", "accuracy_status", "tremor_score",
          "tremor_pct", "tremor_px", "tremor_status", "smoothness_status",
          "verdict_from")
DROP = ("shake_rms_px", "shake_pct")    # engine 3's reading, replaced by tremor
LEGACY_RADIUS_PX = 0.40 * 480      # the layout before raw.spiral.radius existed


def rescore_record(record: dict) -> dict | None:
    """The changed metric fields for one record, or None to leave it alone."""
    m = record.get("metrics") or {}
    if record.get("test") != "spiral" or not m.get("scoreable"):
        return None
    if (m.get("engine_version") or 1) >= M.ENGINE_VERSION:
        return None
    if m.get("sparc") is None:        # pre-SPARC (app 0.2) records: not ours
        return None
    samples = (record.get("raw") or {}).get("samples") or []
    if len(samples) < M.MIN_FRAMES:
        return None
    ts = [s[0] for s in samples]
    xs = [s[1] for s in samples]
    ys = [s[2] for s in samples]
    dev = [s[3] for s in samples] if len(samples[0]) > 3 else []
    # completion was already gated when the run was scored; the template is
    # not needed to recompute the fields that changed
    radius = ((record.get("raw") or {}).get("spiral") or {}).get("radius")         or LEGACY_RADIUS_PX
    new = M.compute_metrics(ts, xs, ys, dev, [[0.0, 0.0]], min_completion=0.0,
                            radius_px=radius)
    if not new["scoreable"]:
        return None
    return {k: _round(new[k]) for k in FIELDS}


def rescore(results_dir: Path, apply: bool) -> list[tuple]:
    changes = []                                  # (name, sid, old, new)
    for path in sorted(results_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        new = rescore_record(record)
        if new is None:
            continue
        m = record["metrics"]
        old = {k: m.get(k) for k in FIELDS}
        changes.append((path.name, record.get("session_id"), old, new))
        if apply:
            if (m.get("engine_version") or 1) == 1:
                m["v1"] = old         # the original scoring, kept once
            m.update(new)
            for k in DROP:
                m.pop(k, None)
            m["engine_version"] = M.ENGINE_VERSION
            path.write_text(json.dumps(record, indent=1), "utf-8")

    index = results_dir / "index.csv"
    if apply and changes and index.exists():
        by_sid = {sid: new for _, sid, _, new in changes if sid}
        with open(index, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or _INDEX_FIELDS
            rows = list(reader)
        for row in rows:
            new = by_sid.get(row.get("session_id"))
            if new:
                row.update({k: v for k, v in new.items() if k in fields})
        with open(index, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return changes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--results", default=str(_REPO_ROOT / "results"))
    args = ap.parse_args()
    changes = rescore(Path(args.results), args.apply)
    for name, _, old, new in changes:
        acc, tr = new["accuracy_score"], new["tremor_score"]
        print(f"{name[:15]}  accuracy {acc if acc is None else f'{acc:5.1f}'}"
              f"   tremor {tr if tr is None else f'{tr:5.1f}'}   "
              f"{old['status']} -> {new['status']} ({new['verdict_from']})")
    verb = "Rescored" if args.apply else "Would rescore"
    print(f"{verb} {len(changes)} spiral sessions.")
    if not args.apply:
        print("Dry run - nothing written. Add --apply to write.")


if __name__ == "__main__":
    main()
