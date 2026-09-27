#!/usr/bin/env python3
"""
Build the downloadable setup bundle the published site hands out.

    python tools/build_release.py    ->  web-build/download/

The bundle is `git archive` of the current commit: that is exactly the set of
files the project publishes, because .gitignore already keeps results/, docs/,
archive/ and CLAUDE.md out of it. It carries the code, the hand
model and the assets (~8 MB); install.py fetches the pip dependencies and
face_landmarker.task on the user's machine, which is why this stays small
enough to serve off Firebase Hosting.

Alongside it goes latest.json, so the download card can state a real size and
date instead of a number that rots in the markup.

Caveat worth knowing: git archive packages the last *commit*, not the working
tree. Uncommitted work is not in the download, so this warns loudly when the
tree is dirty.

Stdlib only, matching launcher.py, install.py and build_web.py.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "web-build" / "download"
ZIP_NAME = "HandScreening-Setup.zip"
# Unpacks into a folder rather than spraying 60 files into Downloads/.
PREFIX = "Hand-Detection-3D/"


def fail(msg: str) -> None:
    print(f"build_release: {msg}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=REPO, check=True,
                             capture_output=True, text=True)
    except FileNotFoundError:
        fail("git is not on PATH — it builds the bundle.")
    except subprocess.CalledProcessError as exc:
        fail(f"git {' '.join(args)} failed: {exc.stderr.strip()}")
    return out.stdout.strip()


def main() -> None:
    commit = git("rev-parse", "--short", "HEAD")
    dirty = git("status", "--porcelain")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUT_DIR / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()

    git("archive", "--format=zip", f"--prefix={PREFIX}",
        "-o", str(zip_path), "HEAD")

    data = zip_path.read_bytes()
    meta = {
        "version": commit,
        "file": ZIP_NAME,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    (OUT_DIR / "latest.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"build_release: {ZIP_NAME} {len(data) / 1_048_576:.1f} MB "
          f"from commit {commit} -> {OUT_DIR}")
    if dirty:
        n = len(dirty.splitlines())
        print(f"build_release: WARNING: {n} uncommitted change(s). The bundle "
              "ships HEAD, so that work is NOT in this download. Commit first.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
