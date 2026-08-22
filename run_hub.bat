@echo off
REM Hand-Detection-3D Control Hub — double-click to start.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" launcher.py
) else (
    python launcher.py
)
pause
