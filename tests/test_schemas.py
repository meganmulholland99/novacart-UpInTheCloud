"""Unit tests for the schema layer."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.utils.schemas import CustomerRecord, OrderRecord, ProductRecord


def test_order_record_happy_path():
    r = OrderRecord(
        order_id="O1", customer_id="C1", product_id="P1",
        order_date="2025-11-09", amount="49.99", currency="usd",
        status="Shipped", quantity=1,
    )
    assert r.status == "shipped"
    assert r.currency == "USD"
    assert r.amount == Decimal("49.99")


def test_order_record_rejects_negative_amount():
    with pytest.raises(ValidationError):
        OrderRecord(order_id="O1", customer_id="C1", product_id="P1",
                    order_date="2025-11-09", amount="-1", currency="USD",
                    status="shipped", quantity=1)


def test_order_record_rejects_unknown_status():
    with pytest.raises(ValidationError):
        OrderRecord(order_id="O1", customer_id="C1", product_id="P1",
                    order_date="2025-11-09", amount="1", currency="USD",
                    status="warped", quantity=1)


def test_order_record_parses_alternate_date_formats():
    r1 = OrderRecord(order_id="O1", customer_id="C1", product_id="P1",
                     order_date="11/09/2025", amount="1", currency="USD",
                     status="shipped", quantity=1)
    r2 = OrderRecord(order_id="O1", customer_id="C1", product_id="P1",
                     order_date="2025/11/09", amount="1", currency="USD",
                     status="shipped", quantity=1)
    assert r1.order_date.isoformat() == "2025-11-09"
    assert r2.order_date.isoformat() == "2025-11-09"


def test_customer_record_lowers_email():
    c = CustomerRecord(customer_id="C1", name="Alice", email="ALICE@X.COM",
                       signup_date="2024-01-01")
    assert c.email == "alice@x.com"


def test_customer_record_rejects_bad_email():
    with pytest.raises(ValidationError):
        CustomerRecord(customer_id="C1", name="Alice", email="not-an-email",
                       signup_date="2024-01-01")


def test_product_record_happy_path():
    p = ProductRecord(product_id="P1", name="Mouse", category="Electronics",
                      price="49.99", updated_at="2025-11-09T10:00:00")
    assert p.price == Decimal("49.99")
