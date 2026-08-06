"""Config loader. Reads YAML once and exposes a typed-ish object."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Config:
    def __init__(self, data: dict[str, Any], root: Path) -> None:
        self._data = data
        self.root = root

    @classmethod
    def load(cls, path: str | Path = "config/pipeline.yaml") -> "Config":
        path = Path(path)
        if not path.is_absolute():
            # resolve relative to project root (parent of src/)
            root = Path(__file__).resolve().parents[2]
            path = root / path
        else:
            root = path.parent.parent
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(data, root)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def path(self, key: str) -> Path:
        """Return an absolute path for a configured path key."""
        rel = self._data["paths"][key]
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    @property
    def data(self) -> dict[str, Any]:
        return self._data
