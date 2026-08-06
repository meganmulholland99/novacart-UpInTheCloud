"""Ingest the daily orders CSV file -> Bronze parquet.

The Bronze layer is a faithful, type-preserved copy of the source with
ingestion metadata appended. No cleaning happens here.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..utils.exceptions import IngestionError
from ..utils.logging_setup import log_event


def _detect_and_read(path: Path, primary_enc: str, fallback_enc: str) -> pd.DataFrame:
    """Try the primary encoding, fall back if it explodes."""
    try:
        # dtype=str — don't let pandas guess types at ingest. Casting belongs in Silver.
        return pd.read_csv(path, dtype=str, encoding=primary_enc, keep_default_na=False, na_values=[""])
    except UnicodeDecodeError:
        return pd.read_csv(path, dtype=str, encoding=fallback_enc, keep_default_na=False, na_values=[""])


def _row_hash(row: pd.Series) -> str:
    """Stable row hash for downstream dedup."""
    payload = "|".join("" if pd.isna(v) else str(v) for v in row.values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ingest_orders(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    """Ingest orders for one date. Returns a small metadata dict."""
    src_cfg = config["sources"]["orders"]
    landing_dir = config.root / src_cfg["landing_dir"]
    filename = src_cfg["file_pattern"].format(date=date_str)
    src_path = landing_dir / filename

    if not src_path.exists():
        raise IngestionError(f"orders file not found: {src_path}")

    df = _detect_and_read(
        src_path,
        primary_enc=src_cfg["encoding_primary"],
        fallback_enc=src_cfg["encoding_fallback"],
    )

    if df.empty:
        raise IngestionError(f"orders file is empty: {src_path}")

    # ingestion metadata
    df["_ingested_at"] = datetime.now(timezone.utc).isoformat()
    df["_source_file"] = filename
    df["_row_hash"] = df.drop(columns=["_ingested_at", "_source_file"], errors="ignore").apply(_row_hash, axis=1)

    bronze_dir = config.path("bronze") / "orders" / f"dt={date_str}"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    out_path = bronze_dir / "orders.parquet"
    df.to_parquet(out_path, index=False)

    log_event(
        logger, "INFO", "bronze_orders_written",
        run_id=run_id, source="orders", date=date_str,
        rows=len(df), path=str(out_path),
    )
    return {"source": "orders", "date": date_str, "rows": len(df), "path": str(out_path)}
