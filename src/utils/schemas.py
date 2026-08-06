"""Pydantic schemas — the contract between source systems and our pipeline."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


ALLOWED_STATUSES = {"pending", "shipped", "delivered", "cancelled"}


class OrderRecord(BaseModel):
    """One validated order. Anything that doesn't match this goes to quarantine."""

    order_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    order_date: date
    amount: Decimal = Field(..., ge=Decimal("0"))
    currency: str = Field(..., min_length=3, max_length=3)
    status: str
    quantity: int = Field(..., ge=1)

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, v: str) -> str:
        v_lower = v.strip().lower()
        if v_lower not in ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {ALLOWED_STATUSES}, got {v!r}")
        return v_lower

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("order_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            v = v.strip()
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"unparseable date: {v!r}")
        raise ValueError(f"unsupported date type: {type(v)}")


class CustomerAddress(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class CustomerRecord(BaseModel):
    customer_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    email: EmailStr
    signup_date: date
    address: CustomerAddress = Field(default_factory=CustomerAddress)
    phones: list[str] = Field(default_factory=list)

    @field_validator("email", mode="before")
    @classmethod
    def lower_email(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class ProductRecord(BaseModel):
    product_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str
    price: Decimal = Field(..., ge=Decimal("0"))
    updated_at: datetime


# Expected columns at the Bronze layer (used for schema-drift detection).
EXPECTED_COLUMNS = {
    "orders": {"order_id", "customer_id", "product_id", "order_date", "amount", "currency", "status", "quantity"},
    "customers": {"customer_id", "name", "email", "signup_date", "address", "phones"},
    "products": {"product_id", "name", "category", "price", "updated_at"},
}
