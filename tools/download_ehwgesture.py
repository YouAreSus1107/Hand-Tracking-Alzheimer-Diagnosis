#!/usr/bin/env python3
"""
Download the finger-tapping slice of EHWGesture (github.com/smilies-polito/EHWGesture).

    python tools/download_ehwgesture.py --dest C:/Datasets/EHWGesture --dry-run
    python tools/download_ehwgesture.py --dest C:/Datasets/EHWGesture

The full dataset is 186 GB; tools/eval_tapping_videos.py needs about 7 GB of
it. Per subject (X01-X25) and hand (Left/Right) this fetches:

    DataKinects/<X>/<side>/rgb/Prova_FT??/master_FT??.mp4   the 30 fps RGB video
    DataKinects/<X>/<side>/<X>_<L|R>_lags.csv               the authors' clock offsets
    DataKinects/<X>/<side>/metadata/AlignedTimestamps/FT*   frame sync tables
    DataMOCAP/<X>/<side>/FT??.csv                           the 120 fps markers

plus the small Annotations/ and Metadata/ folders whole. Paths on disk mirror
the share, which is the layout the evaluation script reads.

The share is a public Nextcloud link, which exposes WebDAV with the share
token as the user name and no password -- the same access the browser page
gives, just scriptable. Files already on disk at the right size are skipped
and partial downloads land in *.part until complete, so an interrupted run is
resumed by running it again. Keep --dest out of OneDrive: 7 GB of video has
no business syncing.

Dataset license: CC BY 4.0, research and educational use only.
Stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HOST = "https://drive.cloud.polito.it"
TOKEN = "5cFBs6HFtrK7PXf"
DAV = f"{HOST}/public.php/webdav/"
AUTH = "Basic " + base64.b64encode(f"{TOKEN}:".encode()).decode()
NS = {"d": "DAV:"}
FT_RE = re.compile(r"FT[SNF][12]")
CHUNK = 1 << 20


def _request(url: str, method: str = "GET", headers: dict | None = None):
    req = urllib.request.Request(url, method=method,
                                 headers={"Authorization": AUTH, **(headers or {})})
    return urllib.request.urlopen(req, timeout=60)


def listing(path: str, depth: str = "1") -> list[tuple[str, int | None]]:
    """(relative path, size) for everything under `path`; folders end in '/'
    and carry no size."""
    url = DAV + urllib.parse.quote(path)
    with _request(url, "PROPFIND", {"Depth": depth}) as r:
        root = ET.fromstring(r.read())
    out = []
    for resp in root.findall("d:response", NS):
        href = urllib.parse.unquote(resp.findtext("d:href", "", NS))
        rel = href.split("/public.php/webdav/", 1)[-1]
        if rel.rstrip("/") == path.rstrip("/"):
            continue
        size = resp.findtext(".//d:getcontentlength", None, NS)
        out.append((rel, int(size) if size else None))
    return out


def plan(subjects: set[str] | None, camera: str) -> list[tuple[str, int]]:
    """Every file to fetch, as (share path, size)."""
    files: list[tuple[str, int]] = []

    def add(entries, keep=lambda p: True):
        files.extend((p, s) for p, s in entries if s is not None and keep(p))

    subs = [p.rstrip("/").split("/")[-1] for p, s in listing("DataKinects/")
            if s is None]
    subs = [s for s in sorted(subs) if not subjects or s.upper() in subjects]
    prefixes = ("master_", "sub2_") if camera == "both" else \
        ("master_",) if camera == "master" else ("sub2_",)
    for n, subj in enumerate(subs, 1):
        print(f"  listing {subj} ({n}/{len(subs)})", flush=True)
        for side in ("Left", "Right"):
            base = f"DataKinects/{subj}/{side}/"
            try:
                top = listing(base)
            except urllib.error.HTTPError as e:
                print(f"    {base}: {e.code}, skipped")
                continue
            add(top, lambda p: p.endswith("_lags.csv"))
            add(listing(base + "rgb/", "infinity"),
                lambda p: p.endswith(".mp4") and FT_RE.search(p)
                and p.rsplit("/", 1)[-1].startswith(prefixes))
            add(listing(base + "metadata/", "infinity"),
                lambda p: FT_RE.search(p.rsplit("/", 1)[-1]))
            add(listing(f"DataMOCAP/{subj}/{side}/"),
                lambda p: FT_RE.search(p.rsplit("/", 1)[-1]))
    for folder in ("Annotations/", "Metadata/"):
        add(listing(folder, "infinity"))
    return files


def fetch(path: str, size: int, dest: Path, retries: int = 4) -> str:
    target = dest / path
    if target.exists() and target.stat().st_size == size:
        return "have"
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if 0 < have < size else {}
        try:
            with _request(DAV + urllib.parse.quote(path), headers=headers) as r:
                # A server that ignores Range answers 200 with the whole file.
                mode = "ab" if headers and r.status == 206 else "wb"
                with open(part, mode) as f:
                    while chunk := r.read(CHUNK):
                        f.write(chunk)
            if part.stat().st_size == size:
                part.replace(target)
                return "got"
            if part.stat().st_size > size:
                part.unlink()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"    retry {attempt}/{retries} after {e}", flush=True)
            time.sleep(2 * attempt)
    raise RuntimeError(f"{path}: incomplete after {retries} attempts")


def _gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB" if n >= 1e8 else f"{n / 1e6:.1f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dest", required=True, type=Path,
                    help="where to mirror the share, e.g. C:/Datasets/EHWGesture")
    ap.add_argument("--subjects", help="comma list, e.g. X01,X02 (default all)")
    ap.add_argument("--camera", default="master", choices=("master", "sub", "both"),
                    help="which Kinect's video (default master, the one scored)")
    ap.add_argument("--workers", type=int, default=4,
                    help="parallel downloads (default 4)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be fetched and its size, then stop")
    args = ap.parse_args()
    dest = args.dest.resolve()
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = os.environ.get(var)
        if od and dest.is_relative_to(Path(od).resolve()):
            print(f"warning: --dest is inside OneDrive ({od}); "
                  f"several GB of video will sync.")
            break
    subjects = {s.strip().upper() for s in args.subjects.split(",")} \
        if args.subjects else None

    print("Reading the share's file list...")
    files = plan(subjects, args.camera)
    total = sum(s for _, s in files)
    videos = sum(p.endswith(".mp4") for p, _ in files)
    todo = [(p, s) for p, s in files
            if not ((args.dest / p).exists() and (args.dest / p).stat().st_size == s)]
    print(f"{len(files)} files ({videos} videos), {_gb(total)}; "
          f"{len(todo)} still to fetch ({_gb(sum(s for _, s in todo))})")
    if args.dry_run:
        for p, s in files[:25]:
            print(f"  {_gb(s):>10}  {p}")
        if len(files) > 25:
            print(f"  ... and {len(files) - 25} more")
        return 0

    # The server caps each connection at roughly 0.7 MB/s, so throughput
    # comes from running several at once.
    todo_bytes = sum(s for _, s in todo)
    done_bytes, done_n, t0, failed = 0, 0, time.time(), []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch, p, s, args.dest): (p, s) for p, s in todo}
        for fut in as_completed(futures):
            path, size = futures[fut]
            try:
                fut.result()
            except Exception as e:
                failed.append(path)
                print(f"  FAILED {path}: {e}", flush=True)
                continue
            done_bytes += size
            done_n += 1
            rate = done_bytes / max(1e-6, time.time() - t0)
            left = (todo_bytes - done_bytes) / max(1.0, rate)
            print(f"[{done_n}/{len(todo)}] {path}  ({rate / 1e6:.1f} MB/s, "
                  f"~{left / 60:.0f} min left)", flush=True)
    if failed:
        print(f"\n{len(failed)} files failed -- run the same command again to retry.")
        return 1
    print(f"\nDone. Next:\n  .venv/Scripts/python tools/eval_tapping_videos.py "
          f"--root {args.dest.as_posix()} --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
