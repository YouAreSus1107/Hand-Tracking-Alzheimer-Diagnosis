"""
Spiral Tracing Test for Early Alzheimer's Screening
=====================================================
Measures motor smoothness and spatial accuracy by asking the patient to
trace an Archimedes spiral with their index fingertip in the air.

Metrics computed:
  Path Deviation  -- mean distance from fingertip to nearest spiral point (px)
  Velocity CV%    -- coefficient of variation of frame-to-frame velocity
  Norm. Jerk      -- normalized mean squared jerk (smoothness, lower = better)
  Completion %    -- fraction of spiral points the fingertip passed near
  Active Ratio    -- fraction of frames with fingertip actively moving

Reference: Kachouri et al. (2021), Schroter et al. (2003),
           Namkoong & Roh (2024), Technology and Health Care 32(S1):253-264

Run:  python spiral_test.py
Quit: press 'q'
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import math
import threading
import winsound
import struct
import io
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core"))
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

from hand_utils import (
    HAND_CONNECTIONS, make_landmark_filters, smooth_landmarks,
    preprocess_for_mediapipe,
)

# ── MediaPipe Setup ───────────────────────────────────────────────────────
BaseOptions           = mp.tasks.BaseOptions
HandLandmarker        = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode     = mp.tasks.vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=1,
    min_hand_detection_confidence=0.6,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.55,
)
landmarker = HandLandmarker.create_from_options(options)

# ── Test Configuration ────────────────────────────────────────────────────
RECORDING_DURATION = 40       # scored seconds
WARMUP_DURATION    = 8        # unscored practice seconds
COUNTDOWN_FROM     = 3

# Spiral geometry
SPIRAL_TURNS       = 3.5
SPIRAL_NUM_POINTS  = 1200
SPIRAL_LINE_THICK  = 3

# Guide dot
GUIDE_DOT_RADIUS   = 12

# Fingertip proximity thresholds (pixels)
FINGERTIP_IDX      = 8        # MediaPipe landmark: index fingertip
CLOSE_THRESHOLD    = 30       # "on track"
FAR_THRESHOLD      = 60       # "drifting"

# Velocity idle threshold (px/s)
IDLE_VEL_THRESHOLD = 15.0

# Scoring thresholds -- path deviation (pixels)
DEV_NORMAL         = 30.0
DEV_CONCERN        = 50.0

# Scoring thresholds -- velocity coefficient of variation (%)
VEL_CV_NORMAL      = 25.0
VEL_CV_CONCERN     = 40.0

# Scoring thresholds -- completion ratio
COMPLETION_GOOD    = 0.80
COMPLETION_MOD     = 0.50

MIN_FRAMES         = 30       # minimum data frames to compute metrics

# ── Colors (BGR) ──────────────────────────────────────────────────────────
WHITE     = (255, 255, 255)
GREEN     = (80,  210,  80)
RED       = (60,   60, 220)
ORANGE    = (30,  160, 255)
YELLOW    = (20,  210, 255)
GRAY      = (160, 160, 160)
DARK      = (25,   25,  25)
BTN_BLUE  = (180, 100,  40)
BTN_HOVER = (220, 140,  70)
BTN_GREEN = (60,  160,  60)

# ── States ────────────────────────────────────────────────────────────────
IDLE = "idle"; INSTRUCTION = "instruction"; COUNTDOWN = "countdown"
WARMUP = "warmup"; RECORDING = "recording"; COMPLETE = "complete"

# ── Mutable State ─────────────────────────────────────────────────────────
state            = IDLE
recording_start  = None
countdown_start  = None
warmup_start     = None

# Spiral data (populated on first frame)
spiral_points    = []          # list of (x, y) pixel coords
spiral_np        = None        # numpy (N, 2) array for fast lookups
spiral_center    = (0, 0)
warmup_points    = []          # circle for warmup
warmup_np        = None
spiral_initialized = False

# Recording data
frame_data       = []          # list of dicts: {t, fx, fy, dev, vel}
guide_index      = 0

# Previous fingertip for velocity
_prev_tip_x      = None
_prev_tip_y      = None
_prev_tip_t      = None

# Results
res_mean_dev     = None
res_vel_mean     = None
res_vel_sd       = None
res_vel_cv       = None
res_norm_jerk    = None
res_completion   = None
res_active_ratio = None

# Landmark smoothing
_lm_filters_x, _lm_filters_y = make_landmark_filters()

# Mouse / button
mouse_x = 0; mouse_y = 0; btn_pressed = False
BTN_W = 155; BTN_H = 46; BTN_MARGIN = 18


# ── UI Helpers ────────────────────────────────────────────────────────────

def mouse_callback(event, x, y, flags, param):
    global mouse_x, mouse_y, btn_pressed
    mouse_x, mouse_y = x, y
    if event == cv2.EVENT_LBUTTONDOWN:
        btn_pressed = True

def get_btn_rect(fw, fh):
    return (fw - BTN_W - BTN_MARGIN, BTN_MARGIN, BTN_W, BTN_H)

def in_rect(px, py, rect):
    x, y, w, h = rect
    return x <= px <= x + w and y <= py <= y + h

def draw_button(frame, rect, label, hovered, color=None):
    x, y, w, h = rect
    bg = BTN_HOVER if hovered else (color or BTN_BLUE)
    cv2.rectangle(frame, (x, y), (x+w, y+h), bg, -1)
    cv2.rectangle(frame, (x, y), (x+w, y+h), WHITE, 2)
    ts, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.putText(frame, label,
                (x+(w-ts[0])//2, y+(h+ts[1])//2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 2)

def dark_panel(frame, x, y, w, h, alpha=0.72):
    y1, y2 = max(0, y), min(frame.shape[0], y + h)
    x1, x2 = max(0, x), min(frame.shape[1], x + w)
    if y2 <= y1 or x2 <= x1:
        return
    roi = frame[y1:y2, x1:x2]
    bg  = np.zeros_like(roi)
    cv2.addWeighted(bg, alpha, roi, 1 - alpha, 0, roi)
    frame[y1:y2, x1:x2] = roi

def ctext(frame, text, cy, scale=0.7, color=WHITE, thickness=2):
    fw = frame.shape[1]
    ts, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    cv2.putText(frame, text, (max(0, (fw - ts[0]) // 2), cy),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)

def draw_hand(frame, landmarks, fh, fw):
    sk  = (80, 210, 80)
    dot = (60,  60, 220)
    tip_col = (20, 210, 255)
    for a, b in HAND_CONNECTIONS:
        p1, p2 = landmarks[a], landmarks[b]
        cv2.line(frame, (int(p1[0]*fw), int(p1[1]*fh)),
                        (int(p2[0]*fw), int(p2[1]*fh)), sk, 2)
    for i, lm in enumerate(landmarks):
        is_tip = i in (4, 8)
        cv2.circle(frame, (int(lm[0]*fw), int(lm[1]*fh)),
                   7 if is_tip else 4, tip_col if is_tip else dot, -1)


# ── Beep (reused from iiv_test.py pattern) ────────────────────────────────

def _build_beep_wav(freq=880, duration_ms=150, sample_rate=44100):
    n       = int(sample_rate * duration_ms / 1000)
    fade_n  = int(sample_rate * 0.005)
    samples = []
    for i in range(n):
        t    = i / sample_rate
        fade = min(i, n - i, fade_n) / fade_n
        samples.append(int(32767 * 0.9 * fade * math.sin(2 * math.pi * freq * t)))
    data = struct.pack(f'<{n}h', *samples)
    buf  = io.BytesIO()
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + len(data)))
    buf.write(b'WAVE')
    buf.write(b'fmt ')
    buf.write(struct.pack('<I', 16))
    buf.write(struct.pack('<HHIIHH', 1, 1, sample_rate,
                          sample_rate * 2, 2, 16))
    buf.write(b'data')
    buf.write(struct.pack('<I', len(data)))
    buf.write(data)
    return buf.getvalue()

BEEP_WAV = _build_beep_wav()

def play_beep():
    winsound.PlaySound(BEEP_WAV, winsound.SND_MEMORY)


# ── Spiral Geometry ───────────────────────────────────────────────────────

def generate_spiral(cx, cy, b, turns, num_points):
    """Archimedes spiral: r = b * theta. Returns list of (x, y) int tuples."""
    max_theta = turns * 2 * math.pi
    points = []
    for i in range(num_points):
        theta = max_theta * i / (num_points - 1)
        r     = b * theta
        x     = cx + r * math.cos(theta)
        y     = cy - r * math.sin(theta)
        points.append((int(round(x)), int(round(y))))
    return points


def generate_warmup_circle(cx, cy, radius, num_points=400):
    """Simple circle for the warmup phase."""
    points = []
    for i in range(num_points):
        theta = 2 * math.pi * i / (num_points - 1)
        x = cx + radius * math.cos(theta)
        y = cy - radius * math.sin(theta)
        points.append((int(round(x)), int(round(y))))
    return points


def scale_spiral_to_frame(fw, fh):
    """Generate spiral + warmup circle sized to fit the viewport."""
    cx, cy   = fw // 2, fh // 2
    max_r    = 0.4 * min(fw, fh)                   # 80% of half the smaller dim
    max_theta = SPIRAL_TURNS * 2 * math.pi
    b        = max_r / max_theta
    pts      = generate_spiral(cx, cy, b, SPIRAL_TURNS, SPIRAL_NUM_POINTS)
    warmup   = generate_warmup_circle(cx, cy, max_r * 0.35, 400)
    return pts, warmup, (cx, cy)


def draw_spiral_overlay(frame, points, color=(120, 120, 120), thickness=SPIRAL_LINE_THICK, alpha=0.45):
    """Draw the spiral as a semi-transparent polyline."""
    overlay = frame.copy()
    pts_arr = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(overlay, [pts_arr], isClosed=False, color=color, thickness=thickness, lineType=cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def nearest_spiral_point(fx, fy, sp_np):
    """Return (index, distance, nearest_x, nearest_y) for the closest spiral point."""
    diffs = sp_np - np.array([fx, fy], dtype=np.float32)
    dists = np.sqrt(np.sum(diffs * diffs, axis=1))
    idx   = int(np.argmin(dists))
    return idx, float(dists[idx]), int(sp_np[idx, 0]), int(sp_np[idx, 1])


# ── Metric Computation ────────────────────────────────────────────────────

def compute_path_deviation(fdata):
    devs = [fd['dev'] for fd in fdata]
    return np.mean(devs) if devs else 0.0


def compute_velocity_stats(fdata):
    vels = [fd['vel'] for fd in fdata if fd['vel'] is not None]
    if len(vels) < 2:
        return None, None, None
    mean_v = np.mean(vels)
    sd_v   = np.std(vels, ddof=1)
    cv_v   = (sd_v / mean_v * 100) if mean_v > 0 else 0.0
    return float(mean_v), float(sd_v), float(cv_v)


def compute_mean_squared_jerk(fdata):
    """Normalized mean squared jerk from finite differences of velocity."""
    entries = [(fd['t'], fd['vel']) for fd in fdata if fd['vel'] is not None]
    if len(entries) < 4:
        return None
    ts   = np.array([e[0] for e in entries])
    vels = np.array([e[1] for e in entries])
    dt   = np.diff(ts)
    dt   = np.where(dt < 1e-6, 1e-6, dt)

    acc  = np.diff(vels) / dt
    if len(acc) < 2:
        return None
    dt2  = dt[1:]
    jerk = np.diff(acc) / dt2
    msj  = float(np.mean(jerk ** 2))

    # Normalize: MSJ * duration^5 / path_length^2
    duration    = ts[-1] - ts[0]
    path_length = float(np.sum(vels[:-1] * dt))
    path_length = max(path_length, 1.0)
    normalized  = msj * (duration ** 5) / (path_length ** 2)
    return normalized


def compute_completion(fdata, sp_np, threshold=CLOSE_THRESHOLD):
    """Fraction of spiral points visited (fingertip came within threshold)."""
    n = len(sp_np)
    visited = np.zeros(n, dtype=bool)
    for fd in fdata:
        fx, fy = fd['fx'], fd['fy']
        diffs  = sp_np - np.array([fx, fy], dtype=np.float32)
        dists  = np.sqrt(np.sum(diffs * diffs, axis=1))
        close  = dists < threshold
        visited |= close
    return float(np.sum(visited) / n) if n > 0 else 0.0


def compute_active_ratio(fdata, threshold=IDLE_VEL_THRESHOLD):
    vels = [fd['vel'] for fd in fdata if fd['vel'] is not None]
    if not vels:
        return 0.0
    active = sum(1 for v in vels if v > threshold)
    return active / len(vels)


def deviation_label(mean_dev):
    if mean_dev < DEV_NORMAL:
        return "Within typical range", GREEN
    elif mean_dev < DEV_CONCERN:
        return "Mild deviation - consider monitoring", ORANGE
    else:
        return "Elevated deviation - recommend follow-up", RED


def velocity_label(cv_pct):
    if cv_pct < VEL_CV_NORMAL:
        return "Smooth, consistent tracing", GREEN
    elif cv_pct < VEL_CV_CONCERN:
        return "Moderate speed variability", ORANGE
    else:
        return "Irregular speed - recommend follow-up", RED


def completion_label(ratio):
    if ratio >= COMPLETION_GOOD:
        return "Good spiral coverage", GREEN
    elif ratio >= COMPLETION_MOD:
        return "Moderate coverage - some sections missed", ORANGE
    else:
        return "Low coverage - difficulty following path", RED


# ── Camera ────────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[ERROR] Could not open camera.")
    exit(1)

WIN = "Spiral Tracing Test  |  Q to quit"
cv2.namedWindow(WIN)
cv2.setMouseCallback(WIN, mouse_callback)

print("=" * 52)
print("  Spiral Tracing Test")
print("  Click 'Start Test' in the camera window.")
print("  Press Q to quit.")
print("=" * 52)

# ── Main Loop ─────────────────────────────────────────────────────────────
while cap.isOpened():

    ok, frame = cap.read()
    if not ok:
        continue

    frame = cv2.flip(frame, 1)
    fh, fw = frame.shape[:2]

    now      = time.time()
    btn_rect = get_btn_rect(fw, fh)
    hovered  = in_rect(mouse_x, mouse_y, btn_rect)
    clicked  = btn_pressed and hovered
    btn_pressed = False

    # ── First-frame spiral generation ─────────────────────────────────────
    if not spiral_initialized:
        spiral_points, warmup_points, spiral_center = scale_spiral_to_frame(fw, fh)
        spiral_np  = np.array(spiral_points, dtype=np.float32)
        warmup_np  = np.array(warmup_points, dtype=np.float32)
        spiral_initialized = True

    # ── MediaPipe ─────────────────────────────────────────────────────────
    rgb    = preprocess_for_mediapipe(frame)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_img, int(now * 1000))
    hand_visible = bool(result.hand_landmarks)

    landmarks = None
    if hand_visible:
        landmarks = smooth_landmarks(
            result.hand_landmarks[0], _lm_filters_x, _lm_filters_y, now
        )

    # ── Draw hand skeleton ────────────────────────────────────────────────
    if hand_visible and landmarks is not None:
        draw_hand(frame, landmarks, fh, fw)

    # ══════════════════════════════════════════════════════════════════════
    # IDLE
    # ══════════════════════════════════════════════════════════════════════
    if state == IDLE:
        dark_panel(frame, fw//2-235, fh//2-75, 470, 128)
        ctext(frame, "Spiral Tracing Test",          fh//2-44, scale=0.85)
        ctext(frame, "Measures motor smoothness -- a biomarker linked to",
              fh//2-10, scale=0.50, color=GRAY)
        ctext(frame, "early cognitive decline  (Alzheimer's research).",
              fh//2+14, scale=0.50, color=GRAY)
        ctext(frame, "Press  'Start Test'  to begin.",
              fh//2+42, scale=0.52, color=YELLOW)
        draw_button(frame, btn_rect, "Start Test", hovered)
        if clicked:
            state = INSTRUCTION

    # ══════════════════════════════════════════════════════════════════════
    # INSTRUCTION
    # ══════════════════════════════════════════════════════════════════════
    elif state == INSTRUCTION:
        dark_panel(frame, 28, fh//2-165, fw-56, 320, alpha=0.84)
        ctext(frame, "Your Task", fh//2-140, scale=1.0, color=YELLOW, thickness=2)
        lines = [
            ("Using your PREFERRED hand:",                                WHITE),
            ("",                                                          WHITE),
            ("A SPIRAL will appear on screen with a moving",             WHITE),
            ("YELLOW DOT.  Trace the spiral by keeping your",            WHITE),
            ("INDEX FINGERTIP near the dot as it moves.",                WHITE),
            ("",                                                          WHITE),
            ("Move smoothly and continuously.",                           GRAY),
            ("Stay as close to the spiral line as you can.",             GRAY),
            ("",                                                          WHITE),
            (f"{WARMUP_DURATION}s practice, then {RECORDING_DURATION}s scored test.", YELLOW),
        ]
        for i, (line, col) in enumerate(lines):
            ctext(frame, line, fh//2-88 + i*28, scale=0.57, color=col)
        draw_button(frame, btn_rect, "I'm Ready", hovered, color=BTN_GREEN)
        if clicked:
            state = COUNTDOWN; countdown_start = now

    # ══════════════════════════════════════════════════════════════════════
    # COUNTDOWN
    # ══════════════════════════════════════════════════════════════════════
    elif state == COUNTDOWN:
        elapsed   = now - countdown_start
        remaining = COUNTDOWN_FROM - int(elapsed)
        if remaining > 0:
            ctext(frame, "Get ready...", fh//2-70, scale=0.85, color=YELLOW)
            ctext(frame, str(remaining), fh//2+55, scale=4.5, color=WHITE, thickness=8)
        else:
            state = WARMUP; warmup_start = now

    # ══════════════════════════════════════════════════════════════════════
    # WARMUP
    # ══════════════════════════════════════════════════════════════════════
    elif state == WARMUP:
        elapsed   = now - warmup_start
        remaining = WARMUP_DURATION - elapsed

        if remaining <= 0:
            # Transition to RECORDING
            state = RECORDING; recording_start = now
            frame_data = []; guide_index = 0
            _prev_tip_x = None; _prev_tip_y = None; _prev_tip_t = None
            # Reset filters
            _new_x, _new_y = make_landmark_filters()
            _lm_filters_x[:] = _new_x
            _lm_filters_y[:] = _new_y
            threading.Thread(target=play_beep, daemon=True).start()
        else:
            # Draw warmup circle
            draw_spiral_overlay(frame, warmup_points, color=(140, 140, 100), thickness=3, alpha=0.40)

            # Guide dot around circle
            wu_idx = int((elapsed / WARMUP_DURATION) * len(warmup_points)) % len(warmup_points)
            gx, gy = warmup_points[wu_idx]
            cv2.circle(frame, (gx, gy), GUIDE_DOT_RADIUS, YELLOW, -1)
            cv2.circle(frame, (gx, gy), GUIDE_DOT_RADIUS + 2, WHITE, 2)

            # Fingertip proximity feedback during warmup
            if hand_visible and landmarks is not None:
                tip_x = int(landmarks[FINGERTIP_IDX][0] * fw)
                tip_y = int(landmarks[FINGERTIP_IDX][1] * fh)
                _, dev, nx, ny = nearest_spiral_point(tip_x, tip_y, warmup_np)
                if dev < CLOSE_THRESHOLD:
                    tip_col = GREEN
                elif dev < FAR_THRESHOLD:
                    tip_col = ORANGE
                else:
                    tip_col = RED
                cv2.line(frame, (tip_x, tip_y), (nx, ny), tip_col, 1, cv2.LINE_AA)
                cv2.circle(frame, (tip_x, tip_y), 8, tip_col, -1)

            # Progress bar
            bar_x, bar_y, bar_w = 20, fh-28, fw-40
            filled = int(bar_w * (elapsed / WARMUP_DURATION))
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), DARK, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+filled, bar_y+14), ORANGE, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), GRAY, 1)

            dark_panel(frame, fw//2-250, fh//2-58, 500, 116, alpha=0.74)
            ctext(frame, "WARM UP -- practice, no data recorded",
                  fh//2-28, scale=0.75, color=ORANGE, thickness=2)
            ctext(frame, "Follow the yellow dot around the circle.",
                  fh//2+10, scale=0.58, color=GRAY)
            ctext(frame, f"Scored test begins in  {remaining:.1f}s",
                  fh//2+42, scale=0.65, color=WHITE)
            if not hand_visible:
                ctext(frame, "No hand detected -- show your hand",
                      fh//2+75, scale=0.55, color=ORANGE)

    # ══════════════════════════════════════════════════════════════════════
    # RECORDING
    # ══════════════════════════════════════════════════════════════════════
    elif state == RECORDING:
        elapsed   = now - recording_start
        remaining = RECORDING_DURATION - elapsed

        if remaining <= 0:
            # ── Compute results ────────────────────────────────────────
            threading.Thread(target=play_beep, daemon=True).start()

            if len(frame_data) >= MIN_FRAMES:
                res_mean_dev  = compute_path_deviation(frame_data)
                res_vel_mean, res_vel_sd, res_vel_cv = compute_velocity_stats(frame_data)
                res_norm_jerk = compute_mean_squared_jerk(frame_data)
                res_completion = compute_completion(frame_data, spiral_np)
                res_active_ratio = compute_active_ratio(frame_data)
            else:
                res_mean_dev = None
            state = COMPLETE

        else:
            # Draw reference spiral
            draw_spiral_overlay(frame, spiral_points, color=(120, 120, 120),
                                thickness=SPIRAL_LINE_THICK, alpha=0.45)

            # Advance guide dot
            guide_index = min(int((elapsed / RECORDING_DURATION) * SPIRAL_NUM_POINTS),
                              SPIRAL_NUM_POINTS - 1)
            gx, gy = spiral_points[guide_index]
            cv2.circle(frame, (gx, gy), GUIDE_DOT_RADIUS, YELLOW, -1)
            cv2.circle(frame, (gx, gy), GUIDE_DOT_RADIUS + 2, WHITE, 2)

            # Draw traced portion of spiral (from start to guide) in brighter color
            if guide_index > 1:
                traced = np.array(spiral_points[:guide_index+1], dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(frame, [traced], isClosed=False, color=(160, 160, 60), thickness=2, lineType=cv2.LINE_AA)

            # ── Fingertip tracking ────────────────────────────────────
            if hand_visible and landmarks is not None:
                tip_x = int(landmarks[FINGERTIP_IDX][0] * fw)
                tip_y = int(landmarks[FINGERTIP_IDX][1] * fh)
                _, dev, nx, ny = nearest_spiral_point(tip_x, tip_y, spiral_np)

                # Color by proximity
                if dev < CLOSE_THRESHOLD:
                    tip_col = GREEN
                elif dev < FAR_THRESHOLD:
                    tip_col = ORANGE
                else:
                    tip_col = RED
                cv2.line(frame, (tip_x, tip_y), (nx, ny), tip_col, 1, cv2.LINE_AA)
                cv2.circle(frame, (tip_x, tip_y), 8, tip_col, -1)

                # Velocity
                vel = None
                if _prev_tip_x is not None and _prev_tip_t is not None:
                    dt = now - _prev_tip_t
                    if dt > 0.2:
                        # Gap from hand loss — reset, don't spike
                        vel = None
                    elif dt > 1e-6:
                        vel = math.hypot(tip_x - _prev_tip_x, tip_y - _prev_tip_y) / dt
                _prev_tip_x = tip_x
                _prev_tip_y = tip_y
                _prev_tip_t = now

                frame_data.append({
                    't':   now,
                    'fx':  tip_x,
                    'fy':  tip_y,
                    'dev': dev,
                    'vel': vel,
                })
            else:
                # Hand not visible — reset velocity tracking
                _prev_tip_x = None; _prev_tip_y = None; _prev_tip_t = None

            # Progress bar (green)
            bar_x, bar_y, bar_w = 20, fh-28, fw-40
            filled = int(bar_w * (elapsed / RECORDING_DURATION))
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), DARK, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+filled, bar_y+14), GREEN, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), GRAY, 1)

            # Live stats
            dark_panel(frame, 10, 10, 250, 75)
            cv2.putText(frame, f"Time left:  {remaining:.1f}s",
                        (22, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, WHITE, 2)
            if frame_data:
                avg_dev = np.mean([fd['dev'] for fd in frame_data])
                cv2.putText(frame, f"Avg deviation: {avg_dev:.0f} px",
                            (22, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.60, GREEN, 2)

            if not hand_visible:
                dark_panel(frame, fw//2-185, fh//2-28, 370, 56)
                ctext(frame, "No hand detected -- show your hand",
                      fh//2+8, scale=0.6, color=ORANGE)

    # ══════════════════════════════════════════════════════════════════════
    # COMPLETE
    # ══════════════════════════════════════════════════════════════════════
    elif state == COMPLETE:
        dark_panel(frame, 28, 42, fw-56, fh-84, alpha=0.90)

        ctext(frame, "Test Complete -- Spiral Tracing Results",
              90, scale=0.82, color=YELLOW, thickness=2)

        if res_mean_dev is not None:
            n_frames = len(frame_data)
            ctext(frame, f"Data frames: {n_frames}",
                  120, scale=0.50, color=GRAY)

            # ── Path Deviation (primary metric) ───────────────────────
            dev_lbl, dev_col = deviation_label(res_mean_dev)
            ctext(frame, f"Path Deviation:  {res_mean_dev:.1f} px",
                  160, scale=0.88, color=dev_col, thickness=2)
            ctext(frame, dev_lbl, 190, scale=0.58, color=dev_col)

            # ── Velocity CV ───────────────────────────────────────────
            if res_vel_cv is not None:
                vel_lbl, vel_col = velocity_label(res_vel_cv)
                ctext(frame, f"Velocity CV:  {res_vel_cv:.1f}%   (mean {res_vel_mean:.0f} px/s,  SD {res_vel_sd:.0f})",
                      230, scale=0.55, color=vel_col)
                ctext(frame, vel_lbl, 255, scale=0.50, color=vel_col)

            # ── Completion ────────────────────────────────────────────
            if res_completion is not None:
                comp_lbl, comp_col = completion_label(res_completion)
                ctext(frame, f"Completion:  {res_completion*100:.0f}%",
                      290, scale=0.65, color=comp_col)
                ctext(frame, comp_lbl, 315, scale=0.50, color=comp_col)

            # ── Jerk (informational) ──────────────────────────────────
            if res_norm_jerk is not None:
                ctext(frame, f"Normalised jerk:  {res_norm_jerk:.2e}   (lower = smoother)",
                      345, scale=0.45, color=GRAY, thickness=1)

            # ── Active ratio (informational) ──────────────────────────
            if res_active_ratio is not None:
                ctext(frame, f"Active ratio:  {res_active_ratio*100:.0f}%   (time spent moving)",
                      370, scale=0.45, color=GRAY, thickness=1)

            ctext(frame, "-" * 58, 398, scale=0.37, color=GRAY, thickness=1)
            ctext(frame, "Ref: Kachouri (2021), Schroter (2003). Deviation <30 px normal | 30-50 mild | >50 elevated",
                  418, scale=0.36, color=GRAY, thickness=1)
            ctext(frame, "Not a medical diagnosis. Consult a healthcare professional.",
                  440, scale=0.40, color=GRAY, thickness=1)
        else:
            ctext(frame, f"Not enough data frames ({len(frame_data)} < {MIN_FRAMES}).",
                  200, scale=0.68, color=ORANGE)
            ctext(frame, "Ensure your hand is visible during the test. Try again.",
                  234, scale=0.58, color=GRAY)

        draw_button(frame, btn_rect, "Try Again", hovered)
        if clicked:
            state = IDLE
            frame_data = []; guide_index = 0
            _prev_tip_x = None; _prev_tip_y = None; _prev_tip_t = None
            res_mean_dev = res_vel_mean = res_vel_sd = res_vel_cv = None
            res_norm_jerk = res_completion = res_active_ratio = None

    # ── Render ────────────────────────────────────────────────────────────
    cv2.imshow(WIN, frame)
    if cv2.waitKey(5) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
landmarker.close()
print("\n[INFO] Spiral tracing test closed.")
