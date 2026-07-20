"""
IIV Finger Tapping Test
=======================
Measures two biomarkers linked to early Alzheimer's disease:

  IIV  -- Intra-Individual Variability of inter-tap intervals (rhythm consistency)
  Sync -- Std dev of tap-latency-after-beat  (beat-following consistency)

Paradigm: one beep every 3 seconds.  Tap ONCE anytime within that 3-second window.
The window is fully open -- no narrow "hit zone".  The first tap per window counts.

IIV is computed only from the one response tap per interval, so extra taps
within a window cannot distort the score.

Sync consistency is std dev of (tap_time - beat_time), i.e. how variable the
patient's reaction delay is -- NOT the mean delay (which is just reaction time
and is physiologically normal at 150-400 ms).

Reference: Namkoong & Roh (2024), Technology and Health Care 32(S1):253-264
           Suzumura et al. (2016/18/21), Roalf et al. (2018)

Run:  python iiv_test.py
Quit: press 'q'
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import math
import threading
import winsound   # Windows built-in, no extra install needed
import struct
import io
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core"))
MODEL_PATH = str(_REPO_ROOT / "model" / "hand_landmarker.task")

from hand_utils import HAND_CONNECTIONS, make_landmark_filters, smooth_landmarks, preprocess_for_mediapipe

# ── MediaPipe Setup ────────────────────────────────────────────────────────
BaseOptions           = mp.tasks.BaseOptions
HandLandmarker        = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode     = mp.tasks.vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.VIDEO,  # VIDEO mode: tracks between frames, stable landmarks
    num_hands=1,
    min_hand_detection_confidence=0.6,    # raised: requires clearer initial detection
    min_hand_presence_confidence=0.5,     # raised: drops low-confidence tracking frames
    min_tracking_confidence=0.55,         # raised: tighter tracking continuity
)
landmarker = HandLandmarker.create_from_options(options)

# ── Test Configuration ─────────────────────────────────────────────────────
RECORDING_DURATION = 30      # scored seconds
WARMUP_DURATION    = 5     # unscored practice seconds
COUNTDOWN_FROM     = 3

TAP_THRESHOLD      = 0.065   # normalised index-tip <-> thumb-tip distance = tap
TAP_DEBOUNCE       = 0.30    # min seconds between registered taps (anti-bounce)
                             # 300 ms is safe: minimum real ITI is ~3000 ms
DIST_EMA_ALPHA     = 0.4     # EMA smoothing on the distance scalar (second filter layer)

# Metronome: one beep every 1 seconds (~30 scored beats).
METRONOME_INTERVAL = 1.0     # seconds
METRONOME_FREQ     = 880     # Hz  (A5)
METRONOME_MS       = 150     # beep length in ms

# Fire the beep thread this many seconds EARLY to compensate for
# thread-startup + OS audio latency, so the audible click lands close to
# next_beat_time rather than perceptibly after it.
AUDIO_LEAD         = 0.200   # seconds  (tune up/down if still off)

MIN_RESPONSES      = 10       # need at least this many hit intervals for IIV

# How far BEFORE the scheduled beat time a tap can land and still count.
# The patient hears the beep AUDIO_LEAD seconds before the scheduled time,
# so their tap can arrive before the window would otherwise open.
# Adding 0.5 s of extra buffer covers fast reactors (~150 ms reaction time).
TAP_WINDOW_LEAD    = AUDIO_LEAD + 0.5   # seconds (= 0.62 s)

# IIV thresholds: Coefficient of Variation (IIV / mean_ITI * 100).
# CV is scale-invariant. At a 3 s interval, healthy adults naturally show
# higher absolute IIV than 1 Hz paradigms from the clinical literature.
# Thresholds are calibrated for this slower-paced paradigm:
IIV_CV_NORMAL  = 15.0   # CV% < 15  -> typical range for 3 s paced tapping
IIV_CV_CONCERN = 25.0   # CV% 15-25 -> mild; > 25 -> elevated

# ── Colors (BGR) ───────────────────────────────
WHITE  = (255, 255, 255)
GREEN  = (80,  210,  80)
RED    = (60,   60, 220)
ORANGE = (30,  160, 255)
YELLOW = (20,  210, 255)
GRAY   = (160, 160, 160)
DARK   = (25,   25,  25)
BTN_BLUE  = (180, 100, 40)
BTN_HOVER = (220, 140, 70)
BTN_GREEN = (60,  160, 60)

# ── States ─────────────────────────────────────────────────────────────────
IDLE = "idle"; INSTRUCTION = "instruction"; COUNTDOWN = "countdown"
WARMUP = "warmup"; RECORDING = "recording"; COMPLETE = "complete"

# ── Mutable State ──────────────────────────────────────────────────────────
state           = IDLE
tap_timestamps  = []    # every tap detected during RECORDING
beat_times      = []    # scheduled beat times during RECORDING
is_touching     = False
last_tap_time   = 0.0
flash_until     = 0.0
recording_start = None
countdown_start = None
warmup_start    = None
next_beat_time  = None
beep_fired      = False

# Results (populated on transition to COMPLETE)
res_hits        = 0
res_misses      = 0
res_iiv_ms      = None
res_mean_iti_ms = None
res_cv_pct      = None
res_mean_lat_ms = None   # mean reaction delay (informational)
res_sync_std_ms = None   # sync consistency (the real biomarker)
tap_count       = 0

# ── Landmark smoothing state ───────────────────────────────────────────────
_lm_filters_x, _lm_filters_y = make_landmark_filters()
_dist_ema: float | None = None   # EMA state for the thumb-index distance scalar

mouse_x = 0; mouse_y = 0; btn_pressed = False

BTN_W = 155; BTN_H = 46; BTN_MARGIN = 18


# ── UI Helpers ─────────────────────────────────────────────────────────────

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
    roi = frame[y:y+h, x:x+w]
    bg  = np.zeros_like(roi)
    cv2.addWeighted(bg, alpha, roi, 1-alpha, 0, roi)
    frame[y:y+h, x:x+w] = roi

def ctext(frame, text, cy, scale=0.7, color=WHITE, thickness=2):
    fw = frame.shape[1]
    ts, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    cv2.putText(frame, text, (max(0, (fw-ts[0])//2), cy),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)

def draw_hand(frame, landmarks, fh, fw, flash=False):
    """Draw skeleton from smoothed landmarks — expects list of (x, y, z) tuples."""
    sk  = (80, 255, 160) if flash else (80, 210, 80)
    tip = (20, 210, 255) if flash else RED
    dot = (60, 60, 220)
    for a, b in HAND_CONNECTIONS:
        p1, p2 = landmarks[a], landmarks[b]
        cv2.line(frame, (int(p1[0]*fw), int(p1[1]*fh)),
                        (int(p2[0]*fw), int(p2[1]*fh)), sk, 2)
    for i, lm in enumerate(landmarks):
        is_tip = i in (4, 8)
        cv2.circle(frame, (int(lm[0]*fw), int(lm[1]*fh)),
                   7 if is_tip else 4, tip if is_tip else dot, -1)

def _build_beep_wav(freq=METRONOME_FREQ, duration_ms=METRONOME_MS, sample_rate=44100):
    """
    Pre-generate a PCM WAV tone in memory.
    PlaySound(SND_MEMORY) routes through the normal audio mixer
    (same path as music/video) -- far more reliable than winsound.Beep()
    which uses the legacy system-beep device and can silently fail.
    """
    n       = int(sample_rate * duration_ms / 1000)
    fade_n  = int(sample_rate * 0.005)          # 5 ms fade in/out to avoid clicks
    samples = []
    for i in range(n):
        t    = i / sample_rate
        fade = min(i, n - i, fade_n) / fade_n   # ramp up then ramp down
        samples.append(int(32767 * 0.9 * fade * math.sin(2 * math.pi * freq * t)))
    data    = struct.pack(f'<{n}h', *samples)
    buf     = io.BytesIO()
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

BEEP_WAV = _build_beep_wav()      # generated once at startup

def play_beep():
    winsound.PlaySound(BEEP_WAV, winsound.SND_MEMORY)


# ── Metric Computation ─────────────────────────────────────────────────────

def analyze_responses(all_taps, beat_times_list):
    """
    Interval-based extraction: for each interval [beat_i, beat_i+1), find
    the FIRST tap. The last interval extends to recording_end implicitly.

    Returns:
      responses  -- list of (beat_time, tap_time, latency_ms) for each hit
      miss_count -- intervals with no tap at all
    """
    if not beat_times_list:
        return [], 0

    responses = []
    missed    = 0
    n = len(beat_times_list)

    for i, bt in enumerate(beat_times_list):
        # Shift window back by TAP_WINDOW_LEAD: the patient hears the beep
        # AUDIO_LEAD seconds before bt, so their tap can land before bt.
        window_start = bt - TAP_WINDOW_LEAD
        window_end   = (beat_times_list[i+1] if i+1 < n else bt + METRONOME_INTERVAL) - TAP_WINDOW_LEAD
        taps_in = [t for t in all_taps if window_start <= t < window_end]
        if taps_in:
            tap_t = min(taps_in)                      # first tap in this window
            responses.append((bt, tap_t, (tap_t - bt) * 1000))
        else:
            missed += 1

    return responses, missed


def compute_iiv(tap_timestamps):
    """
    Sample std dev (ddof=1) of ITI between consecutive raw taps.
    Double-interval gaps (caused by missed beats) are filtered out so a
    single missed beat cannot inflate IIV by ~6000 ms.
    Also returns mean ITI and CV% (scale-invariant measure).
    Requires at least MIN_RESPONSES tap timestamps.
    """
    if len(tap_timestamps) < MIN_RESPONSES:
        return None, None, None
    raw_iti  = [(tap_timestamps[i+1] - tap_timestamps[i]) * 1000
                for i in range(len(tap_timestamps)-1)]
    max_iti  = METRONOME_INTERVAL * 1000 * 1.5   # e.g. 4500 ms for 3 s interval
    iti      = [v for v in raw_iti if v <= max_iti]
    if len(iti) < MIN_RESPONSES - 1:             # not enough valid intervals
        return None, None, None
    mean = sum(iti) / len(iti)
    var  = sum((v-mean)**2 for v in iti) / (len(iti)-1)
    iiv  = math.sqrt(var)
    cv   = (iiv / mean * 100) if mean > 0 else 0
    return iiv, mean, cv


def compute_sync(responses):
    """
    Latency = tap_time - beat_time for each hit.
    Returns (mean_latency_ms, std_latency_ms).
    Mean latency is just reaction time -- physiologically normal, not a score.
    Std dev of latency is the actual synchronisation-consistency biomarker.
    """
    if len(responses) < 2:
        return None, None
    lats = [r[2] for r in responses]
    mean = sum(lats) / len(lats)
    var  = sum((v-mean)**2 for v in lats) / (len(lats)-1)
    return mean, math.sqrt(var)


def iiv_label(cv_pct):
    if cv_pct < IIV_CV_NORMAL:
        return "Within typical range", GREEN
    elif cv_pct < IIV_CV_CONCERN:
        return "Mild variability - consider monitoring", ORANGE
    else:
        return "Elevated variability - recommend follow-up", RED


def sync_label(std_ms):
    # Kept for internal use but no longer shown in results
    if std_ms < 200:
        return "Consistent beat timing", GREEN
    elif std_ms < 400:
        return "Moderate timing variability", ORANGE
    else:
        return "Irregular beat timing - recommend follow-up", RED


# ── Camera ─────────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[ERROR] Could not open camera.")
    exit(1)

WIN = "IIV Finger Tapping Test  |  Q to quit"
cv2.namedWindow(WIN)
cv2.setMouseCallback(WIN, mouse_callback)

print("=" * 52)
print("  IIV Finger Tapping Test")
print("  Click 'Start Test' in the camera window.")
print("  Press Q to quit.")
print("=" * 52)

# ── Main Loop ──────────────────────────────────────────────────────────────
while cap.isOpened():

    ok, frame = cap.read()
    if not ok:
        continue

    frame = cv2.flip(frame, 1)
    fh, fw = frame.shape[:2]

    now        = time.time()
    btn_rect   = get_btn_rect(fw, fh)
    hovered    = in_rect(mouse_x, mouse_y, btn_rect)
    clicked    = btn_pressed and hovered
    btn_pressed = False

    # ── MediaPipe ──────────────────────────────────────────────────────────
    rgb    = preprocess_for_mediapipe(frame)   # CLAHE + sharpening; frame (BGR) untouched for display
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_img, int(now * 1000))
    hand_visible = bool(result.hand_landmarks)
    if hand_visible:
        landmarks = smooth_landmarks(
            result.hand_landmarks[0], _lm_filters_x, _lm_filters_y, now
        )
    else:
        landmarks = None

    # ── Metronome ──────────────────────────────────────────────────────────
    # Fire AUDIO_LEAD seconds early so the sound reaches ears near beat_time.
    # The beat is logged at its scheduled time (next_beat_time), not at fire time,
    # so latency calculations stay accurate.
    if state in (WARMUP, RECORDING) and next_beat_time is not None:
        if now >= next_beat_time - AUDIO_LEAD and not beep_fired:
            beep_fired = True
            if state == RECORDING:
                beat_times.append(next_beat_time)
            threading.Thread(target=play_beep, daemon=True).start()
        if now >= next_beat_time:
            next_beat_time += METRONOME_INTERVAL
            beep_fired = False

    # ── Tap Detection ───────────────────────────────────────────────────────
    if state == RECORDING and hand_visible:
        lm4_x, lm4_y, _ = landmarks[4]
        lm8_x, lm8_y, _ = landmarks[8]
        raw_dist = math.hypot(lm4_x - lm8_x, lm4_y - lm8_y)
        # Distance EMA: second smoothing layer on the scalar signal
        _dist_ema = raw_dist if _dist_ema is None else (
            DIST_EMA_ALPHA * raw_dist + (1 - DIST_EMA_ALPHA) * _dist_ema
        )
        touching = _dist_ema < TAP_THRESHOLD
        if touching and not is_touching and (now - last_tap_time) > TAP_DEBOUNCE:
            tap_timestamps.append(now)
            tap_count    += 1
            last_tap_time = now
            flash_until   = now + 0.15
        is_touching = touching

    # ── Draw Hand ──────────────────────────────────────────────────────────
    if hand_visible:
        draw_hand(frame, landmarks, fh, fw, flash=(now < flash_until))

    # ══════════════════════════════════════════════════════════════════════
    # IDLE
    # ══════════════════════════════════════════════════════════════════════
    if state == IDLE:
        dark_panel(frame, fw//2-235, fh//2-75, 470, 128)
        ctext(frame, "IIV Finger Tapping Test",      fh//2-44, scale=0.85)
        ctext(frame, "Measures motor rhythm -- a biomarker linked to",
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
            ("Using your PREFERRED hand:",                              WHITE ),
            ("",                                                         WHITE ),
            ("Each time you hear the BEEP, tap your INDEX",            WHITE ),
            ("FINGERTIP to your THUMB -- once per beep.",              WHITE ),
            ("",                                                         WHITE ),
            ("Tap anytime within the 1-second window.",                GRAY  ),
            ("Your score is your TAP-TO-TAP rhythm consistency.",      GRAY  ),
            ("Exact beat timing does NOT affect your IIV score.",      GRAY  ),
            ("",                                                         WHITE ),
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
            next_beat_time = now; beep_fired = False

    # ══════════════════════════════════════════════════════════════════════
    # WARMUP
    # ══════════════════════════════════════════════════════════════════════
    elif state == WARMUP:
        elapsed   = now - warmup_start
        remaining = WARMUP_DURATION - elapsed
        if remaining <= 0:
            state = RECORDING; recording_start = now
            tap_timestamps = []; beat_times = []
            tap_count = 0; is_touching = False; last_tap_time = 0.0
            # next_beat_time carries over -- beat stays continuous
            # Reset smoothing state so warmup filter history doesn't bleed into scored data
            _new_x, _new_y = make_landmark_filters()
            _lm_filters_x[:] = _new_x
            _lm_filters_y[:] = _new_y
            _dist_ema = None
        else:
            bar_x, bar_y, bar_w = 20, fh-28, fw-40
            filled = int(bar_w * (elapsed / WARMUP_DURATION))
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), DARK, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+filled, bar_y+14), ORANGE, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), GRAY, 1)

            dark_panel(frame, fw//2-250, fh//2-58, 500, 116, alpha=0.74)
            ctext(frame, "WARM UP -- practice, no data recorded",
                  fh//2-28, scale=0.75, color=ORANGE, thickness=2)
            ctext(frame, "Tap once each time you hear the beep.",
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
            responses, misses      = analyze_responses(tap_timestamps, beat_times)
            response_times         = [r[1] for r in responses]
            res_hits               = len(responses)
            res_misses             = misses
            
            # Discard first 3 "ramp-up" taps to measure steady automaticity
            steady_taps = response_times[3:] if len(response_times) > 6 else response_times
            
            # IIV relies on response_times (one tap per interval max) to filter out
            # accidental double taps in the same beat window.
            res_iiv_ms, res_mean_iti_ms, res_cv_pct = compute_iiv(steady_taps)
            res_mean_lat_ms, res_sync_std_ms         = compute_sync(responses)
            state = COMPLETE

        else:
            # Progress bar (green)
            bar_x, bar_y, bar_w = 20, fh-28, fw-40
            filled = int(bar_w * (elapsed / RECORDING_DURATION))
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), DARK, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+filled, bar_y+14), GREEN, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+14), GRAY, 1)

            # Live stats (top left)
            dark_panel(frame, 10, 10, 228, 75)
            cv2.putText(frame, f"Time left:  {remaining:.1f}s",
                        (22, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, WHITE, 2)
            cv2.putText(frame, f"Taps: {tap_count}   Beats: {len(beat_times)}",
                        (22, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.60, GREEN, 2)

            # ── Beat indicator ─────────────────────────────────────────
            # Depleting arc shows time left in the current 3 s window.
            # Bright flash + "TAP!" text + screen border fire on each beat.
            last_beat   = beat_times[-1] if beat_times else recording_start
            time_since  = now - last_beat
            frac_left   = max(0.0, 1.0 - time_since / METRONOME_INTERVAL)
            frac_done   = 1.0 - frac_left

            cx, cy  = fw // 2, 46
            r_arc   = 38          # outer arc radius
            r_inner = 24          # filled inner circle radius

            # Dark backing disc
            cv2.circle(frame, (cx, cy), r_arc + 4, (30, 30, 30), -1)

            # Depleting arc (green -> yellow -> red as window closes)
            sweep = int(360 * min(1.0, frac_left))
            if sweep > 0:
                if frac_left > 0.55:
                    arc_col = GREEN
                elif frac_left > 0.25:
                    arc_col = YELLOW
                else:
                    arc_col = RED
                cv2.ellipse(frame, (cx, cy), (r_arc, r_arc),
                            -90, 0, -sweep, arc_col, 9)

            # Inner circle: white-hot flash decaying over 400 ms
            if time_since >= 0:
                flash_t   = max(0.0, 1.0 - time_since / 0.4)
                inner_v   = int(55 + 200 * flash_t)
            else:
                inner_v   = 55
            cv2.circle(frame, (cx, cy), r_inner, (min(255, inner_v), min(255, inner_v), min(255, inner_v)), -1)

            # "TAP!" label for 500 ms after beat
            if 0 <= time_since < 0.5:
                ctext(frame, "TAP!", cy + r_arc + 20,
                      scale=1.0, color=YELLOW, thickness=2)

            # Whole-screen border flash for 150 ms after beat
            if 0 <= time_since < 0.15:
                cv2.rectangle(frame, (2, 2), (fw - 3, fh - 3), WHITE, 5)

            if not hand_visible:
                dark_panel(frame, fw//2-185, fh//2-28, 370, 56)
                ctext(frame, "No hand detected -- show your hand",
                      fh//2+8, scale=0.6, color=ORANGE)

    # ══════════════════════════════════════════════════════════════════════
    # COMPLETE
    # ══════════════════════════════════════════════════════════════════════
    elif state == COMPLETE:
        dark_panel(frame, 28, 42, fw-56, fh-84, alpha=0.90)

        total_beats = len(beat_times)
        ctext(frame, "Test Complete -- IIV Result", 90, scale=0.90, color=YELLOW, thickness=2)
        ctext(frame, f"Beats: {total_beats}   Hits: {res_hits}   Missed: {res_misses}   Raw taps: {tap_count}",
              128, scale=0.55, color=WHITE)

        if res_iiv_ms is not None:
            iiv_lbl, iiv_col = iiv_label(res_cv_pct)

            # Hit rate
            ctext(frame, f"Mean tap interval:  {res_mean_iti_ms:.0f} ms  ({res_hits}/{total_beats} beats hit)",
                  160, scale=0.58, color=WHITE)

            # IIV -- core biomarker (tap-to-tap, independent of beat timing)
            ctext(frame, f"IIV:  {res_iiv_ms:.1f} ms   (CV = {res_cv_pct:.1f}%)",
                  210, scale=0.92, color=iiv_col, thickness=2)
            ctext(frame, iiv_lbl, 245, scale=0.65, color=iiv_col)

            ctext(frame, "IIV = std dev of tap-to-tap intervals (beat timing irrelevant)",
                  278, scale=0.44, color=GRAY, thickness=1)

            ctext(frame, "-" * 58, 308, scale=0.37, color=GRAY, thickness=1)
            ctext(frame, "IIV ref (1 s paradigm): CV <15% normal | 15-25% mild | >25% elevated",
                  330, scale=0.40, color=GRAY, thickness=1)
            ctext(frame, "Not a medical diagnosis. Consult a healthcare professional.",
                  356, scale=0.40, color=GRAY, thickness=1)

        else:
            ctext(frame, f"Need at least {MIN_RESPONSES} successful taps to score.",
                  200, scale=0.68, color=ORANGE)
            ctext(frame, f"Got {res_hits} hit(s) this run. Try again.",
                  234, scale=0.58, color=GRAY)

        draw_button(frame, btn_rect, "Try Again", hovered)
        if clicked:
            state = IDLE
            tap_timestamps = []; beat_times = []
            tap_count = 0; flash_until = 0.0
            res_hits = 0; res_misses = 0
            res_iiv_ms = res_mean_iti_ms = res_cv_pct = None
            res_mean_lat_ms = res_sync_std_ms = None

    # ── Render ─────────────────────────────────────────────────────────────
    cv2.imshow(WIN, frame)
    if cv2.waitKey(5) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
landmarker.close()
print("\n[INFO] IIV test closed.")
