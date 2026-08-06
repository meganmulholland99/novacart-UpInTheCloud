"""Shared pytest fixtures. Each test gets an isolated tmp project root."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

# Make `src` importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import Config  # noqa: E402


def _write_yaml_config(project_dir: Path) -> Path:
    cfg = {
        "pipeline": {"name": "novacart_etl_test", "environment": "test"},
        "paths": {
            "landing": "data/landing",
            "bronze": "data/bronze",
            "silver": "data/silver",
            "gold": "data/gold",
            "quarantine": "data/quarantine",
            "state": "state",
            "logs": "logs",
        },
        "sources": {
            "orders": {
                "landing_dir": "data/landing/orders",
                "file_pattern": "orders_{date}.csv",
                "encoding_primary": "utf-8",
                "encoding_fallback": "latin-1",
            },
            "customers": {
                "landing_dir": "data/landing/customers",
                "file_pattern": "customers_{date}.json",
            },
            "products": {
                "db_path": "data/landing/products.db",
                "table": "products",
                "watermark_column": "updated_at",
            },
        },
        "quality": {
            "hard": {"require_non_empty": True,
                     "primary_keys": {"orders": "order_id", "customers": "customer_id", "products": "product_id"}},
            "soft": {"row_count_drop_pct": 30, "email_invalid_pct": 5,
                     "allowed_statuses": ["pending", "shipped", "delivered", "cancelled"]},
        },
        "retry": {"max_attempts": 3, "backoff_seconds": 1},
        "logging": {"level": "WARNING", "json": True},
    }
    cfg_path = project_dir / "config" / "pipeline.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(cfg))
    return cfg_path


def _write_orders_csv(project_dir: Path, date: str, rows: list[tuple], header: str | None = None) -> Path:
    if header is None:
        header = "order_id,customer_id,product_id,order_date,amount,currency,status,quantity"
    out_dir = project_dir / "data" / "landing" / "orders"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"orders_{date}.csv"
    with p.open("w") as f:
        f.write(header + "\n")
        for r in rows:
            f.write(",".join(r) + "\n")
    return p


def _write_customers_json(project_dir: Path, date: str, records: list[dict[str, Any]]) -> Path:
    out_dir = project_dir / "data" / "landing" / "customers"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"customers_{date}.json"
    p.write_text(json.dumps(records))
    return p


def _build_products_db(project_dir: Path, rows: list[tuple]) -> Path:
    db_path = project_dir / "data" / "landing" / "products.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE products (
        product_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
        price TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Fresh isolated project root with config but no data."""
    for d in ["config", "data/landing/orders", "data/landing/customers",
              "data/bronze", "data/silver", "data/gold", "data/quarantine",
              "state", "logs"]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    _write_yaml_config(tmp_path)
    return tmp_path


@pytest.fixture
def config(project_dir: Path) -> Config:
    cfg = Config.load(project_dir / "config" / "pipeline.yaml")
    cfg.root = project_dir  # ensure paths resolve under the temp dir
    return cfg


@pytest.fixture
def write_orders(project_dir: Path):
    def _w(date: str, rows: list[tuple], header: str | None = None) -> Path:
        return _write_orders_csv(project_dir, date, rows, header)
    return _w


@pytest.fixture
def write_customers(project_dir: Path):
    def _w(date: str, records: list[dict[str, Any]]) -> Path:
        return _write_customers_json(project_dir, date, records)
    return _w


@pytest.fixture
def build_products(project_dir: Path):
    def _w(rows: list[tuple]) -> Path:
        return _build_products_db(project_dir, rows)
    return _w


@pytest.fixture
def update_products(project_dir: Path):
    """Update/insert product rows in place (no table drop), so tests can
    simulate 'the source changed between two pipeline runs' without
    destroying the existing watermark state. Needed by ingest_products'
    watermark-based incremental load (src/ingest/products.py)."""
    def _u(rows: list[tuple]) -> Path:
        db_path = project_dir / "data" / "landing" / "products.db"
        conn = sqlite3.connect(db_path)
        conn.executemany(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(product_id) DO UPDATE SET "
            "name=excluded.name, category=excluded.category, "
            "price=excluded.price, updated_at=excluded.updated_at",
            rows,
        )
        conn.commit()
        conn.close()
        return db_path
    return _u


@pytest.fixture
def test_date() -> date:
    """Single source of truth for 'the date under test'. Computed relative
    to today (not hardcoded) so the suite doesn't go stale and actually
    proves the pipeline works for arbitrary dates, not just Nov 2025."""
    return date.today() - timedelta(days=30)


@pytest.fixture
def test_date_str(test_date: date) -> str:
    return test_date.isoformat()


# ----- shared default rows -----

def _default_orders(date_str: str) -> list[tuple]:
    return [
        ("O00000001", "C001", "P001", date_str, "49.99",  "USD", "shipped",   "1"),
        ("O00000002", "C002", "P002", date_str, "129.50", "USD", "pending",   "1"),
        ("O00000003", "C003", "P001", date_str, "49.99",  "USD", "delivered", "2"),
    ]


DEFAULT_CUSTOMERS = [
    {"customer_id": "C001", "name": "Alice", "email": "alice@example.com",
     "signup_date": "2024-01-01",
     "address": {"street": "1 A St", "city": "Austin", "state": "TX", "zip": "78701"},
     "phones": ["+1-555-0100"]},
    {"customer_id": "C002", "name": "Bob", "email": "bob@example.com",
     "signup_date": "2024-02-01",
     "address": {"street": "2 B St", "city": "Boston", "state": "MA", "zip": "02108"}, "phones": []},
    {"customer_id": "C003", "name": "Carol", "email": "carol@example.com",
     "signup_date": "2024-03-01",
     "address": {"street": "3 C St", "city": "Chicago", "state": "IL", "zip": "60601"}, "phones": []},
]


def _default_products(date_str: str) -> list[tuple]:
    # Watermark derived as "2 days before the order date" instead of
    # hand-copied, so the relationship holds no matter what date_str is.
    watermark = (date.fromisoformat(date_str) - timedelta(days=2)).isoformat()
    return [
        ("P001", "Mouse", "Electronics", "49.99", f"{watermark}T10:00:00"),
        ("P002", "Keyboard", "Electronics", "129.50", f"{watermark}T10:00:00"),
    ]


@pytest.fixture
def seed_default_data(write_orders, write_customers, build_products, test_date_str):
    write_orders(test_date_str, _default_orders(test_date_str))
    write_customers(test_date_str, DEFAULT_CUSTOMERS)
    build_products(_default_products(test_date_str))
    return test_date_str
