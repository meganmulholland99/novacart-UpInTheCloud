@echo off
REM End-to-end demo for Windows. Equivalent to scripts\run_everything.sh on Mac/Linux.
REM Just calls the cross-platform Python runner.

cd /d "%~dp0\.."

python scripts\run_everything.py
if errorlevel 1 (
    echo.
    echo Pipeline run failed. See output above.
    exit /b 1
)
