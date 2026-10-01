#!/usr/bin/env python3
"""
Hand-only demo clips for the hub's Why This page, from HUBU-FIS.

    .venv/Scripts/python tools/make_why_clips.py --root C:/Datasets/HUBU-FIS
    .venv/Scripts/python tools/make_why_clips.py --root C:/Datasets/HUBU-FIS --ids PATIENT07_DCHA

One clip per UPDRS grade (0-3) by default. Each one is picked, not chosen by
eye: every video is scored on the seconds the page will show (from the HUBU
eval's cached traces, results/tapping_eval/cache/, so no video is re-read), and
the scoreable one whose CV% sits closest to its grade's median is used. Scoring
the window shown rather than the whole video matters: a hand can tap evenly for
12 s and fall apart later, and the page would then show a verdict that
contradicts its grade.

For each clip this writes launcher_web/img/validation/clips/updrs-<g>.webm
(or <id>.webm with --ids) and one launcher_web/img/validation/clips.json
entry the page replays in step with the video: the smoothed distance trace,
the thresholds in force, every accepted tap and the engine's final score. The
analysis is the eval's own pipeline (same landmarker settings, detect(),
compute_metrics with Big & Fast), run on the seconds the clip shows.

Only the hand is shown. The frame is cropped to a square that follows the hand,
and everything outside a padded hull of its 21 landmarks is pixelated and
dimmed, so a face or room that strays into the crop is not recognisable. A
frame with no hand found is pixelated whole. No patient ID goes into the
output; clips are named by grade.

HUBU-FIS: zenodo.org/records/17738775, CC BY 4.0, Universidad de Burgos and
Hospital Universitario de Burgos. The page credits it under the player.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))

import cv2
import numpy as np

from core.hand_utils import HAND_CONNECTIONS
from core.tapping.detector import thumb_index_distance
from core.tapping.metrics import compute_metrics
from core.tapping.modes import MODES
from tools.eval_tapping_hubu import discover
from tools.eval_tapping_videos import MODEL_PATH, _bbox_area, detect, load_trace

MODE = MODES["big_and_fast"]
OUT = _REPO_ROOT / "launcher_web" / "img" / "validation"
SIZE = 360            # output clip is SIZE x SIZE
OUT_FPS = 15          # frames written per second; the analysis keeps every frame
MAX_SIDE = 960        # the HUBU eval's downscale, so landmarks match its run
CROP_SCALE = 2.1      # crop side, in multiples of the hand's larger bbox side
CROP_EMA = 0.12       # how fast the crop follows the hand (per frame)
HULL_PAD = 0.28       # hull dilation, as a fraction of the hand's size
PIXEL = 15            # outside the hull: one block per PIXEL output pixels
TEAL = (148, 165, 18)     # BGR of the hub's #12A594
WHITE = (245, 245, 245)


def pick_clips(items: list[dict], root: Path, seconds: float) -> list[dict]:
    """The typical scoreable clip of each grade, scored on the first `seconds`."""
    scored = []
    for n, item in enumerate(items, 1):
        print(f"\rScoring {n}/{len(items)} on the first {seconds:g} s", end="", flush=True)
        tr = load_trace(item["video"], root, None, True, pick="largest", max_side=MAX_SIDE)
        keep = [i for i, t in enumerate(tr["t"]) if t < seconds]
        cut = {"fps": tr["fps"], "frames": len(keep),
               "t": [tr["t"][i] for i in keep], "d": [tr["d"][i] for i in keep]}
        if sum(d is not None for d in cut["d"]) < 0.95 * max(1, cut["frames"]):
            continue
        m = analyse(cut)["metrics"]
        if m["scoreable"] and m["cv_pct"] is not None:
            scored.append((item, m["cv_pct"]))
    print()
    out = []
    for g in sorted({i["updrs"] for i, _ in scored}):
        rs = [(i, cv) for i, cv in scored if i["updrs"] == g]
        med = statistics.median(cv for _, cv in rs)
        best, cv = min(rs, key=lambda r: abs(r[1] - med))
        print(f"UPDRS {g}: {len(rs)} scoreable, median CV {med:.1f}%, picked one at {cv:.1f}%")
        out.append(best)
    return out


def track(video: Path, seconds: float) -> dict:
    """Per-frame landmarks (raw, for drawing) and distance (smoothed, as the
    eval derives it), on the downscaled frame."""
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
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.55,
    )
    with quiet.muted_native_stderr():
        landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
    fx, fy = make_landmark_filters()
    t_list, d_list, lm_list, sm_list = [], [], [], []
    shape = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = len(t_list) / fps
            if t >= seconds:
                break
            frame = _downscale(frame)
            shape = frame.shape[:2]
            rgb = preprocess_for_mediapipe(frame, enable=True)
            res = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(round(t * 1000)))
            d = lms = sm = None
            if res.hand_landmarks:
                k = max(range(len(res.hand_landmarks)),
                        key=lambda i: _bbox_area(res.hand_landmarks[i]))
                raw = res.hand_landmarks[k]
                smooth = smooth_landmarks(raw, fx, fy, t)
                d = thumb_index_distance(smooth)
                lms = [(p.x, p.y) for p in raw]
                sm = [(x, y) for x, y, _ in smooth]
            t_list.append(t)
            d_list.append(d)
            lm_list.append(lms)
            sm_list.append(sm)
    finally:
        landmarker.close()
        cap.release()
    return {"fps": fps, "frames": len(t_list), "t": t_list, "d": d_list,
            "lms": lm_list, "smooth": sm_list, "shape": shape}


def _downscale(frame):
    if max(frame.shape[:2]) > MAX_SIDE:
        s = MAX_SIDE / max(frame.shape[:2])
        frame = cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return frame


def crop_path(tr: dict) -> list[tuple[float, float, float]]:
    """(cx, cy, side) in pixels per frame: a fixed side sized to the largest
    hand, centre easing after the hand, held where it was when the hand drops."""
    h, w = tr["shape"]
    sizes = [max(max(x for x, _ in l) - min(x for x, _ in l),
                 max(y for _, y in l) - min(y for _, y in l))
             for l in tr["lms"] if l]
    if not sizes:
        return [(w / 2, h / 2, min(w, h))] * tr["frames"]
    side = min(min(w, h), max(sizes) * max(w, h) * CROP_SCALE)
    first = next(l for l in tr["lms"] if l)
    cx = sum(x for x, _ in first) / 21 * w
    cy = sum(y for _, y in first) / 21 * h
    out = []
    for l in tr["lms"]:
        if l:
            tx = sum(x for x, _ in l) / 21 * w
            ty = sum(y for _, y in l) / 21 * h
            cx += CROP_EMA * (tx - cx)
            cy += CROP_EMA * (ty - cy)
        x = min(max(cx, side / 2), w - side / 2)
        y = min(max(cy, side / 2), h - side / 2)
        out.append((x, y, side))
    return out


def render(video: Path, tr: dict, dest: Path) -> None:
    path = crop_path(tr)
    h, w = tr["shape"]
    # Every step-th frame, so the clip keeps its real duration and the page's
    # chart, which runs on the analysis clock, stays in step with it.
    step = max(1, round(tr["fps"] / OUT_FPS))
    writer = None
    for fourcc in ("VP90", "VP80"):
        writer = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*fourcc),
                                 tr["fps"] / step, (SIZE, SIZE))
        if writer.isOpened():
            break
    if not writer or not writer.isOpened():
        sys.exit("OpenCV could not open a WebM writer (VP9 or VP8).")
    cap = cv2.VideoCapture(str(video))
    try:
        for i in range(tr["frames"]):
            ok, frame = cap.read()
            if not ok:
                break
            if i % step:
                continue
            frame = _downscale(frame)
            cx, cy, side = path[i]
            x0, y0 = max(0, int(round(cx - side / 2))), max(0, int(round(cy - side / 2)))
            s = int(round(side))
            crop = cv2.resize(frame[y0:y0 + s, x0:x0 + s], (SIZE, SIZE),
                              interpolation=cv2.INTER_AREA)
            k = SIZE / s
            # The mask follows the raw landmarks (where the hand really is);
            # the skeleton is the smoothed set the distance is measured on.
            to_px = lambda l: np.array([((x * w - x0) * k, (y * h - y0) * k) for x, y in l],
                                       np.float32) if l else None
            crop = _hands_only(crop, to_px(tr["lms"][i]))
            sm = to_px(tr["smooth"][i])
            if sm is not None:
                _draw_hand(crop, sm)
            writer.write(crop)
    finally:
        cap.release()
        writer.release()


def _hands_only(img, pts):
    """Pixelate and dim everything outside a padded hull of the hand."""
    small = cv2.resize(img, (SIZE // PIXEL, SIZE // PIXEL), interpolation=cv2.INTER_AREA)
    blocky = cv2.resize(small, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST)
    blocky = cv2.GaussianBlur(blocky, (0, 0), PIXEL / 2)
    blocky = (blocky * 0.35).astype(np.uint8)
    if pts is None:
        return blocky
    size = float(max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])))
    mask = np.zeros((SIZE, SIZE), np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull(pts.astype(np.int32)), 255)
    r = max(3, int(size * HULL_PAD))
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    mask = cv2.GaussianBlur(mask, (0, 0), r / 3).astype(np.float32)[..., None] / 255
    return (img * mask + blocky * (1 - mask)).astype(np.uint8)


# The test reads the thumb and index tips over the wrist-to-middle-knuckle
# span. The middle, ring and little fingers never enter it, and seen side-on
# they are curled behind the palm, so the model can only guess them and the
# guesses jump about. They are drawn faint so the eye follows what is measured.
_UNUSED = set(range(10, 13)) | set(range(14, 17)) | set(range(18, 21))


def _draw_hand(img, pts):
    p = [tuple(int(round(v)) for v in q) for q in pts]
    faint = img.copy()
    for a, b in HAND_CONNECTIONS:
        if a in _UNUSED or b in _UNUSED:
            cv2.line(faint, p[a], p[b], WHITE, 1, cv2.LINE_AA)
    cv2.addWeighted(faint, 0.3, img, 0.7, 0, dst=img)
    for a, b in HAND_CONNECTIONS:
        if a not in _UNUSED and b not in _UNUSED:
            cv2.line(img, p[a], p[b], WHITE, 2, cv2.LINE_AA)
    for i, q in enumerate(p):
        if i not in _UNUSED:
            cv2.circle(img, q, 5 if i in (4, 8) else 3, TEAL if i in (4, 8) else WHITE, -1, cv2.LINE_AA)
    cv2.line(img, p[4], p[8], TEAL, 2, cv2.LINE_AA)


def analyse(tr: dict) -> dict:
    """The eval's scoring, on the seconds the clip shows."""
    taps, series, _calibrated, near_miss = detect(tr, MODE)
    vis = sum(d is not None for d in tr["d"]) / max(1, tr["frames"])
    t = tr["t"]
    m = compute_metrics(MODE, taps, series, t[0], t[-1] if t else 0.0,
                        hand_visible_ratio=vis, camera_fps=tr["fps"], near_miss=near_miss)
    # detect() does not hand back its thresholds, so replay them: the same
    # detector, fed the same frames, lands on the same lines.
    from core.tapping.detector import Calibrator, TapDetector
    from tools.eval_tapping_videos import EMA_ALPHA_FAST
    cal = Calibrator()
    for tt, d in zip(tr["t"], tr["d"]):
        if d is not None:
            cal.update(tt, d)
            if cal.done:
                break
    lo, hi = cal.result()
    det = TapDetector(MODE.min_intertap_s, EMA_ALPHA_FAST, lo, hi)
    for tt, d in zip(tr["t"], tr["d"]):
        det.update(tt, d)
    r3 = lambda v: round(v, 3)
    return {
        "series": [[r3(a), r3(b)] for a, b in det.series],
        "thresholds": [[r3(a), r3(b), r3(c)] for a, b, c in det.threshold_series],
        "taps": [r3(x) for x in taps],
        "metrics": {k: m.get(k) for k in ("taps", "frequency_hz", "cv_pct",
                                          "decrement_pct_per_s", "status", "label",
                                          "scoreable", "reason")},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", required=True, type=Path, help="HUBU-FIS folder")
    ap.add_argument("--ids", nargs="*", help="clip ids instead of one typical clip per grade")
    ap.add_argument("--seconds", type=float, default=12.0, help="length of each clip")
    args = ap.parse_args()

    items = discover(args.root)
    chosen = ([i for i in items if i["id"] in set(args.ids)] if args.ids
              else pick_clips(items, args.root, args.seconds))
    if not chosen:
        sys.exit("No clips matched.")
    (OUT / "clips").mkdir(parents=True, exist_ok=True)
    entries = []
    for n, item in enumerate(chosen, 1):
        name = f"updrs-{item['updrs']}" if not args.ids else f"clip-{n}"
        print(f"[{n}/{len(chosen)}] UPDRS {item['updrs']} -> clips/{name}.webm", flush=True)
        tr = track(item["video"], args.seconds)
        render(item["video"], tr, OUT / "clips" / f"{name}.webm")
        entries.append({"file": f"img/validation/clips/{name}.webm",
                        "updrs": item["updrs"], "group": item["group"],
                        "fps": round(tr["fps"], 2),
                        "duration_s": round(tr["frames"] / tr["fps"], 2),
                        **analyse(tr)})
    entries.sort(key=lambda e: e["updrs"])
    (OUT / "clips.json").write_text(json.dumps({
        "source": "HUBU-FIS, zenodo.org/records/17738775, CC BY 4.0",
        "mode": MODE.key, "clips": entries}, separators=(",", ":")))
    print(f"Wrote {len(entries)} clips and {OUT / 'clips.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
