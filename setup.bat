@echo off
REM Hand-Detection-3D one-click setup — double-click to install everything.
cd /d "%~dp0"

REM Most first-run failures are just a missing interpreter, and the shell's
REM own "'python' is not recognized" tells nobody what to do about it.
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo   Python was not found on this PC.
    echo.
    echo   Install Python 3.12 from https://www.python.org/downloads/
    echo   and tick "Add python.exe to PATH" in the installer.
    echo   Or, in a terminal:  winget install Python.Python.3.12
    echo.
    echo   Then double-click this file again.
    echo.
    pause
    exit /b 1
)

python install.py
pause
