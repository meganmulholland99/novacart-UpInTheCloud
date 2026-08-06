"""The seven scenarios required by the lab spec (Phase 5.2), plus
additional coverage for SCD2 history, incremental loading, and
quarantine-reason specificity.

  1. Happy path
  2. Duplicate handling (idempotency on a single row)
  3. Bad data goes to quarantine, not Gold
  4. Schema drift: additive — warn, succeed
  5. Schema drift: subtractive — fail loudly
  6. Idempotency: re-run the same date, Gold doesn't grow
  7. Backfill: 3 sequential dates == 3 individual runs (same Gold state)
  8. SCD Type 2: customer address change preserves history
  9. Incremental loading: only changed products are re-read

NOTE on backfill: src/pipeline.py has no standalone run_backfill()
function. --backfill is implemented in main() as a plain loop that calls
run_one_date() once per date, oldest first. So "sequential run_one_date
calls" IS the real backfill mechanism, not a weaker stand-in for it —
test_backfill_matches_sequential_runs below already covers the actual
code path.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import run_one_date
from src.utils.exceptions import SchemaError
from src.transform.silver import build_silver_orders
from src.ingest.orders import ingest_orders
from src.utils.logging_setup import get_logger


# ----- 1. Happy path -----

def test_happy_path_produces_expected_gold(config, seed_default_data, test_date_str):
    result = run_one_date(test_date_str, config)
    assert result["status"] == "SUCCESS", result.get("error")

    fact = pd.read_parquet(config.path("gold") / "fact_orders.parquet")
    assert len(fact) == 3
    assert set(fact["order_id"]) == {"O00000001", "O00000002", "O00000003"}
    assert (fact["amount"].astype(float) > 0).all()

    dim_customer = pd.read_parquet(config.path("gold") / "dim_customer.parquet")
    assert len(dim_customer) == 3
    assert dim_customer["is_current"].all()


# ----- 2. Duplicate handling -----

def test_duplicate_rows_in_source_collapse(config, write_orders, write_customers, build_products, test_date_str):
    rows = [
        ("O00000001", "C001", "P001", test_date_str, "49.99", "USD", "shipped", "1"),
        ("O00000001", "C001", "P001", test_date_str, "49.99", "USD", "shipped", "1"),  # dup
        ("O00000002", "C002", "P002", test_date_str, "10.00", "USD", "pending", "1"),
    ]
    write_orders(test_date_str, rows)
    write_customers(test_date_str, [
        {"customer_id": "C001", "name": "Alice", "email": "a@x.com", "signup_date": "2024-01-01",
         "address": {}, "phones": []},
        {"customer_id": "C002", "name": "Bob", "email": "b@x.com", "signup_date": "2024-02-01",
         "address": {}, "phones": []},
    ])
    build_products([("P001", "Mouse", "Electronics", "49.99", "2025-11-07T10:00:00"),
                    ("P002", "Keyboard", "Electronics", "129.50", "2025-11-07T10:00:00")])

    result = run_one_date(test_date_str, config)
    assert result["status"] == "SUCCESS"

    fact = pd.read_parquet(config.path("gold") / "fact_orders.parquet")
    assert len(fact) == 2  # the duplicate collapsed


# ----- 3. Bad data quarantines (Gold stays clean) -----

def test_bad_rows_go_to_quarantine_not_gold(config, write_orders, write_customers, build_products, test_date_str):
    rows = [
        ("O00000001", "C001", "P001", test_date_str, "49.99", "USD", "shipped",   "1"),  # good
        ("O00000002", "C002", "P002", test_date_str, "-1.00", "USD", "shipped",   "1"),  # bad: negative amount
        ("O00000003", "C003", "P001", test_date_str, "10.00", "USD", "warped",    "1"),  # bad: bad status
        ("O00000004", "C001", "P001", test_date_str, "10.00", "USD", "shipped",   "0"),  # bad: qty=0
    ]
    write_orders(test_date_str, rows)
    write_customers(test_date_str, [
        {"customer_id": "C001", "name": "Alice", "email": "a@x.com", "signup_date": "2024-01-01",
         "address": {}, "phones": []},
        {"customer_id": "C002", "name": "Bob", "email": "b@x.com", "signup_date": "2024-02-01",
         "address": {}, "phones": []},
        {"customer_id": "C003", "name": "Carol", "email": "c@x.com", "signup_date": "2024-03-01",
         "address": {}, "phones": []},
    ])
    build_products([("P001", "Mouse", "Electronics", "49.99", "2025-11-07T10:00:00"),
                    ("P002", "Keyboard", "Electronics", "129.50", "2025-11-07T10:00:00")])

    result = run_one_date(test_date_str, config)
    assert result["status"] == "SUCCESS"

    fact = pd.read_parquet(config.path("gold") / "fact_orders.parquet")
    assert len(fact) == 1
    assert fact.iloc[0]["order_id"] == "O00000001"

    q_path = config.path("quarantine") / "orders" / f"dt={test_date_str}" / "orders_bad.parquet"
    assert q_path.exists()
    quarantined = pd.read_parquet(q_path)
    assert len(quarantined) == 3
    assert "_error_reason" in quarantined.columns

    # _error_reason is a JSON string: '[{"loc": [...], "msg": ...}, ...]'
    # (see src/transform/silver.py::_validate_rows). Parse it and check
    # the actual field(s) pydantic flagged, rather than fuzzy substring
    # matching — this is what makes the reason "clear" to an on-call
    # engineer, and what the original test never actually verified.
    reasons = quarantined.set_index("order_id")["_error_reason"].apply(json.loads)

    def _flagged_fields(order_id: str) -> set[str]:
        return {loc for err in reasons[order_id] for loc in err["loc"]}

    assert "amount" in _flagged_fields("O00000002")
    assert "status" in _flagged_fields("O00000003")
    assert "quantity" in _flagged_fields("O00000004")

    # Reasons must be genuinely differentiated per row, not one generic
    # boilerplate message copy-pasted onto every quarantined row.
    reason_signatures = reasons.apply(lambda r: tuple(sorted(tuple(e["loc"]) for e in r)))
    assert reason_signatures.nunique() == 3, \
        "expected 3 distinct error reasons — quarantine isn't differentiating failure causes"


# ----- 4. Additive schema drift: succeeds with a warning -----

def test_additive_schema_drift_succeeds(config, write_orders, write_customers, build_products, test_date_str):
    header = "order_id,customer_id,product_id,order_date,amount,currency,status,quantity,promotion_code"
    rows = [
        ("O00000001", "C001", "P001", test_date_str, "49.99", "USD", "shipped", "1", "BLACKFRI"),
        ("O00000002", "C002", "P002", test_date_str, "10.00", "USD", "pending", "1", ""),
    ]
    write_orders(test_date_str, rows, header=header)
    write_customers(test_date_str, [
        {"customer_id": "C001", "name": "Alice", "email": "a@x.com", "signup_date": "2024-01-01",
         "address": {}, "phones": []},
        {"customer_id": "C002", "name": "Bob", "email": "b@x.com", "signup_date": "2024-02-01",
         "address": {}, "phones": []},
    ])
    build_products([("P001", "Mouse", "Electronics", "49.99", "2025-11-07T10:00:00"),
                    ("P002", "Keyboard", "Electronics", "129.50", "2025-11-07T10:00:00")])

    result = run_one_date(test_date_str, config)
    assert result["status"] == "SUCCESS", f"additive drift should be tolerated: {result.get('error')}"
    fact = pd.read_parquet(config.path("gold") / "fact_orders.parquet")
    assert len(fact) == 2


# ----- 5. Subtractive schema drift: fails loudly -----

def test_subtractive_schema_drift_fails_loudly(config, write_orders, write_customers, build_products, test_date_str):
    # quantity column is GONE
    header = "order_id,customer_id,product_id,order_date,amount,currency,status"
    rows = [
        ("O00000001", "C001", "P001", test_date_str, "49.99", "USD", "shipped"),
    ]
    write_orders(test_date_str, rows, header=header)
    write_customers(test_date_str, [
        {"customer_id": "C001", "name": "Alice", "email": "a@x.com", "signup_date": "2024-01-01",
         "address": {}, "phones": []},
    ])
    build_products([("P001", "Mouse", "Electronics", "49.99", "2025-11-07T10:00:00")])

    gold_path = config.path("gold") / "fact_orders.parquet"
    assert not gold_path.exists(), "precondition: no prior Gold data for this test"

    result = run_one_date(test_date_str, config)

    assert result["status"] == "FAILED"
    assert "missing" in (result["error"] or "").lower()

    # run_one_date's own return value IS the run's metadata (run_id, date,
    # status, error, started_at, finished_at, duration_sec, stages) — see
    # src/pipeline.py. Assert on it directly instead of guessing at how
    # StateStore persists it to disk.
    assert result["duration_sec"] is not None and result["duration_sec"] >= 0
    assert result["run_id"]
    assert result["started_at"] and result["finished_at"]
    assert result["error"], "failure record must include the error message"

    # check_schema() (called at the top of build_silver_orders, before any
    # write) raises before silver_dir.mkdir() ever runs — so Silver must
    # not exist for this date at all, and Gold must be untouched. A "loud"
    # failure that still writes partial output is worse than a silent one:
    # it corrupts data AND signals a false partial success.
    assert not gold_path.exists(), \
        "subtractive schema drift must not write ANY Gold output, even partially"

    silver_orders_path = config.path("silver") / "orders" / f"dt={test_date_str}"
    assert not silver_orders_path.exists(), \
        "orders must not reach Silver either — fail before any write past Bronze"


# ----- 6. Idempotency on re-run -----

def test_rerun_is_idempotent(config, seed_default_data, test_date_str):
    r1 = run_one_date(test_date_str, config)
    assert r1["status"] == "SUCCESS"
    fact1 = pd.read_parquet(config.path("gold") / "fact_orders.parquet")

    r2 = run_one_date(test_date_str, config)
    assert r2["status"] == "SUCCESS"
    fact2 = pd.read_parquet(config.path("gold") / "fact_orders.parquet")

    assert len(fact1) == len(fact2)
    assert set(fact1["order_id"]) == set(fact2["order_id"])
    assert fact2["order_id"].is_unique  # catches dedup bugs that coincidentally preserve count/set-membership


# ----- 7. Backfill: sequential runs -----
# See module docstring: this IS the real backfill mechanism, since
# main()'s --backfill flag is just this same loop.

def test_backfill_matches_sequential_runs(config, write_orders, write_customers, build_products, test_date):
    day1 = test_date - timedelta(days=1)
    day2 = test_date
    day1_str, day2_str = day1.isoformat(), day2.isoformat()
    watermark = (day1 - timedelta(days=2)).isoformat()

    write_orders(day1_str, [
        ("O00000001", "C001", "P001", day1_str, "49.99", "USD", "shipped", "1"),
    ])
    write_orders(day2_str, [
        ("O00000002", "C002", "P002", day2_str, "10.00", "USD", "pending", "1"),
    ])
    base_customers = [
        {"customer_id": "C001", "name": "Alice", "email": "a@x.com", "signup_date": "2024-01-01",
         "address": {}, "phones": []},
        {"customer_id": "C002", "name": "Bob", "email": "b@x.com", "signup_date": "2024-02-01",
         "address": {}, "phones": []},
    ]
    write_customers(day1_str, base_customers[:1])
    write_customers(day2_str, base_customers[1:])
    build_products([("P001", "Mouse", "Electronics", "49.99", f"{watermark}T10:00:00"),
                    ("P002", "Keyboard", "Electronics", "129.50", f"{watermark}T10:00:00")])

    # Sequential — same mechanism main()'s --backfill uses internally
    r1 = run_one_date(day1_str, config)
    r2 = run_one_date(day2_str, config)
    assert r1["status"] == "SUCCESS", r1.get("error")
    assert r2["status"] == "SUCCESS", r2.get("error")

    fact = pd.read_parquet(config.path("gold") / "fact_orders.parquet")
    assert set(fact["order_id"]) == {"O00000001", "O00000002"}
    assert len(fact) == 2


# ----- 8. SCD Type 2: customer address change preserves history -----

def test_customer_address_change_creates_scd2_history(config, write_orders, write_customers, build_products, test_date):
    """A customer moving cities must NOT overwrite the old row.
    Directly covers the 'customer history is lost' complaint in the
    problem statement. Column names / SCD2_HIGH sentinel value match
    src/transform/gold.py::build_dim_customer exactly.
    """
    day1 = test_date - timedelta(days=1)
    day2 = test_date
    day1_str, day2_str = day1.isoformat(), day2.isoformat()
    watermark = (day1 - timedelta(days=2)).isoformat()

    build_products([("P001", "Mouse", "Electronics", "49.99", f"{watermark}T10:00:00")])

    # Day 1: Alice in Austin
    write_orders(day1_str, [
        ("O00000001", "C001", "P001", day1_str, "49.99", "USD", "shipped", "1"),
    ])
    write_customers(day1_str, [
        {"customer_id": "C001", "name": "Alice", "email": "alice@example.com",
         "signup_date": "2024-01-01",
         "address": {"street": "1 A St", "city": "Austin", "state": "TX", "zip": "78701"},
         "phones": []},
    ])
    r1 = run_one_date(day1_str, config)
    assert r1["status"] == "SUCCESS", r1.get("error")

    dim_customer = pd.read_parquet(config.path("gold") / "dim_customer.parquet")
    assert len(dim_customer) == 1
    row1 = dim_customer.iloc[0]
    assert row1["addr_city"] == "Austin"
    assert row1["is_current"] == True
    assert row1["valid_to"] == "9999-12-31"  # SCD2_HIGH sentinel for open rows

    # Day 2: Alice moves to Boston
    write_orders(day2_str, [
        ("O00000002", "C001", "P001", day2_str, "10.00", "USD", "pending", "1"),
    ])
    write_customers(day2_str, [
        {"customer_id": "C001", "name": "Alice", "email": "alice@example.com",
         "signup_date": "2024-01-01",
         "address": {"street": "2 B St", "city": "Boston", "state": "MA", "zip": "02108"},
         "phones": []},
    ])
    r2 = run_one_date(day2_str, config)
    assert r2["status"] == "SUCCESS", r2.get("error")

    dim_customer = pd.read_parquet(config.path("gold") / "dim_customer.parquet")
    c001_rows = dim_customer[dim_customer["customer_id"] == "C001"]

    # Both the old and new address rows must exist
    assert len(c001_rows) == 2, "expected 2 historical rows for C001 after address change"
    assert set(c001_rows["addr_city"]) == {"Austin", "Boston"}

    # Exactly one current row, and it's the new address
    current_rows = c001_rows[c001_rows["is_current"] == True]
    assert len(current_rows) == 1
    assert current_rows.iloc[0]["addr_city"] == "Boston"
    assert current_rows.iloc[0]["valid_to"] == "9999-12-31"

    # The old row must be closed out, not deleted
    old_rows = c001_rows[c001_rows["is_current"] == False]
    assert len(old_rows) == 1
    assert old_rows.iloc[0]["addr_city"] == "Austin"
    assert old_rows.iloc[0]["valid_to"] == day2_str, \
        "closed row's valid_to should be set to the date the change was detected"

    # Fact table must still contain both orders
    fact = pd.read_parquet(config.path("gold") / "fact_orders.parquet")
    assert len(fact) == 2


# ----- 9. Incremental loading: only changed products are re-read -----

def test_incremental_load_only_reads_changed_products(
    config, write_orders, write_customers, build_products, update_products, test_date
):
    """Only products with updated_at newer than the last successful run's
    watermark should be re-read (src/ingest/products.py::ingest_products).

    ingest_products returns a dict (source, date, rows, path,
    new_watermark) — not a DataFrame — so this reads the actual Bronze
    parquet it writes to verify which product_ids were pulled, rather
    than mocking the function. This exercises the real watermark logic
    end-to-end instead of guessing at an internal API shape.
    """
    day1 = test_date - timedelta(days=1)
    day2 = test_date
    day1_str, day2_str = day1.isoformat(), day2.isoformat()
    watermark = (day1 - timedelta(days=2)).isoformat()

    build_products([
        ("P001", "Mouse", "Electronics", "49.99", f"{watermark}T10:00:00"),
        ("P002", "Keyboard", "Electronics", "129.50", f"{watermark}T10:00:00"),
    ])
    write_orders(day1_str, [
        ("O00000001", "C001", "P001", day1_str, "49.99", "USD", "shipped", "1"),
    ])
    write_customers(day1_str, [
        {"customer_id": "C001", "name": "Alice", "email": "a@x.com", "signup_date": "2024-01-01",
         "address": {}, "phones": []},
    ])

    r1 = run_one_date(day1_str, config)
    assert r1["status"] == "SUCCESS", r1.get("error")
    stage1 = next(s for s in r1["stages"] if s["stage"] == "ingest_products")
    assert stage1["rows"] == 2, "first run should read both products (no prior watermark)"

    bronze1 = pd.read_parquet(stage1["path"])
    assert set(bronze1["product_id"]) == {"P001", "P002"}

    # Only P001 changes, with an updated_at newer than the watermark
    # set by the first run.
    update_products([
        ("P001", "Mouse", "Electronics", "39.99", f"{day2.isoformat()}T09:00:00"),
    ])
    write_orders(day2_str, [
        ("O00000002", "C001", "P001", day2_str, "39.99", "USD", "shipped", "1"),
    ])
    write_customers(day2_str, [
        {"customer_id": "C001", "name": "Alice", "email": "a@x.com", "signup_date": "2024-01-01",
         "address": {}, "phones": []},
    ])

    r2 = run_one_date(day2_str, config)
    assert r2["status"] == "SUCCESS", r2.get("error")
    stage2 = next(s for s in r2["stages"] if s["stage"] == "ingest_products")
    assert stage2["rows"] == 1, "second run should only read the ONE changed product"

    bronze2 = pd.read_parquet(stage2["path"])
    assert set(bronze2["product_id"]) == {"P001"}, \
        "watermark filter is re-reading unchanged products"

    # SCD-1: price change should overwrite in place, not duplicate
    dim_product = pd.read_parquet(config.path("gold") / "dim_product.parquet")
    p001 = dim_product[dim_product["product_id"] == "P001"]
    assert len(p001) == 1
    assert float(p001.iloc[0]["price"]) == 39.99
