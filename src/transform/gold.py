"""Gold layer: business-ready star schema.

  fact_orders      ────► dim_customer  (SCD-2)
       │
       ├───────────────► dim_product   (SCD-1)
       │
       └───────────────► dim_date
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..utils.logging_setup import log_event


# ----- helpers -----

def _read_silver(config, source: str, date_str: str) -> pd.DataFrame:
    path = config.path("silver") / source / f"dt={date_str}" / f"{source}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _gold_path(config, name: str) -> Path:
    d = config.path("gold")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.parquet"


# ----- dim_date -----

def build_dim_date(config, logger: logging.Logger, run_id: str,
                   start: str = "2024-01-01", end: str = "2026-12-31") -> dict:
    dates = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date": dates})
    df["date_key"] = df["date"].dt.strftime("%Y%m%d").astype(int)
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].dt.quarter
    df["month"] = df["date"].dt.month
    df["day"] = df["date"].dt.day
    df["day_of_week"] = df["date"].dt.day_name()
    df["is_weekend"] = df["date"].dt.dayofweek >= 5

    out_path = _gold_path(config, "dim_date")
    df.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "gold_dim_date_built", run_id=run_id, rows=len(df), path=str(out_path))
    return {"table": "dim_date", "rows": len(df), "path": str(out_path)}


# ----- dim_product (SCD-1: overwrite) -----

def build_dim_product(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    new = _read_silver(config, "products", date_str)
    out_path = _gold_path(config, "dim_product")

    if out_path.exists():
        existing = pd.read_parquet(out_path)
    else:
        existing = pd.DataFrame()

    if new.empty:
        if existing.empty:
            existing.to_parquet(out_path, index=False) if not existing.empty else None
        log_event(logger, "INFO", "gold_dim_product_no_change", run_id=run_id, date=date_str)
        return {"table": "dim_product", "rows": len(existing), "path": str(out_path)}

    keep_cols = ["product_id", "name", "category", "price", "updated_at"]
    new_keep = new[keep_cols].copy()

    if existing.empty:
        merged = new_keep
    else:
        # SCD-1: overwrite — drop existing rows whose PK appears in `new`, then append
        merged = pd.concat([
            existing[~existing["product_id"].isin(new_keep["product_id"])][keep_cols],
            new_keep,
        ], ignore_index=True)

    merged.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "gold_dim_product_built", run_id=run_id,
              rows=len(merged), new_rows=len(new_keep), path=str(out_path))
    return {"table": "dim_product", "rows": len(merged), "path": str(out_path)}


# ----- dim_customer (SCD-2: track history) -----

SCD2_HIGH = "9999-12-31"


def build_dim_customer(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    new = _read_silver(config, "customers", date_str)
    out_path = _gold_path(config, "dim_customer")
    today = date_str  # use the processing date as effective date

    if existing_exists := out_path.exists():
        existing = pd.read_parquet(out_path)
    else:
        existing = pd.DataFrame(columns=[
            "customer_id", "name", "email", "signup_date",
            "addr_street", "addr_city", "addr_state", "addr_zip", "phones",
            "valid_from", "valid_to", "is_current",
        ])

    if new.empty:
        existing.to_parquet(out_path, index=False)
        log_event(logger, "INFO", "gold_dim_customer_no_change", run_id=run_id, date=date_str)
        return {"table": "dim_customer", "rows": len(existing), "path": str(out_path)}

    # The columns that define a "change" for SCD-2
    tracked_cols = [
        "customer_id", "name", "email", "signup_date",
        "addr_street", "addr_city", "addr_state", "addr_zip",
    ]
    # Make sure the columns exist in `new`
    for c in tracked_cols:
        if c not in new.columns:
            new[c] = None
    new = new.copy()
    new["phones"] = new["phones"].apply(lambda v: list(v) if isinstance(v, (list, tuple)) else [])

    # Convert any object-list phones for storage compatibility
    if not existing.empty and "phones" in existing.columns:
        def _norm_phones(v):
            if isinstance(v, (list, tuple)):
                return list(v)
            # numpy arrays — common after parquet roundtrip
            try:
                return list(v)
            except TypeError:
                return [] if v is None else [v]
        existing["phones"] = existing["phones"].apply(_norm_phones)

    current = existing[existing["is_current"] == True] if not existing.empty else existing  # noqa: E712

    # 1) Brand-new customers (not in current) -> straight insert
    new_ids = set(new["customer_id"])
    current_ids = set(current["customer_id"]) if not current.empty else set()
    fresh = new[~new["customer_id"].isin(current_ids)].copy()

    # 2) Existing customers — compare tracked cols. If changed: close old, insert new.
    overlap = new[new["customer_id"].isin(current_ids)].copy()

    changed_rows = []
    if not overlap.empty and not current.empty:
        merged_cmp = overlap.merge(
            current[tracked_cols + ["valid_from"]],
            on="customer_id", suffixes=("_new", "_old"),
        )
        def _safe_isna(v):
            try:
                result = pd.isna(v)
                return bool(result) if not hasattr(result, "__iter__") else False
            except (TypeError, ValueError):
                return False

        for _, r in merged_cmp.iterrows():
            diff = False
            for c in tracked_cols:
                if c == "customer_id":
                    continue
                vn, vo = r[f"{c}_new"], r[f"{c}_old"]
                if _safe_isna(vn) and _safe_isna(vo):
                    continue
                if vn != vo:
                    diff = True
                    break
            if diff:
                changed_rows.append(r["customer_id"])

    # Close out old versions
    if changed_rows and not existing.empty:
        mask = (existing["customer_id"].isin(changed_rows)) & (existing["is_current"] == True)  # noqa: E712
        existing.loc[mask, "valid_to"] = today
        existing.loc[mask, "is_current"] = False

    # Rows to insert: fresh customers + changed customers' new versions
    to_insert = pd.concat([
        fresh,
        new[new["customer_id"].isin(changed_rows)],
    ], ignore_index=True)

    if not to_insert.empty:
        insert_df = to_insert[tracked_cols + ["phones"]].copy()
        insert_df["valid_from"] = today
        insert_df["valid_to"] = SCD2_HIGH
        insert_df["is_current"] = True
        result = pd.concat([existing, insert_df], ignore_index=True)
    else:
        result = existing

    result.to_parquet(out_path, index=False)
    log_event(
        logger, "INFO", "gold_dim_customer_built",
        run_id=run_id, date=date_str, rows=len(result),
        new_inserts=len(fresh), changed=len(changed_rows), path=str(out_path),
    )
    return {"table": "dim_customer", "rows": len(result), "path": str(out_path),
            "new_inserts": len(fresh), "changed": len(changed_rows)}


# ----- fact_orders (idempotent partition replace) -----

def build_fact_orders(date_str: str, config, logger: logging.Logger, run_id: str) -> dict:
    orders = _read_silver(config, "orders", date_str)
    out_path = _gold_path(config, "fact_orders")

    if orders.empty:
        if not out_path.exists():
            # initialize an empty file so downstream queries don't blow up
            pd.DataFrame(columns=[
                "order_id", "customer_id", "product_id", "order_date", "amount", "currency",
                "status", "quantity", "date_key", "_load_date", "_run_id",
            ]).to_parquet(out_path, index=False)
        log_event(logger, "INFO", "gold_fact_orders_no_data", run_id=run_id, date=date_str)
        return {"table": "fact_orders", "rows": 0, "path": str(out_path)}

    fact = orders[[
        "order_id", "customer_id", "product_id", "order_date",
        "amount", "currency", "status", "quantity",
    ]].copy()
    fact["date_key"] = pd.to_datetime(fact["order_date"]).dt.strftime("%Y%m%d").astype(int)
    fact["_load_date"] = date_str
    fact["_run_id"] = run_id

    # Idempotent partition-replace: drop existing rows for this _load_date, then append.
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        existing = existing[existing["_load_date"] != date_str] if "_load_date" in existing.columns else existing
        result = pd.concat([existing, fact], ignore_index=True)
    else:
        result = fact

    result.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "gold_fact_orders_built",
              run_id=run_id, date=date_str, rows=len(result), new_rows=len(fact), path=str(out_path))
    return {"table": "fact_orders", "rows": len(result), "new_rows": len(fact), "path": str(out_path)}
