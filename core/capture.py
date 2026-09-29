"""
Record every camera frame now, analyse it after.

Why this exists: a 60 fps camera is wasted on a loop that runs MediaPipe live,
because live inference is what sets the loop's rate (16-30 fps on a laptop,
docs/performance/FPS_FINDINGS.md). Measured on the Razer Kiyo V2 X at 60 fps
(docs/tests/TREMOR_RESTRUCTURE_PLAN.md §1): a thread that only reads, flips and
JPEG-encodes holds 59.5 fps beside a live MediaPipe, and the same MediaPipe
run afterwards over the recorded frames takes 16 ms a frame instead of 50,
because nothing is competing with it. So:

  FrameRecorder (this thread)   reads every frame, stamps it, flips it to
                                selfie view, hands the newest to the UI, and
                                while a Take is armed keeps it as a JPEG
  the test's run loop           shows the newest frame and runs MediaPipe on
                                it live, for positioning and prompts only
  an analyser, after            MediaPipe on every frame of the Take

Nothing here knows about any one test. Frames are held in memory only and are
dropped with their Take; nothing is written to disk.

The clock: frames carry host time (time.time, the clock the glove's
imu_series() selects on), but when the capture has a device timestamp
(core/camera.Capture.frame_time_ms: MSMF) the frame is placed by that instead,
anchored to host time. Device stamps step exactly one frame period and jump by
whole periods over frames never read, while host read times jitter by ±7 ms,
so this is what lets an analysis place every frame where it was captured and
count the ones that were lost.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field

import cv2
import numpy as np

JPEG_QUALITY = 90            # 56 kB and 2.8 ms a 640x480 frame (measured)
MAX_TAKE_FRAMES = 2000       # ~33 s at 60 fps; beyond it a Take stops growing
ANCHOR_FRAMES = 300          # device->host offset: min over the last ~5 s


@dataclass
class Take:
    """The frames recorded while one hold (or trial) was armed."""
    tag: str
    t: list = field(default_factory=list)       # frame times, s (host clock)
    jpeg: list = field(default_factory=list)    # encoded frames, selfie view
    device_clock: bool = False                  # t came from device stamps
    overflow: bool = False                      # hit MAX_TAKE_FRAMES
    closed: bool = False
    # While recording: each frame's host read time and device stamp (s, or
    # None). close() turns them into `t`.
    _host: list = field(default_factory=list, repr=False)
    _dev: list = field(default_factory=list, repr=False)

    def close(self):
        """Fix the frame times. With a device stamp on every frame, each
        frame is placed at its device time plus ONE offset for the whole
        Take -- the smallest host-minus-device gap in it, since a frame is
        read late, never early. One offset, so the spacing inside the Take is
        exactly the device's; a running estimate would step every time its
        minimum changed. Otherwise the host read times are all there is."""
        if self.closed:
            return
        self.closed = True
        if self._dev and all(d is not None for d in self._dev):
            off = min(h - d for h, d in zip(self._host, self._dev))
            self.t = [d + off for d in self._dev]
            self.device_clock = True
        else:
            self.t = list(self._host)
            self.device_clock = False
        self._host, self._dev = [], []

    def __len__(self):
        return len(self.t) if self.closed else len(self._host)

    def frames(self):
        """(t, BGR frame) in order, decoded on demand."""
        for t, buf in zip(self.t, self.jpeg):
            yield t, cv2.imdecode(buf, cv2.IMREAD_COLOR)

    def free(self):
        self.jpeg = []


class DeviceAnchor:
    """Maps device timestamps (ms) onto the host clock, frame by frame, for
    the picture the UI shows (a Take fixes its own times in Take.close()).

    Host time = device time + offset, where the offset is the smallest
    host-minus-device gap seen recently: a frame can be read late, never
    early, so the minimum is the read latency's floor and the jitter above it
    is the read being late. Recent, not all-time, so slow drift between the
    two clocks cannot accumulate."""

    def __init__(self, n: int = ANCHOR_FRAMES):
        self._gaps = deque(maxlen=n)

    def place(self, host_s: float, device_ms: float | None) -> float:
        if device_ms is None:
            return host_s
        dev_s = device_ms / 1000.0
        self._gaps.append(host_s - dev_s)
        return dev_s + min(self._gaps)


class FrameRecorder(threading.Thread):
    """Owns the capture. `next_frame()` for the UI; `arm()`/`disarm()` around
    anything that should be analysed later."""

    def __init__(self, cap, flip: bool = True, clock=time.time,
                 jpeg_quality: int = JPEG_QUALITY,
                 max_take_frames: int = MAX_TAKE_FRAMES):
        super().__init__(daemon=True, name="frame-recorder")
        self.cap = cap
        self.flip = flip
        self.clock = clock
        self.max_take_frames = max_take_frames
        self._params = [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)]
        self._anchor = DeviceAnchor()
        self._lock = threading.Lock()
        self._new = threading.Condition(self._lock)
        self._frame = None
        self._frame_t = 0.0
        self._seq = 0
        self._take: Take | None = None
        self._stop = threading.Event()
        self.fps = 0.0
        self.frames_read = 0
        self.error: str | None = None

    # ── thread side ──
    def _stamp(self) -> tuple[float, float, float | None]:
        """(time shown to the UI, host read time, device time in s or None)."""
        host = self.clock()
        get = getattr(self.cap, "frame_time_ms", None)
        dev = None
        if callable(get):
            try:
                dev = get()
            except Exception:  # noqa: BLE001 - a clock is never worth a crash
                dev = None
        return (self._anchor.place(host, dev), host,
                dev / 1000.0 if dev is not None else None)

    def step(self) -> bool:
        """Read and handle one frame. False when the camera gave nothing.
        run() calls it in a loop; tests call it directly."""
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return False
        t, host, dev = self._stamp()
        if self.flip:
            frame = cv2.flip(frame, 1)
        with self._lock:
            last = self._frame_t if self._seq else None
            take = self._take
        if last is not None and t > last:
            dt = t - last
            self.fps = (1.0 / dt) if self.fps == 0 else 0.95 * self.fps + 0.05 / dt
        if take is not None and not take.closed:
            if len(take) >= self.max_take_frames:
                take.overflow = True
            else:
                ok_enc, buf = cv2.imencode(".jpg", frame, self._params)
                if ok_enc:
                    with self._lock:
                        if not take.closed:
                            take._host.append(host)
                            take._dev.append(dev)
                            take.jpeg.append(buf)
        with self._new:
            self._frame, self._frame_t, self._seq = frame, t, self._seq + 1
            self.frames_read += 1
            self._new.notify_all()
        return True

    def run(self):
        while not self._stop.is_set():
            try:
                if not self.step():
                    time.sleep(0.005)
            except cv2.error as e:     # one bad frame never ends a run
                self.error = str(e)
                time.sleep(0.005)

    # ── UI side ──
    def next_frame(self, after_seq: int, timeout: float = 1.0):
        """(seq, t, frame) of the newest frame after `after_seq`, or None.
        `t` is the frame's capture time, the clock a Take is stamped with."""
        with self._new:
            if self._seq <= after_seq:
                self._new.wait(timeout)
            if self._seq <= after_seq or self._frame is None:
                return None
            return self._seq, self._frame_t, self._frame

    def arm(self, tag: str) -> Take:
        """Start keeping frames. An armed Take is closed first."""
        take = Take(tag)
        with self._lock:
            if self._take is not None:
                self._take.close()
            self._take = take
        return take

    def disarm(self) -> Take | None:
        """Stop keeping frames; the Take that was recording, now closed."""
        with self._lock:
            take, self._take = self._take, None
            if take is not None:
                take.close()
        return take

    def stop(self):
        self._stop.set()
        if self.is_alive():
            self.join(timeout=2.0)


