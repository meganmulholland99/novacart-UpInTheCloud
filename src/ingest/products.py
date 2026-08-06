"""Ingest products from SQLite -> Bronze parquet using an incremental watermark."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from ..utils.exceptions import IngestionError
from ..utils.logging_setup import log_event
from ..utils.state import StateStore


def _row_hash(row: pd.Series) -> str:
    payload = "|".join("" if pd.isna(v) else str(v) for v in row.values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ingest_products(date_str: str, config, logger: logging.Logger, run_id: str, state: StateStore) -> dict:
    """Incremental load: read rows with updated_at > last_watermark."""
    src_cfg = config["sources"]["products"]
    db_path = config.root / src_cfg["db_path"]
    table = src_cfg["table"]
    watermark_col = src_cfg["watermark_column"]

    if not db_path.exists():
        raise IngestionError(f"products db not found: {db_path}")

    last_wm = state.get_watermark("products")
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        if last_wm:
            query = text(f"SELECT * FROM {table} WHERE {watermark_col} > :wm ORDER BY {watermark_col}")
            df = pd.read_sql(query, conn, params={"wm": last_wm})
        else:
            df = pd.read_sql(f"SELECT * FROM {table} ORDER BY {watermark_col}", conn)

    if df.empty:
        log_event(logger, "INFO", "products_no_new_rows", run_id=run_id, last_watermark=last_wm)
        return {"source": "products", "date": date_str, "rows": 0, "path": None}

    df["_ingested_at"] = datetime.now(timezone.utc).isoformat()
    df["_source_file"] = f"{table}@sqlite"
    df["_row_hash"] = df.drop(columns=["_ingested_at", "_source_file"], errors="ignore").apply(_row_hash, axis=1)

    bronze_dir = config.path("bronze") / "products" / f"dt={date_str}"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    out_path = bronze_dir / "products.parquet"
    df.to_parquet(out_path, index=False)

    # Advance the watermark ONLY after a successful write.
    new_wm = str(df[watermark_col].max())
    state.set_watermark("products", new_wm)

    log_event(
        logger, "INFO", "bronze_products_written",
        run_id=run_id, source="products", date=date_str,
        rows=len(df), path=str(out_path), new_watermark=new_wm,
    )
    return {"source": "products", "date": date_str, "rows": len(df), "path": str(out_path), "new_watermark": new_wm}
