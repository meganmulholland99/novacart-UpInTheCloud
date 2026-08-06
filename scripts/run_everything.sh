#!/usr/bin/env bash
# End-to-end demo for macOS / Linux. Equivalent to scripts\run_everything.bat on Windows.
# Just calls the cross-platform Python runner.
set -e

cd "$(dirname "$0")/.."

# Prefer python3 on macOS where `python` may point to Python 2 or not exist.
if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

"$PY" scripts/run_everything.py
