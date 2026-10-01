"""
The end of a tremor run: merge the offline pass into the live fallback,
score, and save.

One function for both places a run can end. Normally the test hands its
unfinished holds to a worker process and exits (core/pending.py,
`tremor_test.py --finish`), and the worker calls finish_run(); when that
hand-off cannot happen, the test finishes in-process and calls the same
function. So a session saved either way is built by the same code.

`job` is everything the run knew when its last hold ended -- plain data
only, since it is pickled across to the worker:

    phase_order, hands        the holds and hands, in order
    windows                   {phase: (t0, t1)} scored window, capture clock
    data                      {phase: {hand: {t, pts, len}}} live landmarks
    cells_live                {phase: {hand: cell}} the live landmark cells
    clip_frames, all_frames   live edge-frame counts (the last-resort figure)
    glove_cells, glove_on, glove_hand, glove_dev
    capture_fps, camera_fps, frame_size, capture_info, app_version,
    duration_s, profile, timestamp

`results`/`errors` are the offline pass's, {phase: result} / {phase: why}.
"""

from __future__ import annotations

from core.tremor import metrics as tm


def merge_offline(job: dict, results: dict, errors: dict) -> dict:
    """Score each hold from the offline pass where it succeeded, else from
    the live landmarks. Returns the merged state: cells, data, flow_data,
    capture_stats and the edge-frame counts to use."""
    cells, stats = {}, {}
    data = {p: dict(per) for p, per in job["data"].items()}
    flow = {p: {h: {"t": [], "xy": []} for h in job["hands"]}
            for p in job["phase_order"]}
    clip, total, live_only = 0, 0, False
    for p in job["phase_order"]:
        if p not in job["windows"]:
            continue
        res = results.get(p)
        if res is not None:
            cells[p] = res["cells"]
            data[p] = res["lm"]
            flow[p] = res["flow"]
            stats[p] = res["stats"]
            clip += res["clip_frames"]
            total += res["all_frames"]
        else:
            live_only = True
            cells[p] = job["cells_live"].get(p, {})
            why = errors.get(p)
            if why:
                print(f"[WARN] {p}: offline pass failed ({why}) - "
                      "scored from the live landmarks.")
    if live_only and not total:        # nothing measured offline at all
        clip, total = job["clip_frames"], job["all_frames"]
    return {"cells": cells, "data": data, "flow_data": flow,
            "capture_stats": stats, "clip_frames": clip, "all_frames": total}


def score(job: dict, merged: dict) -> dict:
    """The run's metrics from the merged cells."""
    clip_frames, all_frames = merged["clip_frames"], merged["all_frames"]
    clipped = 100.0 * clip_frames / all_frames if all_frames else 0.0
    r = tm.compute_metrics(
        merged["cells"], phase_order=job["phase_order"], hands=job["hands"],
        glove=job["glove_cells"] if job["glove_on"] else None,
        clipped_pct=clipped, glove_hand=job["glove_hand"])
    r["edge_clipped_pct"] = round(clipped, 1)
    methods = {c.get("method") for c in tm.cells_iter(merged["cells"])
               if c.get("scored")}
    r["method"] = (methods.pop() if len(methods) == 1
                   else "mixed" if methods else None)
    r["capture_fps"] = round(job["capture_fps"], 1)
    r["engine_version"] = tm.ENGINE_VERSION
    stats = merged["capture_stats"].values()
    frames = sum((s.get("frames") or 0) for s in stats)
    dropped = sum((s.get("dropped") or 0) for s in stats)
    r["dropped_frames"] = dropped
    if frames and dropped / frames > 0.02:
        r.setdefault("confidence_reasons", []).append(
            "The camera lost frames during the holds.")
    return r


