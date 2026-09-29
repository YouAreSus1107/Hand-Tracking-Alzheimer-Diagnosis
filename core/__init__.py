import os

# OpenCV's Media Foundation backend inserts hardware transforms by default, and
# with them every property set renegotiates the stream: opening the Razer Kiyo
# V2 X at 640x480/60 took ~15 s, against 0.5 s with them off, at the same
# 62 fps (measured 2026-09-28). OpenCV reads this once, when cv2 is imported,
# so it has to be set here: every entry script imports `core` (i18n, the
# splash) before cv2. A value the user already set is left alone.
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
