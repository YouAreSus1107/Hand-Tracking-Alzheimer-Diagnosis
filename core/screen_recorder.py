"""Press R to record what a test window shows into recordings/<test>_<time>.mp4.

Records the composed frame exactly as displayed (camera + overlay), not the raw
camera, so a clip shows what the person was looking at. Encoding runs on its
own thread so a CPU-bound test loop only pays for a queue put. The loops run at
whatever rate the machine manages, so frames are placed on a fixed FPS grid by
wall-clock time (repeated or dropped as needed) and the clip plays back in real
time. No audio. The only on-screen sign is a small red dot, top-right, drawn on
the displayed copy and never into the file.
"""

import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

REC_DIR = Path(__file__).resolve().parent.parent / "recordings"
FPS = 30.0
KEYS = (ord("r"), ord("R"))


class ScreenRecorder:
    def __init__(self, name: str):
        self.name = name
        self._q = None
        self._thread = None
        self.path = None

    @property
    def active(self) -> bool:
        return self._thread is not None

    def key(self, key: int) -> None:
        """Feed the loop's waitKey result; R toggles recording."""
        if key in KEYS:
            self.stop() if self.active else self.start()

    def start(self) -> None:
        REC_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = REC_DIR / f"{self.name}_{stamp}.mp4"
        self._q = queue.Queue(maxsize=90)
        self._thread = threading.Thread(target=self._run, args=(self._q, self.path),
                                        daemon=True)
        self._thread.start()
        print(f"[REC] Recording to {self.path}")

    def stop(self) -> None:
        if not self.active:
            return
        self._q.put(None)
        self._thread.join(timeout=10)
        self._thread = self._q = None
        print(f"[REC] Saved {self.path}")

    close = stop

    def frame(self, img):
        """Queue img if recording; return the image to display."""
        if not self.active:
            return img
        try:
            self._q.put_nowait((time.perf_counter(), img))
        except queue.Full:          # encoder behind: drop, the grid repeats the last frame
            pass
        shown = img.copy()
        w = shown.shape[1]
        cv2.circle(shown, (w - 14, 14), 5, (40, 40, 230), -1, cv2.LINE_AA)
        return shown

    @staticmethod
    def _run(q, path):
        writer = None
        size = None
        t0 = None
        written = 0
        last = None
        while True:
            item = q.get()
            if item is None:
                break
            t, img = item
            if writer is None:
                size = (img.shape[1], img.shape[0])
                writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                                         FPS, size)
                if not writer.isOpened():
                    print(f"[REC] Could not open a video writer for {path}")
                    # keep draining so the test loop never blocks
                    while q.get() is not None:
                        pass
                    return
                t0 = t
            if (img.shape[1], img.shape[0]) != size:
                img = cv2.resize(img, size)
            due = int((t - t0) * FPS) + 1   # frames that should exist by time t
            if last is not None:
                while written < due - 1:    # fill the gap with the previous frame
                    writer.write(last)
                    written += 1
            if written < due:
                writer.write(img)
                written += 1
            last = img
        if writer is not None:
            writer.release()
