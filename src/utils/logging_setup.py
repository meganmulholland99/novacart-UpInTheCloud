"""Structured logging. Uses loguru if available, falls back to stdlib."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any


def _json_formatter(record: logging.LogRecord) -> str:
    payload: dict[str, Any] = {
        "ts": record.created,
        "level": record.levelname,
        "logger": record.name,
        "msg": record.getMessage(),
    }
    if hasattr(record, "extra_data"):
        payload.update(record.extra_data)  # type: ignore[arg-type]
    if record.exc_info:
        payload["exc"] = logging.Formatter().formatException(record.exc_info)
    return json.dumps(payload, default=str)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _json_formatter(record)


def get_logger(name: str = "novacart", log_dir: Path | None = None, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # console handler — human readable
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(ch)

    # file handler — JSON lines
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "pipeline.jsonl")
        fh.setFormatter(JsonFormatter())
        logger.addHandler(fh)

    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: str, msg: str, **kwargs: Any) -> None:
    """Emit a structured event with extra fields."""
    level_int = getattr(logging, level.upper(), logging.INFO)
    record = logger.makeRecord(
        name=logger.name,
        level=level_int,
        fn="",
        lno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    record.extra_data = kwargs  # type: ignore[attr-defined]
    logger.handle(record)
