"""Watermark + run-metadata persistence. Tiny JSON file = good enough for a lab."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.watermarks_path = self.state_dir / "watermarks.json"
        self.runs_path = self.state_dir / "runs.jsonl"

    # ----- watermarks -----
    def get_watermark(self, source: str) -> str | None:
        if not self.watermarks_path.exists():
            return None
        try:
            data = json.loads(self.watermarks_path.read_text())
        except json.JSONDecodeError:
            return None
        return data.get(source)

    def set_watermark(self, source: str, value: str) -> None:
        data: dict[str, Any] = {}
        if self.watermarks_path.exists():
            try:
                data = json.loads(self.watermarks_path.read_text())
            except json.JSONDecodeError:
                data = {}
        data[source] = value
        self.watermarks_path.write_text(json.dumps(data, indent=2, default=str))

    # ----- run metadata -----
    def record_run(self, run_metadata: dict[str, Any]) -> None:
        with self.runs_path.open("a") as f:
            f.write(json.dumps(run_metadata, default=str) + "\n")

    def get_last_run(self) -> dict[str, Any] | None:
        if not self.runs_path.exists():
            return None
        lines = self.runs_path.read_text().strip().splitlines()
        if not lines:
            return None
        return json.loads(lines[-1])


def new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
