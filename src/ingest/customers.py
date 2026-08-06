"""Ingest nested customer JSON -> Bronze parquet."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..utils.exceptions import IngestionError
from ..utils.logging_setup import log_event


def _row_hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ingest_customers(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    src_cfg = config["sources"]["customers"]
    landing_dir = config.root / src_cfg["landing_dir"]
    filename = src_cfg["file_pattern"].format(date=date_str)
    src_path = landing_dir / filename

    if not src_path.exists():
        raise IngestionError(f"customers file not found: {src_path}")

    try:
        with src_path.open("r", encoding="utf-8") as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        raise IngestionError(f"invalid JSON in {src_path}: {e}") from e

    if not isinstance(records, list):
        raise IngestionError(f"expected a JSON array, got {type(records).__name__}")

    if not records:
        raise IngestionError(f"customers file is empty: {src_path}")

    # Keep nested fields as JSON strings at Bronze; explode/normalize in Silver.
    rows = []
    for rec in records:
        row = {
            "customer_id": rec.get("customer_id"),
            "name": rec.get("name"),
            "email": rec.get("email"),
            "signup_date": rec.get("signup_date"),
            "address": json.dumps(rec.get("address")) if rec.get("address") is not None else None,
            "phones": json.dumps(rec.get("phones", [])),
            "_row_hash": _row_hash(rec),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df["_ingested_at"] = datetime.now(timezone.utc).isoformat()
    df["_source_file"] = filename

    bronze_dir = config.path("bronze") / "customers" / f"dt={date_str}"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    out_path = bronze_dir / "customers.parquet"
    df.to_parquet(out_path, index=False)

    log_event(
        logger, "INFO", "bronze_customers_written",
        run_id=run_id, source="customers", date=date_str,
        rows=len(df), path=str(out_path),
    )
    return {"source": "customers", "date": date_str, "rows": len(df), "path": str(out_path)}
