"""
Analyses that finish after their test has closed.

The tremor test records three holds and then needs up to a minute to measure
every frame (core/tremor/offline.py). That minute used to keep the test's
window open, so the camera and the hub's one-test-at-a-time slot stayed taken
while nothing was being recorded. Now the test writes what is left into a job
folder, starts a worker process, and exits; the worker measures, saves the
session, deletes the frames and marks the job done.

Each job is one folder under ROOT holding `job.pkl` (the recorded frames and
the run's state, written by the test, deleted by the worker), `status.json`
(this module's, read by the hub) and `worker.log` (the worker's console).
A finished or failed job keeps only those last two, for KEEP_DONE_S /
KEEP_FAILED_S, then goes. The folder is in the system temp directory,
not the repo: the repo lives in OneDrive, and recorded frames must never be
synced anywhere.

The worker's heartbeat thread rewrites status.json every second. A running
job whose heartbeat stops (the worker was killed, the machine slept through
it) is marked failed and its frames deleted the next time anyone looks, so a
dead worker can neither hold the hub's "Analysing" badge forever nor leave a
patient's frames behind.

Stdlib-only: launcher.py imports it.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(tempfile.gettempdir()) / "hand3d_pending"
STATUS = "status.json"
JOB = "job.pkl"
LOG = "worker.log"

HEARTBEAT_S = 1.0
STALE_S = 45.0          # no heartbeat for this long: the worker is gone
KEEP_DONE_S = 60.0      # a finished job stays listed this long (the hub polls
                        # every 3 s), so its end is a state, not a disappearance
KEEP_FAILED_S = 600.0   # a failure stays listed this long, so the hub can say so

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


def new_job(tool: str, root: Path | None = None) -> Path:
    """A fresh, empty job folder for `tool` (the launcher's TOOLS key)."""
    base = Path(root or ROOT)
    base.mkdir(parents=True, exist_ok=True)
    try:
        jobs(base)      # tidy up after runs made while the hub was closed
    except OSError:
        pass
    stamp = time.strftime("%Y%m%d_%H%M%S")
    d = base / f"{tool}_{stamp}_{os.getpid()}"
    d.mkdir()
    write_status(d, tool=tool, state=QUEUED, progress=0.0,
                 started=time.time())
    return d


def read_status(job: Path, tries: int = 5) -> dict | None:
    """The job's status, or None when there is none. Retried briefly: on
    Windows a read that lands on the instant write_status() swaps the file in
    fails with a sharing error, and a job missing from one poll would read
    to the hub as finished."""
    path = Path(job) / STATUS
    for i in range(tries):
        try:
            return json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            if i + 1 < tries:
                time.sleep(0.02)
    return None


def write_status(job: Path, **fields) -> None:
    """Merge `fields` into the job's status and stamp the heartbeat. Written
    to a temp file and swapped in, so a reader never sees half a file."""
    job = Path(job)
    data = read_status(job) or {}
    data.update(fields)
    data["heartbeat"] = time.time()
    tmp = job / (STATUS + ".tmp")
    tmp.write_text(json.dumps(data), "utf-8")
    for i in range(5):
        try:
            os.replace(tmp, job / STATUS)
            return
        except PermissionError:          # a reader has it open (Windows)
            if i == 4:
                raise
            time.sleep(0.02)


def drop_frames(job: Path) -> None:
    """Delete everything but the status and the log."""
    for p in Path(job).iterdir():
        if p.name in (STATUS, LOG):
            continue
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        except OSError:
            pass


def remove(job: Path) -> None:
    shutil.rmtree(job, ignore_errors=True)


def fail(job: Path, error: str) -> None:
    """Mark a job failed and delete its frames; the status stays for the hub."""
    drop_frames(job)
    write_status(job, state=FAILED, error=str(error)[:300], finished=time.time())


def done(job: Path, **fields) -> None:
    """Mark a job finished and delete its frames; the status stays briefly,
    so the hub sees the job end rather than vanish."""
    drop_frames(job)
    write_status(job, state=DONE, progress=1.0, finished=time.time(), **fields)


def jobs(root: Path | None = None, now: float | None = None) -> list[dict]:
    """Every job the hub should know about, oldest first, after tidying:
    a job whose worker stopped beating becomes failed, an old failure is
    removed, and a folder with no readable status is removed."""
    base = Path(root or ROOT)
    now = time.time() if now is None else now
    out = []
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        st = read_status(d)
        if st is None:
            # being created right now, or debris: leave young ones alone
            try:
                young = now - d.stat().st_mtime < STALE_S
            except OSError:
                young = False
            if not young:
                remove(d)
            continue
        state = st.get("state")
        if state in (QUEUED, RUNNING) and now - st.get("heartbeat", 0) > STALE_S:
            fail(d, "The analysis stopped before it finished.")
            st = read_status(d) or st
            state = FAILED
        keep = KEEP_DONE_S if state == DONE else KEEP_FAILED_S
        if state in (DONE, FAILED) and now - st.get("finished", now) > keep:
            remove(d)
            continue
        out.append({"id": d.name, "tool": st.get("tool"), "state": state,
                    "progress": st.get("progress", 0.0),
                    "started": st.get("started"), "error": st.get("error")})
    return out


def summary(root: Path | None = None) -> list[dict]:
    """The jobs for /api/status: id, tool, state, progress, error. Never
    raises: the hub's poll must not break because the temp directory is
    unreadable."""
    try:
        return [{k: j[k] for k in ("id", "tool", "state", "progress", "error")}
                for j in jobs(root)]
    except OSError:
        return []


class Heartbeat(threading.Thread):
    """Rewrites the job's status every HEARTBEAT_S with `progress()`, until
    stop(). A separate thread, so a long model load still beats."""

    def __init__(self, job: Path, progress=lambda: 0.0,
                 interval: float = HEARTBEAT_S):
        super().__init__(daemon=True, name="pending-heartbeat")
        self.job, self.progress, self.interval = Path(job), progress, interval
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                write_status(self.job, state=RUNNING,
                             progress=round(float(self.progress()), 3))
            except (OSError, ValueError):
                pass
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
        if self.is_alive():
            self.join(timeout=2.0)
