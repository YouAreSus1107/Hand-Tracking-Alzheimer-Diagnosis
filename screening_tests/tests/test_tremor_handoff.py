"""
Unit tests for finishing the tremor test in the background: core/pending.py
(the job registry the hub reads), OfflineAnalyser.hand_over() (taking the
unfinished holds back with their frames intact), core/tremor/finish.py (the
merge-score-save both endings share) and tremor_test.run_job() (the worker).
No camera, no MediaPipe: synthetic video and a scripted detector, as in
test_tremor_offline.py. The run loop's side of the hand-off is covered by
test_run_loops.test_tremor_run_loop_hands_off.

Run:  python screening_tests/tests/test_tremor_handoff.py
"""

from __future__ import annotations

import importlib.util
import pickle
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import pending
from core.tremor import finish
from core.tremor import offline as off
from core.tremor.phases import HANDS, PHASE_ORDER

import test_tremor_offline as t_off       # synthetic takes + scripted detector


def _tmp():
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def _wait(cond, secs=60.0):
    end = time.monotonic() + secs
    while not cond() and time.monotonic() < end:
        time.sleep(0.02)
    return cond()


# ── core/pending.py ───────────────────────────────────────────────────────

def test_a_new_job_is_listed_as_queued():
    with _tmp() as d:
        job = pending.new_job("tremor", root=Path(d))
        listed = pending.summary(Path(d))
        assert [j["id"] for j in listed] == [job.name], listed
        assert listed[0]["tool"] == "tremor" and listed[0]["state"] == pending.QUEUED


def test_a_silent_worker_becomes_failed_and_its_frames_go():
    with _tmp() as d:
        job = pending.new_job("tremor", root=Path(d))
        (job / pending.JOB).write_bytes(b"frames")
        later = time.time() + pending.STALE_S + 1
        st = pending.jobs(Path(d), now=later)
        assert st[0]["state"] == pending.FAILED, st
        assert not (job / pending.JOB).exists()        # no patient frames left
        # and a failure is dropped once it has been listed long enough
        assert pending.jobs(Path(d), now=later + pending.KEEP_FAILED_S + 5) == []
        assert not job.exists()


def test_a_beating_worker_stays_running():
    with _tmp() as d:
        job = pending.new_job("tremor", root=Path(d))
        beat = pending.Heartbeat(job, lambda: 0.25, interval=0.05)
        beat.start()
        try:
            assert _wait(lambda: (pending.read_status(job) or {}).get("state")
                         == pending.RUNNING, 5)
            j = pending.summary(Path(d))[0]
            assert j["state"] == pending.RUNNING and j["progress"] == 0.25, j
        finally:
            beat.stop()


def test_a_done_job_is_listed_briefly_then_removed():
    with _tmp() as d:
        job = pending.new_job("tremor", root=Path(d))
        (job / pending.JOB).write_bytes(b"frames")
        pending.done(job, session="x.json")
        assert not (job / pending.JOB).exists()
        assert pending.summary(Path(d))[0]["state"] == pending.DONE
        assert pending.jobs(Path(d), now=time.time() + pending.KEEP_DONE_S + 5) == []


def test_debris_without_a_status_is_cleared_once_old():
    with _tmp() as d:
        junk = Path(d) / "tremor_old"
        junk.mkdir()
        assert pending.jobs(Path(d)) == [] and junk.exists()    # young: left alone
        assert pending.jobs(Path(d), now=time.time() + pending.STALE_S + 5) == []
        assert not junk.exists()


def test_summary_of_a_missing_root_is_empty():
    assert pending.summary(Path(tempfile.gettempdir()) / "no_such_hand3d_root") == []


# ── OfflineAnalyser.hand_over() ───────────────────────────────────────────

def test_hand_over_returns_queued_holds_with_their_frames():
    a, truth_a = t_off._take_from_video(dur=1.0)
    b, _ = t_off._take_from_video(dur=1.0)
    an = off.OfflineAnalyser(lambda: (t_off._detect_for(truth_a), None))
    an.pause()                        # nothing measured: both still queued
    an.start()
    an.submit("rest_palm_up", a, t_off._window(a), 0.15)
    an.submit("postural", b, t_off._window(b), 0.6)
    left = an.hand_over(timeout=5)
    assert [j[0] for j in left] == ["rest_palm_up", "postural"], left
    assert all(len(j[1].jpeg) == len(j[1]) > 0 for j in left)   # frames intact
    assert an.idle() and an.results == {} and an.errors == {}
    assert _wait(lambda: not an.is_alive(), 5)                  # thread gone


def test_hand_over_stops_a_hold_mid_way_and_keeps_the_finished_ones():
    done_take, truth = t_off._take_from_video(dur=2.0)
    long_take, _ = t_off._take_from_video(dur=6.0)
    base = t_off._detect_for(truth)
    calls = [0]
    an = None

    def detect(rgb, ms):
        # stop the clock part-way through the second hold, deterministically
        calls[0] += 1
        if calls[0] == len(done_take) + 20:
            an.pause()
        return base(rgb, ms)
    an = off.OfflineAnalyser(lambda: (detect, None))
    an.start()
    an.submit("rest_palm_up", done_take, t_off._window(done_take), 0.15)
    assert _wait(lambda: "rest_palm_up" in an.results)
    an.submit("postural", long_take, t_off._window(long_take), 0.6)
    assert _wait(lambda: calls[0] >= len(done_take) + 20)       # mid-way, parked
    left = an.hand_over(timeout=10)
    assert [j[0] for j in left] == ["postural"], left
    assert len(left[0][1].jpeg) == len(long_take)               # not freed
    assert "rest_palm_up" in an.results and "postural" not in an.results
    assert "postural" not in an.errors                          # not a failure


