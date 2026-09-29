"""
Unit tests for core/orientation.py -- is this camera's picture mirrored?
Pure, no camera.

Run:  python screening_tests/tests/test_orientation.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from core import orientation as ori


# Unmirrored picture, right hand raised: hand at image-left of the nose and
# labelled "Right". Mirrored: image-right, labelled "Left".
NOT_MIRRORED = (0.30, 0.50, "Right")
MIRRORED = (0.70, 0.50, "Left")


def _hold(vote, frame, secs, fps=30, t0=0.0):
    out = None
    for i in range(int(secs * fps) + 1):
        out = vote.feed(t0 + i / fps, *frame)
    return out


def test_each_side_decides():
    assert _hold(ori.SideVote(), NOT_MIRRORED, ori.HOLD_S + 0.1) is False
    assert _hold(ori.SideVote(), MIRRORED, ori.HOLD_S + 0.1) is True


def test_a_short_hold_decides_nothing():
    assert _hold(ori.SideVote(), MIRRORED, ori.HOLD_S * 0.5) is None


def test_a_side_change_restarts_the_hold():
    v = ori.SideVote()
    _hold(v, MIRRORED, ori.HOLD_S * 0.8)
    assert _hold(v, NOT_MIRRORED, ori.HOLD_S * 0.5, t0=ori.HOLD_S * 0.8) is None
    assert v.side is False


def test_a_hand_in_front_of_the_face_does_not_count():
    near = (0.50 + ori.SIDE_MARGIN * 0.5, 0.50, "Left")
    assert ori.frame_side(*near) is None
    assert _hold(ori.SideVote(), near, 3.0) is None


def test_label_disagreeing_with_position_does_not_count_or_fail():
    # image-left of the face but labelled "Left": back of the hand, or a misread
    assert ori.frame_side(0.30, 0.50, "Left") is None
    v = ori.SideVote()
    _hold(v, (0.30, 0.50, "Left"), 3.0)
    assert v.mirrored is None
    assert _hold(v, NOT_MIRRORED, ori.HOLD_S + 0.1, t0=3.1) is False


def test_missing_face_or_hand_does_not_count():
    assert ori.frame_side(None, 0.5, "Right") is None
    assert ori.frame_side(0.3, None, "Right") is None
    assert _hold(ori.SideVote(), (None, 0.5, None), 3.0) is None


def test_a_brief_dropout_keeps_the_hold_a_long_one_restarts_it():
    gone = (None, 0.5, None)
    v = ori.SideVote()
    _hold(v, NOT_MIRRORED, 0.5)
    v.feed(0.5 + ori.GAP_S * 0.5, *gone)
    assert _hold(v, NOT_MIRRORED, 0.6, t0=0.5 + ori.GAP_S * 0.6) is False
    v = ori.SideVote()
    _hold(v, NOT_MIRRORED, 0.5)
    v.feed(0.5 + ori.GAP_S * 2, *gone)
    assert _hold(v, NOT_MIRRORED, 0.6, t0=0.5 + ori.GAP_S * 2.1) is None


def test_too_few_frames_cannot_decide():
    assert _hold(ori.SideVote(), MIRRORED, ori.HOLD_S + 0.5, fps=4) is None


def test_true_hand_convention():
    from core.hand_utils import true_hand
    assert true_hand("Right", selfie=False) == "right"
    assert true_hand("Left", selfie=False) == "left"
    assert true_hand("Right", selfie=True) == "left"
    assert true_hand("Left", selfie=True) == "right"


def test_fix_hand_labels_swaps_once_and_keeps_csv_in_step():
    import csv, json
    sys.path.insert(0, str(_REPO_ROOT / "tools"))
    import fix_hand_labels as fx
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        recs = [
            {"session_id": "a", "test": "finger_tapping", "hand": "left"},
            {"session_id": "b", "test": "spiral", "hand": "right"},
            {"session_id": "c", "test": "finger_tapping", "hand": "left",
             "hand_label_fixed": True},                   # saved after the fix
            {"session_id": "d", "test": "finger_tapping", "hand": "left",
             "source": "remote"},
            {"session_id": "e", "test": "tremor", "hand": "both"},
        ]
        for r in recs:
            (root / f"{r['session_id']}.json").write_text(json.dumps(r), "utf-8")
        with open(root / "index.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["session_id", "test", "hand"])
            w.writeheader()
            for r in recs:
                w.writerow({k: r[k] for k in ("session_id", "test", "hand")})

        dry = fx.fix(root, apply=False)
        assert dry["left->right"] == 1 and dry["right->left"] == 1
        assert json.loads((root / "a.json").read_text("utf-8"))["hand"] == "left"

        fx.fix(root, apply=True)
        hands = {r["session_id"]: r["hand"] for r in
                 csv.DictReader(open(root / "index.csv", encoding="utf-8"))}
        for sid in "abcde":
            assert json.loads((root / f"{sid}.json").read_text("utf-8"))["hand"]                 == hands[sid], sid
        assert hands == {"a": "right", "b": "left", "c": "left",
                         "d": "left", "e": "both"}

        again = fx.fix(root, apply=True)
        assert again["left->right"] == 0 and again["right->left"] == 0


def test_store_round_trip_and_forget():
    old = ori.CACHE_PATH
    with tempfile.TemporaryDirectory() as d:
        ori.CACHE_PATH = Path(d) / "cache.json"
        # the backend cache lives in the same file and must survive
        ori.CACHE_PATH.write_text('{"0|640x480|0": [700, true]}', "utf-8")
        try:
            assert ori.load(0) is None
            assert ori.save(0, True) and ori.load(0) is True
            assert ori.load("0") is True                  # index as int or str
            assert ori.save("http://cam/video", False)
            assert ori.load("http://cam/video") is False
            assert ori.load(1) is None                     # other cameras untouched
            assert ori.save(0, None) and ori.load(0) is None
            assert '"0|640x480|0"' in ori.CACHE_PATH.read_text("utf-8")
        finally:
            ori.CACHE_PATH = old


def test_a_named_camera_keeps_its_answer_when_its_index_moves():
    old = ori.CACHE_PATH
    with tempfile.TemporaryDirectory() as d:
        ori.CACHE_PATH = Path(d) / "cache.json"
        try:
            # an answer saved before names were known is still read...
            assert ori.save(0, True, name="")
            assert ori.load(0, name="Razer") is True
            # ...until the camera is answered by name, which drops the index key
            assert ori.save(0, False, name="Razer")
            assert ori.load(0, name="") is None, "index key left for the next camera"
            # the Razer moves to index 1; its answer goes with it
            assert ori.load(1, name="Razer") is False
            # and the camera that now sits at 0 does not inherit it
            assert ori.load(0, name="ASUS") is None
            # forgetting by name clears it
            assert ori.save(1, None, name="Razer") and ori.load(1, name="Razer") is None
            # the tools pass no name and read the launcher's env var instead
            ori.save(2, True, name="Kiyo")
            prev = os.environ.get("HAND3D_CAMERA_NAME")
            os.environ["HAND3D_CAMERA_NAME"] = "Kiyo"
            try:
                assert ori.load(5) is True
            finally:
                if prev is None:
                    os.environ.pop("HAND3D_CAMERA_NAME", None)
                else:
                    os.environ["HAND3D_CAMERA_NAME"] = prev
        finally:
            ori.CACHE_PATH = old


def test_store_survives_a_broken_file():
    old = ori.CACHE_PATH
    with tempfile.TemporaryDirectory() as d:
        ori.CACHE_PATH = Path(d) / "cache.json"
        ori.CACHE_PATH.write_text("not json", "utf-8")
        try:
            assert ori.load(0) is None
            assert ori.save(0, False) and ori.load(0) is False
        finally:
            ori.CACHE_PATH = old


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
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
