"""Customer repository — fixture-backed stub.

Real implementation will project from the BigQuery `customers` table after
DLP redaction at the data boundary (no name/email/phone reach this layer).
"""
from __future__ import annotations

from backend.fixtures import CUSTOMERS
from backend.models.customer import Customer


def list_customers() -> list[Customer]:
    return list(CUSTOMERS)


def get_customer(customer_id: str) -> Customer | None:
    return next((c for c in CUSTOMERS if c.customer_id == customer_id), None)
