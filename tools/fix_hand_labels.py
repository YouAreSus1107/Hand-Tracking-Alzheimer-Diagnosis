"""
Swap the reversed hand labels in already-saved tapping and spiral results.

Until 2026-09-27 the tapping and spiral tests read MediaPipe's handedness label
on their selfie-flipped frame and saved it as the hand tested. On a flipped
frame that label names the OTHER hand (core/hand_utils.true_hand has the
evidence), so every saved `hand` of those two tests is reversed.

This swaps left <-> right once per record, in the JSON and its index.csv row
together (the pattern of core/session.reassign), and stamps the JSON with
"hand_label_fixed": true so a second run changes nothing. core/session.py
stamps the same flag on every record saved since the fix, so those are never
touched. Remote sessions are skipped (the participant page records no hand).

Dry run by default:

    .venv/Scripts/python tools/fix_hand_labels.py
    .venv/Scripts/python tools/fix_hand_labels.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

TESTS = ("finger_tapping", "spiral")
SWAP = {"left": "right", "right": "left"}
FLAG = "hand_label_fixed"


def _candidates(results_dir: Path, before: str | None):
    for path in sorted(results_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("test") not in TESTS:
            continue
        if record.get(FLAG) or record.get("source") == "remote":
            continue
        if str(record.get("hand", "")).lower() not in SWAP:
            continue
        if before and str(record.get("timestamp", "")) >= before:
            continue
        yield path, record


def fix(results_dir: Path, apply: bool, before: str | None = None) -> dict:
    """Returns counts; writes only when `apply`."""
    swapped: dict[str, str] = {}              # session_id -> new hand
    counts = {"left->right": 0, "right->left": 0, "csv_rows": 0,
              "csv_without_json": 0}
    for path, record in _candidates(results_dir, before):
        old = record["hand"].lower()
        new = SWAP[old]
        counts[f"{old}->{new}"] += 1
        sid = record.get("session_id")
        if sid:
            swapped[sid] = new
        if apply:
            record["hand"] = new
            record[FLAG] = True
            path.write_text(json.dumps(record, indent=1), "utf-8")

    index = results_dir / "index.csv"
    if index.exists():
        with open(index, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or []
            rows = list(reader)
        known = {json_sid for json_sid in _all_session_ids(results_dir)}
        for row in rows:
            sid = row.get("session_id")
            if sid in swapped:
                row["hand"] = swapped[sid]
                counts["csv_rows"] += 1
            elif (row.get("test") in TESTS and row.get("hand") in SWAP
                  and sid not in known):
                counts["csv_without_json"] += 1   # left alone: nothing to mark
        if apply and swapped:
            with open(index, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
    return counts


def _all_session_ids(results_dir: Path):
    for path in results_dir.glob("*.json"):
        try:
            sid = json.loads(path.read_text("utf-8")).get("session_id")
        except (OSError, ValueError, AttributeError):
            continue
        if sid:
            yield sid


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--before", help="only records with timestamp < this "
                    "(ISO, e.g. 2026-09-27T12:00)")
    ap.add_argument("--results", default=str(_REPO_ROOT / "results"))
    args = ap.parse_args()
    counts = fix(Path(args.results), args.apply, args.before)
    verb = "Swapped" if args.apply else "Would swap"
    print(f"{verb}: {counts['left->right']} left->right, "
          f"{counts['right->left']} right->left "
          f"({counts['csv_rows']} index.csv rows).")
    if counts["csv_without_json"]:
        print(f"{counts['csv_without_json']} index.csv rows have no JSON and "
              "were left as they are.")
    if not args.apply:
        print("Dry run - nothing written. Add --apply to write.")


if __name__ == "__main__":
    main()
