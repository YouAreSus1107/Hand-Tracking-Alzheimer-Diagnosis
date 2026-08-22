#!/usr/bin/env python3
"""One-command setup for the Camera-Based Motor Screening Suite.

Run this once after cloning the repo:

    python install.py            # or double-click setup.bat on Windows

It is stdlib-only (no third-party imports) so it can bootstrap before any
dependencies exist. It will:

  1. Check the Python version.
  2. Create a local virtual environment in .venv/ (if not already there).
  3. Install the pip dependencies from requirements.txt into that venv.
  4. Download any missing MediaPipe model bundles into model/.
  5. Print how to launch the suite.
"""

import os
import subprocess
import sys
import urllib.request

# Resolve everything relative to this file so it works from any cwd.
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(REPO_ROOT, ".venv")
REQUIREMENTS = os.path.join(REPO_ROOT, "requirements.txt")
MODEL_DIR = os.path.join(REPO_ROOT, "model")

# MediaPipe model bundles. hand_landmarker.task is committed to the repo and so
# normally arrives with the clone; face_landmarker.task is NOT in git and must be
# downloaded. Both are re-fetched here if missing, for robustness.
MODELS = {
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/latest/hand_landmarker.task"
    ),
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/latest/face_landmarker.task"
    ),
}

IS_WINDOWS = os.name == "nt"


def log(msg):
    print(f"[setup] {msg}", flush=True)


def check_python_version():
    major, minor = sys.version_info[:2]
    log(f"Python {major}.{minor}.{sys.version_info[2]} detected.")
    if (major, minor) < (3, 9):
        log("WARNING: Python 3.9+ is recommended; older versions may not have "
            "MediaPipe wheels. Continuing anyway.")
    elif (major, minor) >= (3, 13):
        log("NOTE: MediaPipe wheels are published mainly for Python 3.9-3.12. "
            "If 'pip install' fails on mediapipe, use a 3.12 interpreter. "
            "Continuing anyway.")


def venv_python():
    """Path to the venv's interpreter (Windows: Scripts, else bin)."""
    if IS_WINDOWS:
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def create_venv():
    py = venv_python()
    if os.path.exists(py):
        log(".venv already exists — reusing it.")
        return
    log("Creating virtual environment in .venv/ ...")
    subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    log(".venv created.")


def install_requirements():
    py = venv_python()
    log("Upgrading pip in the venv ...")
    subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "pip"])
    log("Installing dependencies from requirements.txt ...")
    subprocess.check_call([py, "-m", "pip", "install", "-r", REQUIREMENTS])
    log("Dependencies installed.")


def _progress(block_num, block_size, total_size):
    if total_size <= 0:
        return
    pct = min(100, block_num * block_size * 100 // total_size)
    print(f"\r        downloading... {pct:3d}%", end="", flush=True)


def download_models():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for name, url in MODELS.items():
        dest = os.path.join(MODEL_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            log(f"{name} already present — skipping.")
            continue
        log(f"Downloading {name} ...")
        try:
            urllib.request.urlretrieve(url, dest, _progress)
            print()  # end the progress line
            log(f"{name} downloaded ({os.path.getsize(dest) // 1024} KB).")
        except Exception as exc:  # noqa: BLE001 — don't abort the whole setup
            print()
            log(f"ERROR: could not download {name}: {exc}")
            log(f"  Download it manually into model/ from:\n    {url}")


def print_next_steps():
    py = venv_python()
    # Show a repo-relative, shell-friendly path for the interpreter.
    rel_py = os.path.relpath(py, REPO_ROOT)
    print()
    log("Setup complete. To launch the control hub:")
    if IS_WINDOWS:
        print("        run_hub.bat            (double-click, or run in a terminal)")
        print(f"        {rel_py} launcher.py")
    else:
        print(f"        {rel_py} launcher.py")
    print()
    log("To run a test directly, use the same venv interpreter, e.g.:")
    print(f"        {rel_py} screening_tests{os.sep}finger_tapping.py")


def main():
    log("Starting setup for the Motor Screening Suite.")
    check_python_version()
    create_venv()
    install_requirements()
    download_models()
    print_next_steps()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        log(f"A setup step failed (exit code {exc.returncode}). See the output above.")
        sys.exit(exc.returncode)
