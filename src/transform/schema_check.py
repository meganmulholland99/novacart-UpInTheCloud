"""Schema-drift detection. Distinguishes additive vs subtractive drift."""
from __future__ import annotations

import logging
from typing import Iterable

from ..utils.exceptions import SchemaError
from ..utils.logging_setup import log_event


def check_schema(source: str, actual_columns: Iterable[str], expected_columns: Iterable[str],
                 logger: logging.Logger, run_id: str) -> dict:
    """Return a dict describing drift; raise SchemaError on hard failures."""
    actual = set(actual_columns)
    expected = set(expected_columns)

    missing = expected - actual           # SUBTRACTIVE — hard fail
    extra = actual - expected             # ADDITIVE — warn

    if missing:
        log_event(
            logger, "ERROR", "schema_drift_missing",
            run_id=run_id, source=source, missing=sorted(missing),
        )
        raise SchemaError(f"[{source}] required columns missing: {sorted(missing)}")

    if extra:
        log_event(
            logger, "WARNING", "schema_drift_extra",
            run_id=run_id, source=source, extra=sorted(extra),
        )

    return {"source": source, "missing": sorted(missing), "extra": sorted(extra)}
