"""Generate sample datasets for the NovaCart pipeline lab.

Creates files for several dates so backfill and incremental loads can be demoed:
  - 2025-11-07: clean baseline
  - 2025-11-08: clean, with a few new customers + an updated product
  - 2025-11-09: deliberately contains broken rows (for quarantine demo)
  - 2025-11-10: schema drift (extra column — should warn, not fail)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANDING = PROJECT_ROOT / "data" / "landing"


# ----------- orders CSVs -----------

CLEAN_ORDERS = {
    "2025-11-07": [
        ("O00000001", "C001", "P001", "2025-11-07", "49.99",  "USD", "shipped",   "1"),
        ("O00000002", "C002", "P002", "2025-11-07", "129.50", "USD", "pending",   "2"),
        ("O00000003", "C003", "P001", "2025-11-07", "49.99",  "USD", "delivered", "1"),
        ("O00000004", "C001", "P003", "2025-11-07", "15.00",  "USD", "cancelled", "1"),
        ("O00000005", "C004", "P002", "2025-11-07", "129.50", "USD", "shipped",   "1"),
    ],
    "2025-11-08": [
        ("O00000006", "C002", "P004", "2025-11-08", "299.00", "USD", "shipped",   "1"),
        ("O00000007", "C005", "P001", "2025-11-08", "49.99",  "USD", "pending",   "1"),
        ("O00000008", "C003", "P005", "2025-11-08", "9.99",   "USD", "delivered", "3"),
        ("O00000009", "C001", "P002", "2025-11-08", "129.50", "USD", "shipped",   "1"),
    ],
    "2025-11-09": [
        # 4 good rows, 3 deliberately broken
        ("O00000010", "C002", "P001", "2025-11-09", "49.99",  "USD", "shipped",   "1"),
        ("O00000011", "C004", "P003", "2025-11-09", "15.00",  "USD", "pending",   "1"),
        ("O00000012", "C005", "P004", "2025-11-09", "299.00", "USD", "delivered", "2"),
        ("O00000013", "C003", "P002", "2025-11-09", "129.50", "USD", "shipped",   "1"),
        # BAD: negative amount
        ("O00000014", "C001", "P001", "2025-11-09", "-10.00", "USD", "shipped",   "1"),
        # BAD: unknown status
        ("O00000015", "C002", "P002", "2025-11-09", "129.50", "USD", "warped",    "1"),
        # BAD: quantity zero
        ("O00000016", "C003", "P003", "2025-11-09", "15.00",  "USD", "delivered", "0"),
    ],
    "2025-11-10": [
        # Schema drift: extra column "promotion_code" added by upstream
        ("O00000017", "C001", "P001", "2025-11-10", "49.99",  "USD", "shipped",   "1", "BLACKFRI"),
        ("O00000018", "C002", "P004", "2025-11-10", "299.00", "USD", "pending",   "1", "BLACKFRI"),
        ("O00000019", "C006", "P001", "2025-11-10", "49.99",  "USD", "shipped",   "1", ""),
    ],
}


def write_orders_csv(date_str: str, rows: list[tuple]) -> Path:
    out_dir = LANDING / "orders"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"orders_{date_str}.csv"

    if date_str == "2025-11-10":
        header = "order_id,customer_id,product_id,order_date,amount,currency,status,quantity,promotion_code"
    else:
        header = "order_id,customer_id,product_id,order_date,amount,currency,status,quantity"

    with out_path.open("w", encoding="utf-8") as f:
        f.write(header + "\n")
        for r in rows:
            f.write(",".join(r) + "\n")
    return out_path


# ----------- customer JSON -----------

CLEAN_CUSTOMERS = {
    "2025-11-07": [
        {"customer_id": "C001", "name": "Alice Johnson", "email": "alice@example.com",
         "signup_date": "2024-03-15",
         "address": {"street": "123 Maple St", "city": "Austin", "state": "TX", "zip": "78701"},
         "phones": ["+1-555-0100"]},
        {"customer_id": "C002", "name": "Bob Smith", "email": "bob@example.com",
         "signup_date": "2024-05-22",
         "address": {"street": "45 Oak Ave", "city": "Denver", "state": "CO", "zip": "80202"},
         "phones": ["+1-555-0200", "+1-555-0201"]},
        {"customer_id": "C003", "name": "Carol Davis", "email": "carol@example.com",
         "signup_date": "2024-07-01",
         "address": {"street": "9 Pine Rd", "city": "Seattle", "state": "WA", "zip": "98101"},
         "phones": ["+1-555-0300"]},
        {"customer_id": "C004", "name": "David Lee", "email": "david@example.com",
         "signup_date": "2024-09-10",
         "address": {"street": "55 Birch Ln", "city": "Boston", "state": "MA", "zip": "02108"},
         "phones": []},
    ],
    "2025-11-08": [
        # C002 moved cities (SCD-2 should track this)
        {"customer_id": "C002", "name": "Bob Smith", "email": "bob@example.com",
         "signup_date": "2024-05-22",
         "address": {"street": "200 Cherry St", "city": "Portland", "state": "OR", "zip": "97201"},
         "phones": ["+1-555-0200", "+1-555-0201"]},
        # New customer
        {"customer_id": "C005", "name": "Eve Martinez", "email": "EVE@example.com",
         "signup_date": "2025-11-08",
         "address": {"street": "777 Cedar Way", "city": "Miami", "state": "FL", "zip": "33101"},
         "phones": ["+1-555-0500"]},
    ],
    "2025-11-09": [
        # 1 good, 2 bad
        {"customer_id": "C006", "name": "Frank Wright", "email": "frank@example.com",
         "signup_date": "2025-11-09",
         "address": {"street": "12 Elm Ct", "city": "Chicago", "state": "IL", "zip": "60601"},
         "phones": ["+1-555-0600"]},
        # BAD: invalid email
        {"customer_id": "C007", "name": "Grace Bad", "email": "not-an-email",
         "signup_date": "2025-11-09", "address": {}, "phones": []},
        # BAD: missing required field "name"
        {"customer_id": "C008", "email": "henry@example.com", "signup_date": "2025-11-09",
         "address": {}, "phones": []},
    ],
    "2025-11-10": [
        {"customer_id": "C009", "name": "Iris Khan", "email": "iris@example.com",
         "signup_date": "2025-11-10",
         "address": {"street": "88 Willow Dr", "city": "Atlanta", "state": "GA", "zip": "30301"},
         "phones": ["+1-555-0900"]},
    ],
}


def write_customers_json(date_str: str, records: list[dict]) -> Path:
    out_dir = LANDING / "customers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"customers_{date_str}.json"
    out_path.write_text(json.dumps(records, indent=2))
    return out_path


# ----------- products SQLite -----------

INITIAL_PRODUCTS = [
    ("P001", "Wireless Mouse",       "Electronics",  "49.99",  "2025-11-07T10:00:00"),
    ("P002", "Mechanical Keyboard",  "Electronics",  "129.50", "2025-11-07T10:00:00"),
    ("P003", "USB-C Cable 2m",       "Accessories",  "15.00",  "2025-11-07T10:00:00"),
    ("P004", "27\" Monitor",         "Electronics",  "299.00", "2025-11-07T10:00:00"),
    ("P005", "Notebook A5",          "Stationery",   "9.99",   "2025-11-07T10:00:00"),
]

PRODUCT_UPDATES = [
    # P001 price drop (SCD-1: overwrite)
    ("P001", "Wireless Mouse",       "Electronics",  "44.99",  "2025-11-08T08:00:00"),
    # New product
    ("P006", "Webcam HD",            "Electronics",  "79.00",  "2025-11-08T08:00:00"),
]


def build_products_db() -> Path:
    db_path = LANDING / "products.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE products (
            product_id  TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            category    TEXT NOT NULL,
            price       TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", INITIAL_PRODUCTS)
    conn.commit()
    conn.close()
    return db_path


def apply_product_updates() -> None:
    """Simulate upstream updates that move the watermark forward."""
    db_path = LANDING / "products.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for row in PRODUCT_UPDATES:
        cur.execute(
            "INSERT OR REPLACE INTO products (product_id, name, category, price, updated_at) VALUES (?, ?, ?, ?, ?)",
            row,
        )
    conn.commit()
    conn.close()


# ----------- runner -----------

def generate_all(*, only_initial: bool = False) -> None:
    LANDING.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {LANDING}")

    # Orders + customers
    dates_to_write = ["2025-11-07"] if only_initial else list(CLEAN_ORDERS.keys())
    for d in dates_to_write:
        p1 = write_orders_csv(d, CLEAN_ORDERS[d])
        p2 = write_customers_json(d, CLEAN_CUSTOMERS[d])
        print(f"  orders    -> {p1.name}")
        print(f"  customers -> {p2.name}")

    # Products DB
    db = build_products_db()
    print(f"  products  -> {db.name} (initial: {len(INITIAL_PRODUCTS)} rows)")

    if not only_initial:
        apply_product_updates()
        print(f"  products  -> applied {len(PRODUCT_UPDATES)} updates (new watermark)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate sample data for the NovaCart pipeline")
    parser.add_argument("--initial-only", action="store_true",
                        help="Only generate the 2025-11-07 baseline (for the first run demo)")
    args = parser.parse_args(argv)
    generate_all(only_initial=args.initial_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