def _lighten(cells: dict) -> dict:
    """One line a cell: the spectra are for the report panel, which reads
    `raw`; the metrics block is sent with every session list."""
    return {p: {hnd: ({k: c.get(k) for k in ("peak_hz", "amp_pct",
                                            "prominence", "verdict",
                                            "method")}
                      if c and c.get("scored") else
                      {"why": (c or {}).get("why")})
                for hnd, c in per.items()}
            for p, per in cells.items()}


def build_record(job: dict, merged: dict, r: dict, errors: dict) -> dict:
    """save_session()'s keyword arguments for the run."""
    cells = merged["cells"]
    metrics = {k: v for k, v in r.items() if k not in ("cells", "glove")}
    metrics["cells"] = _lighten(cells)
    raw = {"phases": {}, "glove": job["glove_cells"] or None,
           "live_cells": _lighten(job["cells_live"]),
           "offline_errors": dict(errors) or None}
    for p, per in merged["data"].items():
        t0 = job["windows"].get(p, (0.0, 0.0))[0]
        traces = {}
        for hnd, d in per.items():
            if not d["t"]:
                continue
            # middle knuckle (tm.LANDMARKS[2]; the index fingertip before
            # engine 3), relative to its own median, in % of the hand
            # length: the movement the landmark spectrum was computed from
            scale = sorted(d["len"])[len(d["len"]) // 2]
            xs = [pt[2][0] for pt in d["pts"]]
            ys = [pt[2][1] for pt in d["pts"]]
            mx, my = sorted(xs)[len(xs) // 2], sorted(ys)[len(ys) // 2]
            traces[hnd] = [[round(t - t0, 3),
                            round((x - mx) / scale * 100, 2),
                            round((y - my) / scale * 100, 2)]
                           for t, x, y in zip(d["t"], xs, ys)]
        # the flow position, in % of hand length from its median, so a
        # recorded still hand can serve tools/eval_tremor_accel.py as a
        # noise carrier the way the fingertip traces do
        flow_traces = {}
        for hnd, f in (merged["flow_data"].get(p) or {}).items():
            lens = (per.get(hnd) or {}).get("len") or []
            if len(f["t"]) < 8 or not lens:
                continue
            scale = sorted(lens)[len(lens) // 2]
            xs = [xy[0] for xy in f["xy"]]
            ys = [xy[1] for xy in f["xy"]]
            mx, my = sorted(xs)[len(xs) // 2], sorted(ys)[len(ys) // 2]
            flow_traces[hnd] = [[round(t - t0, 4),
                                 round((x - mx) / scale * 100, 3),
                                 round((y - my) / scale * 100, 3)]
                                for t, x, y in zip(f["t"], xs, ys)]
        raw["phases"][p] = {
            "traces": traces,
            "flow_traces": flow_traces,
            "capture": merged["capture_stats"].get(p),
            "spectra": {hnd: c.get("spectrum")
                        for hnd, c in (cells.get(p) or {}).items()
                        if c and c.get("scored")},
        }
    fw, fh = job["frame_size"]
    return dict(
        test="tremor", mode="rest_postural", hand="both",
        duration_s=job["duration_s"],
        device={"camera_fps": round(job["camera_fps"], 1),
                "capture_fps": round(job["capture_fps"], 1),
                "resolution": f"{fw}x{fh}", "app_version": job["app_version"],
                "glove": job["glove_dev"], **(job["capture_info"] or {})},
        metrics=metrics, raw=raw, profile=job["profile"],
        timestamp=job["timestamp"])


def finish_run(job: dict, results: dict, errors: dict, *, save) -> dict:
    """Merge, score and save. `save` is core.session.save_session (passed in,
    so a test harness that replaces it is obeyed). Returns {"results",
    "cells", "saved_path"}; saved_path is None when the save failed, which
    is reported rather than raised -- the run's numbers are still good."""
    merged = merge_offline(job, results, errors)
    r = score(job, merged)
    try:
        path = save(**build_record(job, merged, r, errors))
    except OSError as e:
        path = None
        print(f"[WARN] Could not save session: {e}")
    return {"results": r, "cells": merged["cells"], "saved_path": path}
