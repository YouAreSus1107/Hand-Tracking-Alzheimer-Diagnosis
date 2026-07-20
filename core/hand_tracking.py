"""
Hand Tracking / UDP Broadcast
=============================
Uses OpenCV + MediaPipe Tasks API to detect hand landmarks from webcam,
draws the skeleton overlay, and broadcasts the 21 landmark positions
(x, y, z) per hand over UDP to 127.0.0.1:5052 for any downstream consumer.
"""

import cv2
import mediapipe as mp
import socket
import time
from pathlib import Path
from hand_utils import HAND_CONNECTIONS, make_landmark_filters, smooth_landmarks, preprocess_for_mediapipe

MODEL_PATH = str(Path(__file__).resolve().parents[1] / "model" / "hand_landmarker.task")

# ── UDP Setup ──────────────────────────────────────────────
UDP_IP = "127.0.0.1"
UDP_PORT = 5052
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ── MediaPipe Tasks API Setup ─────────────────────────────
# In modern MediaPipe (0.10+), especially on Python 3.12+, the old 'solutions'
# API may be omitted. We use the robust Tasks API instead.
BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.VIDEO,  # VIDEO mode tracks between frames
    num_hands=2,
    min_hand_detection_confidence=0.6,    # raised: requires clearer initial detection
    min_hand_presence_confidence=0.5,     # raised: drops low-confidence tracking frames
    min_tracking_confidence=0.65,         # raised: re-detects sooner when occluded
)

landmarker = HandLandmarker.create_from_options(options)

# Per-hand One-Euro filter sets (separate filters for left/right hand)
_lm_filters: dict[str, tuple] = {
    'L': make_landmark_filters(),
    'R': make_landmark_filters(),
}

# ── Webcam Setup ──────────────────────────────────────────
print("\n--- Camera Selection ---")
print("1. Default Laptop/USB Camera")
print("2. Phone Camera (via IP Webcam app or similar)")
choice = input("Enter 1 or 2 [Default 1]: ").strip()

if choice == "2":
    print("\nTo use your phone, install an app like 'IP Webcam' (Android).")
    print("Ensure your phone and computer are on the SAME Wi-Fi network.")
    source = input("Enter the video stream URL (e.g., http://192.168.1.5:8080/video): ").strip()
else:
    source = 0

cap = cv2.VideoCapture(source)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

if not cap.isOpened():
    print(f"[ERROR] Could not open camera source: {source}. Please check your connection.")
    exit(1)

print("=" * 50)
print("  Hand Detection 3D - Python Tracker (Modern API)")
print("=" * 50)
print(f"  Sending UDP data to {UDP_IP}:{UDP_PORT}")
print("  Press 'q' to quit")
print("=" * 50)

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("[WARNING] Ignoring empty camera frame.")
        continue

    h, w, c = frame.shape

    # Preprocess for better detection under varied lighting
    rgb_frame    = preprocess_for_mediapipe(frame)
    mp_image     = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    # VIDEO mode requires a monotonically increasing timestamp in milliseconds
    timestamp_ms  = int(time.time() * 1000)
    timestamp_sec = timestamp_ms / 1000.0
    result = landmarker.detect_for_video(mp_image, timestamp_ms)

    if result.hand_landmarks:
        for i, hand_landmarks in enumerate(result.hand_landmarks):
            side = result.handedness[i][0].category_name[0]   # "L" or "R"
            filters_x, filters_y = _lm_filters[side]
            smoothed = smooth_landmarks(hand_landmarks, filters_x, filters_y, timestamp_sec)

            for connection in HAND_CONNECTIONS:
                p1 = smoothed[connection[0]]
                p2 = smoothed[connection[1]]
                cv2.line(frame,
                         (int(p1[0] * w), int(p1[1] * h)),
                         (int(p2[0] * w), int(p2[1] * h)),
                         (0, 255, 0), 2)
            for lm in smoothed:
                cv2.circle(frame, (int(lm[0] * w), int(lm[1] * h)), 4, (0, 0, 255), -1)

            landmark_list = []
            for lm in smoothed:
                landmark_list.extend([int(lm[0] * w), int(lm[1] * h), int(lm[2] * w)])
            data_string = side + ":[" + ",".join(str(v) for v in landmark_list) + "]"
            sock.sendto(data_string.encode('utf-8'), (UDP_IP, UDP_PORT))

    cv2.imshow("Hand Detection 3D - Press 'q' to quit", frame)

    if cv2.waitKey(5) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()
sock.close()
landmarker.close()
print("\n[INFO] Hand tracking stopped. Goodbye!")
