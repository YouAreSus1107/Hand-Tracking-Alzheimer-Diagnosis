#!/usr/bin/env python3
"""
Offline accuracy check of the finger-tapping detector against motion capture.

    .venv/Scripts/python tools/eval_tapping_videos.py --root D:/EHWGesture --dry-run
    .venv/Scripts/python tools/eval_tapping_videos.py --root D:/EHWGesture --subjects X01,X02

Runs every EHWGesture finger-tapping video through the same pipeline the live
test uses -- CLAHE preprocessing, MediaPipe Hand Landmarker in
VIDEO mode, One-Euro smoothing, `thumb_index_distance`, `Calibrator`,
`TapDetector`, `compute_metrics` -- and scores the taps it finds against the
taps in the synchronised 120 fps marker data (see tools/tapping_eval.py).

Expected layout under --root (only these folders are needed):

    DataMOCAP/X01/Left/FTS1.csv ...
    DataKinects/X01/Left/rgb/Prova_FTS1/master_FTS1.mp4 ...

Two things differ from a live run, on purpose:

  * Frame times come from the file (frame index / fps), never the wall
    clock. The live loop stamps frames with time.time(); here that would time
    the video by how fast this machine decodes it.
  * There is no warm-up screen, so calibration is fed from the recording
    itself until `Calibrator` is satisfied, then the detector runs over the
    whole recording from the first frame. That is mildly optimistic -- the
    seed comes from the taps being scored -- but the detector's rolling
    envelope replaces the seed within ~3 s either way.

MediaPipe output is cached per video under results/tapping_eval/cache/, so
re-scoring after a detector change takes seconds rather than re-running the
landmarker. Pass --no-cache to force extraction.

Writes results/tapping_eval/<timestamp>.csv (one row per recording) and prints
an agreement summary.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))

from core.tapping.detector import Calibrator, TapDetector, thumb_index_distance
from core.tapping.metrics import compute_metrics
from core.tapping.modes import MODES, TapMode
from tools import tapping_eval as te

OUT_DIR = _REPO_ROOT / "results" / "tapping_eval"
CACHE_DIR = OUT_DIR / "cache"
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")
# Must match screening_tests/finger_tapping.py.
EMA_ALPHA_PACED = 0.4
EMA_ALPHA_FAST = 0.6
CACHE_VERSION = 2          # 2: frames no longer flipped before detection


# ── discovery ──────────────────────────────────────────────────────────────

def discover(root: Path, camera: str, subjects: set[str] | None,
             speeds: set[str] | None) -> list[dict]:
    """Pair each finger-tapping video with its marker file."""
    items = []
    kin = root / "DataKinects"
    for video in sorted(kin.glob(f"*/*/rgb/**/{camera}_FT*.mp4")):
        rel = video.relative_to(kin).parts
        subject, side = rel[0], rel[1]
        task = te.parse_task(video.name)
        if task is None:
            continue
        speed, take = task
        if subjects and subject.upper() not in subjects:
            continue
        if speeds and speed not in speeds:
            continue
        mocap = root / "DataMOCAP" / subject / side / f"FT{speed}{take}.csv"
        lags = kin / subject / side / f"{subject}_{side[0].upper()}_lags.csv"
        items.append({"subject": subject, "side": side, "speed": speed,
                      "take": take, "bpm": te.SPEED_BPM[speed],
                      "video": video, "mocap": mocap if mocap.exists() else None,
                      "lags": lags if lags.exists() else None})
    return items


# ── MediaPipe extraction (the only part that needs cv2 / mediapipe) ────────

def _cache_path(video: Path, root: Path) -> Path:
    rel = video.relative_to(root).with_suffix(".json")
    return CACHE_DIR / "__".join(rel.parts)


def _bbox_area(landmarks) -> float:
    xs = [p.x for p in landmarks]
    ys = [p.y for p in landmarks]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def extract(video: Path, side: str | None, pick: str = "label",
            max_side: int | None = None) -> dict:
    """Per-frame thumb-index distance, exactly as the live test derives it.

    `pick` chooses between two detected hands: "label" takes the one whose
    handedness matches `side` (EHWGesture: un-mirrored Kinect, resting hand
    often in shot); "largest" takes the biggest in frame (phone clinic video,
    one hand, possibly mirrored, so its label cannot be trusted).
    `max_side` downscales each frame so its longer side is at most that many
    pixels before preprocessing -- nearer the live test's 640x480 than a
    1080x1920 phone frame, and much cheaper."""
    import cv2
    from core import quiet
    import mediapipe as mp
    from core.hand_utils import (make_landmark_filters, smooth_landmarks,
                                 preprocess_for_mediapipe)

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not 1.0 <= fps <= 240.0:
        fps = 30.0
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        # Two, not the live test's one: the resting hand is often in shot too,
        # and the tapping hand is picked by label below.
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.55,
    )
    with quiet.muted_native_stderr():
        landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
    fx, fy = make_landmark_filters()
    want = (side or "").lower()
    t_list, d_list = [], []
    label_hits = frames = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = frames / fps
            frames += 1
            # No selfie flip, unlike the live test. The Kinect frames are an
            # un-mirrored view, and with the flip MediaPipe labelled the
            # participant's left hand "Right" on ~98% of X01's frames, so the
            # label could not pick the tapping hand. The distance measure is
            # mirror-invariant, so dropping the flip changes nothing else.
            if max_side and max(frame.shape[:2]) > max_side:
                s = max_side / max(frame.shape[:2])
                frame = cv2.resize(frame, None, fx=s, fy=s,
                                   interpolation=cv2.INTER_AREA)
            rgb = preprocess_for_mediapipe(frame, enable=True)
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res = landmarker.detect_for_video(img, int(round(t * 1000)))
            d = None
            if res.hand_landmarks:
                hand = 0
                if pick == "largest":
                    hand = max(range(len(res.hand_landmarks)),
                               key=lambda k: _bbox_area(res.hand_landmarks[k]))
                else:
                    for k, h in enumerate(res.handedness or []):
                        if h and h[0].category_name.lower() == want:
                            hand = k
                            label_hits += 1
                            break
                lms = smooth_landmarks(res.hand_landmarks[hand], fx, fy, t)
                d = thumb_index_distance(lms)
            t_list.append(t)
            d_list.append(d)
    finally:
        landmarker.close()
        cap.release()
    return {"version": CACHE_VERSION, "size": video.stat().st_size,
            "fps": fps, "frames": frames, "t": t_list, "d": d_list,
            "label_hits": label_hits, "pick": pick, "max_side": max_side}


def cache_matches(data: dict, size: int, pick: str,
                  max_side: int | None) -> bool:
    """Whether a cached trace was made from this file with these settings. A
    cache written before `pick`/`max_side` existed was made with the old
    defaults, so it still serves those -- the EHWGesture caches stay valid."""
    return (data.get("version") == CACHE_VERSION and data.get("size") == size
            and data.get("pick", "label") == pick
            and data.get("max_side") == max_side)


def load_trace(video: Path, root: Path, side: str | None, use_cache: bool,
               pick: str = "label", max_side: int | None = None) -> dict:
    cp = _cache_path(video, root)
    if use_cache and cp.exists():
        try:
            data = json.loads(cp.read_text())
            if cache_matches(data, video.stat().st_size, pick, max_side):
                return data
        except (OSError, ValueError):
            pass
    data = extract(video, side, pick, max_side)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(data))
    return data


# ── scoring ────────────────────────────────────────────────────────────────

def mode_for(key: str, bpm: float) -> TapMode:
    if key == "paced":
        # The app's paced mode is a 1 Hz metronome; these recordings run at
        # 1.25-2.33 Hz, and its 0.5 s debounce would drop every other tap at
        # 140 bpm. Keep its scoring, move its pace to the recording's.
        return dataclasses.replace(MODES["paced"], interval_s=60.0 / bpm,
                                   expected_rate_hz=bpm / 60.0, max_rate_hz=5.0)
    return MODES[key]


def detect(trace: dict, mode: TapMode) -> tuple[list[float], list, bool, int]:
    """Our tap times on the video clock, the smoothed series, whether
    calibration completed, and the near-miss count (the live test hands that
    to compute_metrics, and its quality gate reads it)."""
    samples = [(t, d) for t, d in zip(trace["t"], trace["d"]) if d is not None]
    cal = Calibrator()
    for t, d in samples:
        cal.update(t, d)
        if cal.done:
            break
    calibrated = cal.done
    lo, hi = cal.result()
    if hi <= lo:
        return [], [], False, 0
    ema = EMA_ALPHA_PACED if mode.paced else EMA_ALPHA_FAST
    det = TapDetector(mode.min_intertap_s, ema, lo, hi)
    for t, d in zip(trace["t"], trace["d"]):
        det.update(t, d)
    return det.tap_times, det.series, calibrated, det.near_miss


def score_one(item: dict, trace: dict, mode: TapMode, tol_s: float,
              offset_source: str = "estimate") -> dict:
    row = {"subject": item["subject"], "side": item["side"],
           "speed": item["speed"], "take": item["take"], "bpm": item["bpm"],
           "video": item["video"].name, "fps": round(trace["fps"], 2),
           "frames": trace["frames"]}
    n = max(1, trace["frames"])
    seen = sum(d is not None for d in trace["d"])
    row["hand_visible"] = round(seen / n, 3)
    row["label_match"] = round(trace["label_hits"] / max(1, seen), 3)

    ours, series, calibrated, near_miss = detect(trace, mode)
    row["calibrated"] = calibrated
    if item["mocap"] is None:
        row["error"] = "no marker file"
        return row

    ref_t, thumb, index = te.read_mocap(item["mocap"])
    ref_d = te.fill_gaps(te.marker_distance(thumb, index))
    ref_taps = te.mocap_taps(ref_t, ref_d, item["bpm"])
    video = [(t, d) for t, d in zip(trace["t"], trace["d"]) if d is not None]
    off, r = te.estimate_offset(video, ref_t, ref_d)
    row["offset_est_s"] = None if off is None else round(off, 4)
    row["offset_r"] = None if r is None else round(r, 3)
    lag = te.read_lag(item["lags"], f"FT{item['speed']}{item['take']}") \
        if item.get("lags") else None
    off_ds = ref_t[lag] if lag is not None and 0 <= lag < len(ref_t) else None
    row["offset_dataset_s"] = None if off_ds is None else round(off_ds, 4)
    if off is not None and off_ds is not None:
        row["offset_diff_ms"] = round((off - off_ds) * 1000, 1)
    if offset_source == "dataset":
        off = off_ds
    row["offset_used"] = offset_source
    if off is None:
        row["error"] = "could not align clocks"
        return row

    # Score only where both recordings exist.
    w0 = max(trace["t"][0], ref_t[0] - off)
    w1 = min(trace["t"][-1], ref_t[-1] - off)
    ref_v = [x - off for x in ref_taps if w0 <= x - off <= w1]
    ours_w = [x for x in ours if w0 <= x <= w1]
    row["window_s"] = round(w1 - w0, 2)
    row.update(te.timing_agreement(ours_w, ref_v, tol_s))

    fps = trace["fps"]
    m_ours = compute_metrics(mode, ours_w, series, w0, w1,
                             hand_visible_ratio=row["hand_visible"],
                             camera_fps=fps, near_miss=near_miss)
    m_ref = compute_metrics(mode, ref_v, [], w0, w1, camera_fps=te.MOCAP_FPS)
    for tag, m in (("ours", m_ours), ("ref", m_ref)):
        row[f"scoreable_{tag}"] = m["scoreable"]
        row[f"freq_hz_{tag}"] = m["frequency_hz"]
        row[f"cv_pct_{tag}"] = m["cv_pct"]
        row[f"status_{tag}"] = m["status"]
    row["reason_ours"] = m_ours["reason"]
    return row


# ── report ─────────────────────────────────────────────────────────────────

def _fmt(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def summarise(rows: list[dict]) -> None:
    ok = [r for r in rows if "recall" in r and r["recall"] is not None]
    print(f"\n{len(rows)} recordings, {len(ok)} scored against motion capture")
    if not ok:
        return
    groups = [("all", ok)] + [(s, [r for r in ok if r["speed"] == s])
                              for s in ("S", "N", "F")]
    print(f"\n{'group':<8}{'n':>4}{'recall':>8}{'precis':>8}"
          f"{'lead ms':>9}{'jitter':>8}")
    for name, rs in groups:
        if not rs:
            continue
        ref = sum(r["ref_taps"] for r in rs)
        ours = sum(r["our_taps"] for r in rs)
        hit = sum(r["matched"] for r in rs)
        leads = [r["lead_ms"] for r in rs if r["lead_ms"] is not None]
        sds = [r["err_sd_ms"] for r in rs if r["err_sd_ms"] is not None]
        label = f"{name} ({te.SPEED_BPM[name]:.0f})" if name in te.SPEED_BPM else name
        print(f"{label:<8}{len(rs):>4}{hit / max(1, ref):>8.1%}"
              f"{hit / max(1, ours):>8.1%}"
              f"{_fmt(sum(leads) / len(leads) if leads else None):>9}"
              f"{_fmt(sum(sds) / len(sds) if sds else None):>8}")
    print("(recall/precision pooled over taps; lead = median of our tap minus "
          "the moment of finger contact, + = ours later; jitter = per-tap SD "
          "around that, ms)")

    both = [r for r in ok if r.get("scoreable_ours") and r.get("scoreable_ref")]
    print(f"\nAgreement on {len(both)} recordings both sides could score "
          f"(ours - reference):")
    for key, unit in (("freq_hz", "Hz"), ("cv_pct", "CV%")):
        ba = te.bland_altman([r[f"{key}_ours"] for r in both],
                             [r[f"{key}_ref"] for r in both])
        if ba:
            print(f"  {key:<8} bias {ba['bias']:+.2f} {unit}, 95% LoA "
                  f"[{ba['loa_low']:+.2f}, {ba['loa_high']:+.2f}], "
                  f"MAE {ba['mae']:.2f}, r {_fmt(ba['r'], 3)}")
    same = sum(r["status_ours"] == r["status_ref"] for r in both)
    if both:
        print(f"  CV% band identical in {same}/{len(both)} recordings")
    unscored = [r for r in ok if not r.get("scoreable_ours")]
    if unscored:
        print(f"\n{len(unscored)} recordings our pipeline refused to score:")
        for r in unscored[:10]:
            print(f"  {r['subject']} {r['side']} FT{r['speed']}{r['take']}: "
                  f"{r.get('reason_ours')}")
    weak = [r for r in ok if (r.get("offset_r") or 0) < 0.5]
    if weak:
        print(f"\n{len(weak)} recordings aligned with r < 0.5 -- check their "
              f"timing figures by eye before trusting them.")
    diffs = [abs(r["offset_diff_ms"]) for r in ok if r.get("offset_diff_ms") is not None]
    if diffs:
        far = sum(d > 50 for d in diffs)
        print(f"\nClock offset, ours vs the dataset's lags.csv: median "
              f"{sorted(diffs)[len(diffs) // 2]:.0f} ms apart, {far} of "
              f"{len(diffs)} more than 50 ms apart")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", required=True, type=Path,
                    help="EHWGesture folder holding DataKinects/ and DataMOCAP/")
    ap.add_argument("--subjects", help="comma list, e.g. X01,X02 (default all)")
    ap.add_argument("--speeds", help="subset of S,N,F (default all)")
    ap.add_argument("--camera", default="master", choices=("master", "sub"))
    ap.add_argument("--mode", default="big_and_fast", choices=tuple(MODES))
    ap.add_argument("--tol-ms", type=float, default=150.0,
                    help="max gap for a tap to count as found (default 150)")
    ap.add_argument("--offset", default="estimate", choices=("estimate", "dataset"),
                    help="clock alignment: our correlation estimate (default) "
                         "or the dataset's lags.csv")
    ap.add_argument("--limit", type=int, help="stop after N recordings")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--cached-only", action="store_true",
                    help="score only videos whose MediaPipe output is already "
                         "cached; never run the landmarker")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be evaluated and exit")
    args = ap.parse_args()

    subjects = {s.strip().upper() for s in args.subjects.split(",")} \
        if args.subjects else None
    speeds = {s.strip().upper() for s in args.speeds.split(",")} \
        if args.speeds else None
    items = discover(args.root, args.camera, subjects, speeds)
    if args.cached_only:
        items = [i for i in items if _cache_path(i["video"], args.root).exists()]
    if args.limit:
        items = items[:args.limit]
    if not items:
        print(f"No {args.camera}_FT*.mp4 videos under "
              f"{args.root / 'DataKinects'}/<subject>/<side>/rgb/")
        return 1
    missing = sum(i["mocap"] is None for i in items)
    print(f"{len(items)} finger-tapping videos, {missing} without a marker file")
    if args.dry_run:
        for i in items:
            print(f"  {i['subject']} {i['side']:<5} FT{i['speed']}{i['take']} "
                  f"{'ok' if i['mocap'] else 'NO MOCAP'}  {i['video']}")
        return 0

    rows = []
    for k, item in enumerate(items, 1):
        tag = f"{item['subject']} {item['side']} FT{item['speed']}{item['take']}"
        t0 = time.time()
        try:
            trace = load_trace(item["video"], args.root, item["side"],
                               not args.no_cache)
            row = score_one(item, trace, mode_for(args.mode, item["bpm"]),
                            args.tol_ms / 1000.0, args.offset)
        except Exception as e:           # one bad file must not end a long run
            row = {"subject": item["subject"], "side": item["side"],
                   "speed": item["speed"], "take": item["take"],
                   "video": item["video"].name, "error": repr(e)}
        rows.append(row)
        rec = row.get("recall")
        print(f"[{k}/{len(items)}] {tag}: "
              + (f"{row['matched']}/{row['ref_taps']} taps found, "
                 f"{row['extra']} extra, CV% {_fmt(row.get('cv_pct_ours'))} "
                 f"vs {_fmt(row.get('cv_pct_ref'))}"
                 if rec is not None else row.get("error", "not scored"))
              + f"  ({time.time() - t0:.0f}s)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"ehwgesture_{args.mode}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    summarise(rows)
    print(f"\nPer-recording results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