def test_hand_over_of_an_idle_analyser_is_empty():
    an = off.OfflineAnalyser(lambda: (None, None))
    an.start()
    assert an.hand_over(timeout=5) == []


# ── core/tremor/finish.py ─────────────────────────────────────────────────

def _job(**over) -> dict:
    job = {
        "phase_order": list(PHASE_ORDER), "hands": list(HANDS),
        "windows": {}, "data": {p: {h: {"t": [], "pts": [], "len": []}
                                    for h in HANDS} for p in PHASE_ORDER},
        "cells_live": {}, "clip_frames": 0, "all_frames": 0,
        "glove_cells": {}, "glove_on": False, "glove_hand": None,
        "glove_dev": None, "capture_fps": 60.0, "camera_fps": 30.0,
        "frame_size": (640, 480), "capture_info": {"backend": "test"},
        "app_version": "test", "duration_s": 60.0,
        "profile": {"name": "Test"}, "timestamp": datetime(2026, 10, 1, 12, 0, 0),
    }
    job.update(over)
    return job


def test_finish_falls_back_to_the_live_cells_for_a_failed_hold():
    live = {"rest_palm_up": {h: {"scored": False, "why": "live"} for h in HANDS}}
    saved = {}
    out = finish.finish_run(
        _job(windows={"rest_palm_up": (0.0, 20.0)}, cells_live=live,
             clip_frames=3, all_frames=30),
        {}, {"rest_palm_up": "RuntimeError: gone"},
        save=lambda **k: saved.update(k) or Path("x.json"))
    assert out["cells"]["rest_palm_up"] == live["rest_palm_up"]
    assert out["results"]["edge_clipped_pct"] == 10.0     # the live counts
    assert saved["raw"]["offline_errors"] == {"rest_palm_up": "RuntimeError: gone"}
    # the snapshot and the run's own time, not the worker's
    assert saved["profile"] == {"name": "Test"}
    assert saved["timestamp"] == datetime(2026, 10, 1, 12, 0, 0)
    assert saved["device"]["backend"] == "test" and saved["test"] == "tremor"


def test_finish_reports_a_failed_save_instead_of_raising():
    def broken(**_k):
        raise OSError("disk full")
    out = finish.finish_run(_job(), {}, {}, save=broken)
    assert out["saved_path"] is None and out["results"] is not None


# ── the worker: tremor_test.run_job() ────────────────────────────────────

def _load_tremor_test():
    spec = importlib.util.spec_from_file_location(
        "_handoff_tremor_test", _REPO_ROOT / "screening_tests" / "tremor_test.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_job(root: Path, todo, results=None, errors=None, job=None) -> Path:
    d = pending.new_job("tremor", root=root)
    with open(d / pending.JOB, "wb") as f:
        pickle.dump({"job": job or _job(), "results": results or {},
                     "errors": errors or {}, "todo": todo, "keep_dir": None}, f)
    return d


def test_worker_measures_the_handed_holds_and_saves():
    tt = _load_tremor_test()
    take, truth = t_off._take_from_video(dur=8.0, hz=6.0, amp_px=0.6)
    win = t_off._window(take)
    saved = {}
    with _tmp() as d:
        job_dir = _write_job(Path(d), [("postural", take, win, 0.6)],
                             job=_job(windows={"postural": win}))
        out = tt.run_job(job_dir, make_detect=lambda: (t_off._detect_for(truth), None),
                         save=lambda **k: saved.update(k) or Path("s.json"))
        st = pending.read_status(job_dir)
        assert out is not None, st
        cell = out["cells"]["postural"]["right"]
        assert cell["scored"] and cell["method"] == "offline_flow", cell
        assert abs(cell["peak_hz"] - 6.0) <= 0.25, cell["peak_hz"]
        assert st["state"] == pending.DONE and st["session"] == "s.json", st
        assert not (job_dir / pending.JOB).exists()
        assert saved["metrics"]["method"] == "offline_flow"


def test_worker_keeps_holds_measured_before_the_hand_off():
    tt = _load_tremor_test()
    take, truth = t_off._take_from_video(dur=4.0)
    earlier = off.analyse_take(take, t_off._detect_for(truth), t_off._window(take), 0.15)
    calls = []
    with _tmp() as d:
        job_dir = _write_job(Path(d), [], results={"rest_palm_up": earlier},
                             job=_job(windows={"rest_palm_up": t_off._window(take)}))
        out = tt.run_job(job_dir, make_detect=lambda: calls.append(1),
                         save=lambda **k: Path("s.json"))
        assert out is not None and calls == []              # nothing re-measured
        assert out["cells"]["rest_palm_up"] == earlier["cells"]


def test_worker_marks_a_broken_job_failed():
    tt = _load_tremor_test()
    with _tmp() as d:
        job_dir = pending.new_job("tremor", root=Path(d))
        (job_dir / pending.JOB).write_bytes(b"not a pickle")
        assert tt.run_job(job_dir, save=lambda **k: None) is None
        st = pending.read_status(job_dir)
        assert st["state"] == pending.FAILED and st["error"], st
        assert not (job_dir / pending.JOB).exists()


def test_worker_marks_a_failed_save_failed():
    tt = _load_tremor_test()

    def broken(**_k):
        raise OSError("disk full")
    with _tmp() as d:
        job_dir = _write_job(Path(d), [])
        assert tt.run_job(job_dir, make_detect=lambda: None, save=broken) is not None
        assert pending.read_status(job_dir)["state"] == pending.FAILED


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
