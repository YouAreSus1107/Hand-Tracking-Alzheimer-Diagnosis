"""
Unit tests for core/camera.open_capture's backend choice -- which capture
settings it keeps, judged by the frame rate a candidate actually delivers
rather than the one its driver claims. No camera: cv2.VideoCapture and the
rate measurement are replaced by fakes.

Run:  python screening_tests/tests/test_camera.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

import cv2

from core import camera, camera_list, orientation

DSHOW, MSMF = cv2.CAP_DSHOW, cv2.CAP_MSMF


class _FakeCap:
    def __init__(self, rates, log, sources, source, backend, nofps=None):
        self.rate = rates.get(backend)
        # what the camera delivers when no rate is asked for, if different
        self.nofps = (nofps or {}).get(backend)
        self.backend = backend
        self.props = {}
        log.append(backend)
        sources.append((backend, source))

    def delivered(self):
        if self.nofps is not None and cv2.CAP_PROP_FPS not in self.props:
            return self.nofps
        return self.rate

    def isOpened(self):
        return self.rate is not None

    def set(self, prop, value):
        self.props[prop] = value
        return True

    def get(self, prop):
        return self.props.get(prop, -1.0)

    def read(self):
        return True, None

    def release(self):
        pass


class _Env:
    """Fake cameras delivering `rates` {backend: fps}, a temp cache file, and
    a chosen camera name; restores everything on exit.

    `mf` is Media Foundation's device list (None: could not be listed), so a
    test never depends on the cameras plugged into the machine running it."""

    def __init__(self, rates, name="", nofps=None, mf=None):
        self.rates, self.name, self.opens, self.nofps = rates, name, [], nofps
        self.mf, self.sources = mf, []

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        cache = Path(self._dir.name) / "cache.json"
        self._saved = (camera._CACHE_PATH, orientation.CACHE_PATH, camera.sys,
                       camera.measure_fps, camera.cv2.VideoCapture,
                       os.environ.get(camera.ENV_CAMERA_NAME), camera_list.msmf_names)
        camera_list.msmf_names = lambda: self.mf
        camera._CACHE_PATH = orientation.CACHE_PATH = cache
        camera.sys = types.SimpleNamespace(platform="win32")
        camera.measure_fps = lambda cap, *a, **k: cap.delivered()
        camera.cv2.VideoCapture = (lambda source, backend=None:
                                   _FakeCap(self.rates, self.opens, self.sources,
                                            source, backend, self.nofps))
        os.environ[camera.ENV_CAMERA_NAME] = self.name
        return self

    def __exit__(self, *exc):
        (camera._CACHE_PATH, orientation.CACHE_PATH, camera.sys,
         camera.measure_fps, camera.cv2.VideoCapture, name,
         camera_list.msmf_names) = self._saved
        if name is None:
            os.environ.pop(camera.ENV_CAMERA_NAME, None)
        else:
            os.environ[camera.ENV_CAMERA_NAME] = name
        self._dir.cleanup()

    def cache(self) -> dict:
        import json
        return json.loads(camera._CACHE_PATH.read_text("utf-8"))


def test_a_camera_short_on_dshow_moves_to_msmf():
    # The Razer: DirectShow claims 60 and delivers 30; MSMF delivers 60.
    with _Env({DSHOW: 30.0, MSMF: 60.0}, name="Razer Kiyo V2 X") as env:
        cap = camera.open_capture(0, fps=60)
        assert cap is not None and cap.backend == "MSMF", cap and cap.backend
        assert cap.fps_measured == 60.0
        assert env.opens == [DSHOW, DSHOW, DSHOW, MSMF], env.opens
        entry = env.cache()["name:Razer Kiyo V2 X|640x480|60"]
        assert entry == [MSMF, True, 60.0], entry


def test_the_cached_answer_opens_once():
    with _Env({DSHOW: 30.0, MSMF: 60.0}, name="Razer Kiyo V2 X") as env:
        camera.open_capture(0, fps=60)
        env.opens.clear()
        cap = camera.open_capture(0, fps=60)
        assert cap.backend == "MSMF" and env.opens == [MSMF], env.opens


def test_a_camera_that_tops_out_everywhere_keeps_dshow():
    # The ASUS: 30 on every backend. Nothing reaches 60, so the best is
    # reopened -- the first DirectShow candidate, the path it always had.
    with _Env({DSHOW: 30.0, MSMF: 29.0}, name="ASUS HD webcam") as env:
        cap = camera.open_capture(0, fps=60)
        assert cap.backend == "DSHOW" and cap.fps_measured == 30.0
        assert env.opens[-1] == DSHOW and len(env.opens) == 6, env.opens
        assert env.cache()["name:ASUS HD webcam|640x480|60"] == [DSHOW, True, 30.0]
        env.opens.clear()                   # next launch: the cached best, once
        cap = camera.open_capture(0, fps=60)
        assert cap.backend == "DSHOW" and env.opens == [DSHOW], env.opens


def test_the_asus_keeps_directshow_by_not_asking_for_60():
    # Measured 2026-09-28: over DirectShow the ASUS delivers 15 fps when 60 is
    # asked for and 30 when nothing is; MSMF delivers 30 either way. The
    # unasked DirectShow open is preferred to MSMF at the same rate.
    with _Env({DSHOW: 15.0, MSMF: 30.0}, name="ASUS HD webcam",
              nofps={DSHOW: 29.4}) as env:
        cap = camera.open_capture(0, fps=60)
        assert cap.backend == "DSHOW" and cap.fps_measured == 29.4, cap.info()
        assert cv2.CAP_PROP_FPS not in cap._cap.props       # the rate was not asked
        entry = env.cache()["name:ASUS HD webcam|640x480|60"]
        assert entry == [DSHOW, False, 29.4, False], entry
        env.opens.clear()
        cap = camera.open_capture(0, fps=60)                # cached: one open,
        assert env.opens == [DSHOW] and cv2.CAP_PROP_FPS not in cap._cap.props


def test_a_near_tie_keeps_the_preferred_backend():
    # What the ASUS actually measured on 2026-09-28: MSMF 29.5, DSHOW 29.3.
    # Noise, not a reason to leave DirectShow.
    with _Env({DSHOW: 29.3, MSMF: 29.5}, name="ASUS HD webcam"):
        assert camera.open_capture(0, fps=60).backend == "DSHOW"


def test_a_stale_cache_entry_is_measured_and_left():
    # An old two-element entry pinned DirectShow; it is timed like any other.
    with _Env({DSHOW: 30.0, MSMF: 60.0}) as env:
        camera._CACHE_PATH.write_text('{"0|640x480|60": [%d, true]}' % DSHOW, "utf-8")
        cap = camera.open_capture(0, fps=60)
        assert cap.backend == "MSMF"
        assert env.cache()["0|640x480|60"] == [MSMF, True, 60.0]


def test_no_rate_asked_means_no_measurement():
    with _Env({DSHOW: 30.0, MSMF: 60.0}) as env:
        cap = camera.open_capture(0)
        assert cap.backend == "DSHOW" and cap.fps_measured is None
        assert env.opens == [DSHOW]
        assert env.cache()["0|640x480|0"] == [DSHOW, True]


def test_the_key_follows_the_name_not_the_index():
    # Two cameras swapping indices must not inherit each other's backend.
    with _Env({DSHOW: 30.0, MSMF: 60.0}, name="Razer Kiyo V2 X") as env:
        camera.open_capture(1, fps=60)
        assert "name:Razer Kiyo V2 X|640x480|60" in env.cache()
        assert not any(k.startswith("1|") for k in env.cache())


def test_nothing_opens():
    with _Env({}) as env:
        assert camera.open_capture(0, fps=60) is None
        assert len(env.opens) == 5


def test_info_reports_what_was_negotiated():
    with _Env({DSHOW: 30.0, MSMF: 60.0}, name="Razer Kiyo V2 X"):
        cap = camera.open_capture(0, fps=60)
        info = camera.capture_info(cap)
        assert info["camera_name"] == "Razer Kiyo V2 X"
        assert info["backend"] == "MSMF" and info["fps_measured"] == 60.0
        assert info["fps_requested"] == 60


def test_info_tolerates_a_plain_capture():
    with _Env({}, name="X"):
        assert camera.capture_info(object()) == {"camera_name": "X"}


def test_frame_time_only_from_msmf():
    with _Env({DSHOW: 60.0}):
        cap = camera.open_capture(0, fps=60)
        cap._cap.props[cv2.CAP_PROP_POS_MSEC] = 1234.5
        assert cap.frame_time_ms() is None            # DSHOW: never trusted
        cap.backend = "MSMF"
        assert cap.frame_time_ms() == 1234.5


# ── the two backends number cameras differently ─────────────────────────────

def test_msmf_opens_the_chosen_camera_not_the_same_number():
    # DirectShow: 0 OBS (virtual), 1 Razer. Media Foundation skips OBS, so the
    # Razer is MSMF 0 — opening MSMF 1 would have opened the ASUS.
    mf = ["Razer Kiyo V2 X", "ASUS HD webcam"]
    with _Env({DSHOW: 30.0, MSMF: 60.0}, name="Razer Kiyo V2 X", mf=mf) as env:
        cap = camera.open_capture(1, fps=60)
        assert cap.backend == "MSMF"
        assert (MSMF, 0) in env.sources and (MSMF, 1) not in env.sources, env.sources
        assert all(src == 1 for b, src in env.sources if b == DSHOW), env.sources


def test_a_camera_msmf_cannot_see_never_opens_through_msmf():
    # A DirectShow-only virtual camera: trying MSMF at its index would open
    # a different, real camera.
    with _Env({DSHOW: 30.0, MSMF: 60.0}, name="OBS Virtual Camera",
              mf=["Razer Kiyo V2 X"]) as env:
        cap = camera.open_capture(0, fps=60)
        assert cap.backend == "DSHOW"
        assert MSMF not in env.opens, env.opens


def test_an_unlisted_msmf_keeps_the_index():
    with _Env({DSHOW: 30.0, MSMF: 60.0}, name="Razer Kiyo V2 X", mf=None) as env:
        camera.open_capture(1, fps=60)
        assert (MSMF, 1) in env.sources, env.sources


def test_msmf_index_matching():
    ds = ["OBS Virtual Camera", "Cam", "Cam", "Other"]
    mf = ["Cam", "Other", "Cam"]
    assert camera_list.msmf_index("Other", 3, ds, mf) == 1
    assert camera_list.msmf_index("OBS Virtual Camera", 0, ds, mf) is None
    # identical models keep their order within the name
    assert camera_list.msmf_index("Cam", 1, ds, mf) == 0
    assert camera_list.msmf_index("Cam", 2, ds, mf) == 2
    assert camera_list.msmf_index("", 2, ds, mf) == 2          # no name: as given


def test_resolve_index_follows_the_name():
    cams = [{"index": 0, "name": "ASUS"}, {"index": 1, "name": "Razer"}]
    assert camera_list.resolve_index("Razer", 0, cams) == 1     # shifted
    assert camera_list.resolve_index("Razer", 1, cams) == 1
    assert camera_list.resolve_index("Gone", 3, cams) == 3      # unplugged: kept
    assert camera_list.resolve_index("", 4, cams) == 4


def test_letterbox_pads_the_short_axis():
    assert camera.letterbox_pad(640, 480, 1920, 1080) == (106, 0, 107, 0)   # 4:3 on 16:9
    assert camera.letterbox_pad(1280, 720, 1920, 1080) == (0, 0, 0, 0)      # same shape
    assert camera.letterbox_pad(480, 640, 1920, 1080) == (329, 0, 329, 0)   # portrait phone
    assert camera.letterbox_pad(1280, 480, 1920, 1080) == (0, 120, 0, 120)  # wider than screen
    assert camera.letterbox_pad(640, 480, 0, 0) == (0, 0, 0, 0)


def test_show_pads_to_the_screen_and_clicks_come_back_unpadded():
    import numpy as np
    shown, calls = {}, []
    real = (cv2.imshow, cv2.setMouseCallback)
    cv2.imshow = lambda name, img: shown.__setitem__(name, img)
    cv2.setMouseCallback = lambda name, cb: shown.__setitem__("cb", cb)
    try:
        camera._screens["w"] = (1920, 1080)
        camera.show("w", np.full((480, 640, 3), 255, np.uint8))
        img = shown["w"]
        assert img.shape[:2] == (480, 853)
        assert img[:, :106].max() == 0 and img[:, -107:].max() == 0
        assert img[:, 106:-107].min() == 255
        camera.set_mouse_callback("w", lambda *a: calls.append(a[1:3]))
        shown["cb"](cv2.EVENT_LBUTTONDOWN, 106 + 20, 30, 0, None)
        assert calls == [(20, 30)]
        camera.show("plain", np.zeros((10, 10, 3), np.uint8))       # no window: as is
        assert shown["plain"].shape[:2] == (10, 10)
    finally:
        cv2.imshow, cv2.setMouseCallback = real
        camera._screens.pop("w", None)
        camera._pads.pop("w", None)


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
