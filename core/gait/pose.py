"""
Pose tracker for the walking test: MediaPipe PoseLandmarker (Tasks API, VIDEO
mode), one person. Returns RAW image landmarks in pixels plus per-joint
visibility; every metric reads these. Smoothing, if any, is for drawing only
(GAIT_TEST_PLAN.md §6.1).

Imports mediapipe, so it is the one module in core/gait that the unit tests do
not load.
"""

from __future__ import annotations

from pathlib import Path

from core import quiet            # keep above mediapipe: silences its startup log
import mediapipe as mp

MODEL_DIR = Path(__file__).resolve().parents[2] / "model"
MODEL_LITE = MODEL_DIR / "pose_landmarker_lite.task"


class PoseTracker:
    def __init__(self, model_path: Path = MODEL_LITE):
        if not Path(model_path).is_file():
            raise FileNotFoundError(
                f"{model_path.name} is missing - run install.py to download it")
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        with quiet.muted_native_stderr():
            self.landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self._last_ms = -1

    def detect(self, rgb, t_s: float, size: tuple[int, int]):
        """(points_px, visibility) for the one person, or (None, None).

        `points_px` is 33 (x, y) in pixels of the frame given, so distances
        are true to the picture's aspect ratio; `size` is (width, height)."""
        ms = int(t_s * 1000)
        if ms <= self._last_ms:            # VIDEO mode needs rising timestamps
            ms = self._last_ms + 1
        self._last_ms = ms
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(img, ms)
        if not result.pose_landmarks:
            return None, None
        w, h = size
        lms = result.pose_landmarks[0]
        pts = [(lm.x * w, lm.y * h) for lm in lms]
        vis = [float(getattr(lm, "visibility", 1.0) or 0.0) for lm in lms]
        return pts, vis

    def close(self):
        self.landmarker.close()