def drop_stats(ts) -> dict:
    """How regular a Take's frame times are: the nominal period, and how many
    frames were lost (an interval of k periods means k-1 lost). Only exact
    with device stamps; with host stamps a late read can pass for a loss."""
    t = np.asarray(ts, dtype=np.float64)
    if len(t) < 3:
        return {"frames": int(len(t)), "period_ms": None, "dropped": 0}
    dt = np.diff(t)
    period = float(np.median(dt))
    if period <= 0:
        return {"frames": int(len(t)), "period_ms": None, "dropped": 0}
    k = np.rint(dt / period)
    dropped = int(np.clip(k - 1, 0, None)[dt > 1.5 * period].sum())
    return {"frames": int(len(t)), "period_ms": round(period * 1000, 2),
            "dropped": dropped}


def save_take(take: Take, folder: Path) -> Path:
    """Write a Take as numbered JPEGs plus its frame times, for re-analysing
    the same recording later (the developer-only --keep-frames option; never
    reachable from the hub). The JPEG bytes are written as recorded, so a
    re-analysis sees exactly the frames the first one did."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for i, buf in enumerate(take.jpeg):
        (folder / f"{i:05d}.jpg").write_bytes(bytes(buf))
    (folder / "take.json").write_text(json.dumps({
        "tag": take.tag, "t": take.t, "device_clock": take.device_clock,
        "overflow": take.overflow}), "utf-8")
    return folder


def load_take(folder: Path) -> Take:
    """The inverse of save_take()."""
    folder = Path(folder)
    meta = json.loads((folder / "take.json").read_text("utf-8"))
    take = Take(meta.get("tag", folder.name), device_clock=bool(meta.get("device_clock")),
                overflow=bool(meta.get("overflow")))
    take.t = list(meta["t"])
    take.jpeg = [np.frombuffer((folder / f"{i:05d}.jpg").read_bytes(), np.uint8)
                 for i in range(len(take.t))]
    take.closed = True
    return take
