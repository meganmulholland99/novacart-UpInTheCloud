"""End-to-end runner. Works on Mac, Linux, and Windows.

Usage:
    python scripts/run_everything.py

Optional flags:
    --skip-install     skip the pip install step (use if deps are already installed)
    --skip-tests       skip the pytest step

Equivalent to running these four commands in order:
    pip install -r requirements.txt
    python scripts/generate_sample_data.py
    python -m src.pipeline --date "2026-08-05" --backfill 4
    python -m pytest -v
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def run(label: str, cmd: list[str], fatal: bool = True) -> int:
    """Run a command; print a clear header; return its exit code."""
    print(f"\n==> {label}")
    print(f"    $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0 and fatal:
        print(f"\n[FAIL] '{label}' exited with code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)
    return result.returncode

def deps_installed() -> bool:
    """Quick probe: are core dependencies already importable?"""
    try:
        import pandas  # noqa: F401
        import pydantic  # noqa: F401
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False

def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end NovaCart ETL demo")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip 'pip install' (dependencies already present)")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip the pytest run")
    args = parser.parse_args()

    py = sys.executable  # same interpreter that invoked this script

    # 1. Install dependencies (smart: skip if already present)
    if args.skip_install:
        print("==> Skipping dependency install (--skip-install)")
    elif deps_installed():
        print("==> Dependencies already installed, skipping pip install")
    else:
        rc = run("Installing dependencies",
                 [py, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                 fatal=False)
        if rc != 0:
            print(
                "\nPip install failed. Two common reasons:\n"
                "  1. You're not in a virtualenv on a 'managed' Python (Debian/Ubuntu/Homebrew).\n"
                "     Fix: create a venv first.\n"
                "       macOS/Linux:   python3 -m venv .venv && source .venv/bin/activate\n"
                "       Windows:       python -m venv .venv && .venv\\Scripts\\activate\n"
                "     Then run this script again.\n"
                "  2. No internet / proxy blocking PyPI.\n"
                "     Fix: configure pip or install manually.\n",
                file=sys.stderr,
            )
            sys.exit(rc)

    # 2. Generate sample data
    run("Generating old sample data",
        [py, "scripts/generate_sample_data.py"])
    run("Generating new sample data",
            [py, "scripts/New_sample_data_gen.py"])
    # 3. Run pipeline
    run("Running pipeline for all 4 dates",
        [py, "-m", "src.pipeline", "--date", "2026-08-10", "--backfill", "3"])

    # 4. Tests
    if args.skip_tests:
        print("\n==> Skipping tests (--skip-tests)")
    else:
        run("Running test suite",
            [py, "-m", "pytest", "-v"])

    print("\nDone. See SAMPLE_RUN_REPORT.md for the expected output.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
