"""Silver layer: validate Bronze rows against pydantic schemas, dedup,
quarantine bad rows, write cleaned parquet."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Type

import pandas as pd
from pydantic import BaseModel, ValidationError

from ..utils.logging_setup import log_event
from ..utils.schemas import (
    CustomerRecord,
    EXPECTED_COLUMNS,
    OrderRecord,
    ProductRecord,
)
from .schema_check import check_schema


# ----- generic validator -----

def _validate_rows(df: pd.DataFrame, model: Type[BaseModel]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run each row through a pydantic model. Return (valid_df, bad_df)."""
    valid_rows: list[dict] = []
    bad_rows: list[dict] = []

    for raw in df.to_dict(orient="records"):
        meta_cols = {k: raw.get(k) for k in ("_ingested_at", "_source_file", "_row_hash")}
        payload = {k: v for k, v in raw.items() if not k.startswith("_")}
        try:
            cleaned = model(**payload).model_dump(mode="json")
            cleaned.update(meta_cols)
            valid_rows.append(cleaned)
        except ValidationError as e:
            bad = dict(raw)
            bad["_error_reason"] = json.dumps([{"loc": err["loc"], "msg": err["msg"]} for err in e.errors()])
            bad_rows.append(bad)

    return (
        pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(),
        pd.DataFrame(bad_rows) if bad_rows else pd.DataFrame(),
    )


def _write_quarantine(df: pd.DataFrame, config, source: str, date_str: str) -> Path | None:
    if df.empty:
        return None
    qdir = config.path("quarantine") / source / f"dt={date_str}"
    qdir.mkdir(parents=True, exist_ok=True)
    qpath = qdir / f"{source}_bad.parquet"
    df = df.copy()
    # Make every column safe for parquet: serialize dicts/lists to JSON strings
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(
                lambda v: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v
            )
    df["_quarantined_at"] = datetime.now(timezone.utc).isoformat()
    df.to_parquet(qpath, index=False)
    return qpath


# ----- orders -----

def build_silver_orders(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    bronze_path = config.path("bronze") / "orders" / f"dt={date_str}" / "orders.parquet"
    df = pd.read_parquet(bronze_path)

    check_schema("orders", df.columns, EXPECTED_COLUMNS["orders"] | {"_ingested_at", "_source_file", "_row_hash"},
                 logger, run_id)

    valid, bad = _validate_rows(df, OrderRecord)

    # Dedup on order_id, keep latest by _ingested_at
    if not valid.empty:
        valid = valid.sort_values("_ingested_at").drop_duplicates(subset=["order_id"], keep="last")

    silver_dir = config.path("silver") / "orders" / f"dt={date_str}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    out_path = silver_dir / "orders.parquet"
    valid.to_parquet(out_path, index=False)

    qpath = _write_quarantine(bad, config, "orders", date_str)

    log_event(
        logger, "INFO", "silver_orders_built",
        run_id=run_id, source="orders", date=date_str,
        rows_in=len(df), rows_out=len(valid), rows_quarantined=len(bad),
        out_path=str(out_path), quarantine_path=str(qpath) if qpath else None,
    )
    return {"source": "orders", "rows_in": len(df), "rows_out": len(valid),
            "rows_quarantined": len(bad), "out_path": str(out_path)}


# ----- customers -----

def build_silver_customers(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    bronze_path = config.path("bronze") / "customers" / f"dt={date_str}" / "customers.parquet"
    df = pd.read_parquet(bronze_path)

    check_schema("customers", df.columns, EXPECTED_COLUMNS["customers"] | {"_ingested_at", "_source_file", "_row_hash"},
                 logger, run_id)

    # Re-hydrate nested fields from JSON strings
    df = df.copy()
    df["address"] = df["address"].apply(lambda v: json.loads(v) if pd.notna(v) and v else None)
    df["phones"] = df["phones"].apply(lambda v: json.loads(v) if pd.notna(v) and v else [])

    valid, bad = _validate_rows(df, CustomerRecord)

    if not valid.empty:
        # flatten address into top-level columns; ensure every address has all fields
        def _addr_fields(a):
            a = a or {}
            return {
                "addr_street": a.get("street"),
                "addr_city": a.get("city"),
                "addr_state": a.get("state"),
                "addr_zip": a.get("zip"),
            }
        addr_df = pd.DataFrame([_addr_fields(a) for a in valid["address"]])
        valid = pd.concat([valid.drop(columns=["address"]).reset_index(drop=True),
                           addr_df.reset_index(drop=True)], axis=1)
        # phones stays as a list column
        valid = valid.sort_values("_ingested_at").drop_duplicates(subset=["customer_id"], keep="last")

    silver_dir = config.path("silver") / "customers" / f"dt={date_str}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    out_path = silver_dir / "customers.parquet"
    valid.to_parquet(out_path, index=False)

    qpath = _write_quarantine(bad, config, "customers", date_str)

    log_event(
        logger, "INFO", "silver_customers_built",
        run_id=run_id, source="customers", date=date_str,
        rows_in=len(df), rows_out=len(valid), rows_quarantined=len(bad),
        out_path=str(out_path), quarantine_path=str(qpath) if qpath else None,
    )
    return {"source": "customers", "rows_in": len(df), "rows_out": len(valid),
            "rows_quarantined": len(bad), "out_path": str(out_path)}


# ----- products -----

def build_silver_products(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    bronze_path = config.path("bronze") / "products" / f"dt={date_str}" / "products.parquet"
    if not bronze_path.exists():
        log_event(logger, "INFO", "silver_products_skipped_no_bronze", run_id=run_id, date=date_str)
        return {"source": "products", "rows_in": 0, "rows_out": 0, "rows_quarantined": 0, "out_path": None}

    df = pd.read_parquet(bronze_path)
    check_schema("products", df.columns, EXPECTED_COLUMNS["products"] | {"_ingested_at", "_source_file", "_row_hash"},
                 logger, run_id)

    valid, bad = _validate_rows(df, ProductRecord)
    if not valid.empty:
        valid = valid.sort_values("_ingested_at").drop_duplicates(subset=["product_id"], keep="last")

    silver_dir = config.path("silver") / "products" / f"dt={date_str}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    out_path = silver_dir / "products.parquet"
    valid.to_parquet(out_path, index=False)

    qpath = _write_quarantine(bad, config, "products", date_str)

    log_event(
        logger, "INFO", "silver_products_built",
        run_id=run_id, source="products", date=date_str,
        rows_in=len(df), rows_out=len(valid), rows_quarantined=len(bad),
        out_path=str(out_path), quarantine_path=str(qpath) if qpath else None,
    )
    return {"source": "products", "rows_in": len(df), "rows_out": len(valid),
            "rows_quarantined": len(bad), "out_path": str(out_path)}
