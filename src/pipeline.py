"""Orchestrator. Wires ingest -> silver -> gold for a given processing date.

Usage:
    python -m src.pipeline --date 2025-11-09
    python -m src.pipeline --date 2025-11-09 --backfill 3   # also run 3 prior days
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ingest.customers import ingest_customers
from .ingest.orders import ingest_orders
from .ingest.products import ingest_products
from .transform.gold import (
    build_dim_customer,
    build_dim_date,
    build_dim_product,
    build_fact_orders,
)
from .transform.silver import (
    build_silver_customers,
    build_silver_orders,
    build_silver_products,
)
from .utils.config import Config
from .utils.exceptions import IngestionError, PipelineError, SchemaError
from .utils.logging_setup import get_logger, log_event
from .utils.state import StateStore, new_run_id


def run_one_date(date_str: str, config: Config) -> dict:
    logger = get_logger(log_dir=config.path("logs"), level=config["logging"]["level"])
    state = StateStore(config.path("state"))
    run_id = new_run_id()
    started_at = datetime.now(timezone.utc)

    log_event(logger, "INFO", "pipeline_start", run_id=run_id, date=date_str)

    stages: list[dict] = []
    status = "SUCCESS"
    error_msg: str | None = None

    try:
        # ---- INGEST ----
        try:
            stages.append({"stage": "ingest_orders", **ingest_orders(date_str, config, logger, run_id)})
        except IngestionError as e:
            log_event(logger, "ERROR", "ingest_orders_failed", run_id=run_id, error=str(e))
            raise

        try:
            stages.append({"stage": "ingest_customers", **ingest_customers(date_str, config, logger, run_id)})
        except IngestionError as e:
            log_event(logger, "ERROR", "ingest_customers_failed", run_id=run_id, error=str(e))
            raise

        try:
            stages.append({"stage": "ingest_products", **ingest_products(date_str, config, logger, run_id, state)})
        except IngestionError as e:
            log_event(logger, "ERROR", "ingest_products_failed", run_id=run_id, error=str(e))
            raise

        # ---- SILVER ----
        stages.append({"stage": "silver_orders", **build_silver_orders(date_str, config, logger, run_id)})
        stages.append({"stage": "silver_customers", **build_silver_customers(date_str, config, logger, run_id)})
        stages.append({"stage": "silver_products", **build_silver_products(date_str, config, logger, run_id)})

        # ---- GOLD ----
        stages.append({"stage": "dim_date", **build_dim_date(config, logger, run_id)})
        stages.append({"stage": "dim_product", **build_dim_product(date_str, config, logger, run_id)})
        stages.append({"stage": "dim_customer", **build_dim_customer(date_str, config, logger, run_id)})
        stages.append({"stage": "fact_orders", **build_fact_orders(date_str, config, logger, run_id)})

    except PipelineError as e:
        status = "FAILED"
        error_msg = str(e)
        log_event(logger, "ERROR", "pipeline_failed", run_id=run_id, error=str(e), type=type(e).__name__)

    finished_at = datetime.now(timezone.utc)
    metadata = {
        "run_id": run_id,
        "date": date_str,
        "status": status,
        "error": error_msg,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_sec": (finished_at - started_at).total_seconds(),
        "stages": stages,
    }
    state.record_run(metadata)
    log_event(logger, "INFO", "pipeline_end", **{k: v for k, v in metadata.items() if k != "stages"})
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NovaCart ETL pipeline")
    parser.add_argument("--date", required=True, help="Processing date YYYY-MM-DD")
    parser.add_argument("--backfill", type=int, default=0,
                        help="Also process N days before --date")
    parser.add_argument("--config", default="config/pipeline.yaml")
    args = parser.parse_args(argv)

    config = Config.load(args.config)

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    dates = [target - timedelta(days=i) for i in range(args.backfill, -1, -1)]

    failures = 0
    for d in dates:
        result = run_one_date(d.strftime("%Y-%m-%d"), config)
        if result["status"] != "SUCCESS":
            failures += 1
            print(f"[FAIL] {d}: {result['error']}", file=sys.stderr)
        else:
            print(f"[OK]   {d}: ran in {result['duration_sec']:.2f}s")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
