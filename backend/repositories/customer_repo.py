"""Customer repository — BigQuery-backed.

Reads from `customers_context`. The display label (`Cust #<id> · <Tier>`) is
derived at read time so it never has to be persisted, which keeps the storage
schema PII-poor: no name/email/phone columns at all.
"""
from __future__ import annotations

from functools import lru_cache
from typing import cast

from fastapi import Depends
from google.cloud import bigquery

from backend.models.common import Journey, LoyaltyTier
from backend.models.customer import Customer
from backend.repositories.bigquery_client import fq, get_bq_client


def _display_label(customer_id: str, tier: str) -> str:
    return f"Cust #{customer_id} · {tier.title()}"


def _row_to_customer(row: bigquery.Row) -> Customer:
    return Customer(
        customer_id=row["customer_id"],
        display_label=_display_label(row["customer_id"], row["tier"]),
        tier=cast(LoyaltyTier, row["tier"]),
        lifetime_value_usd=float(row["lifetime_value"]),
        open_orders=int(row["open_orders"]),
        recent_journey=cast("Journey | None", row["recent_journey"]),
    )


class CustomerRepository:
    """Thin wrapper around the BigQuery client for `customers_context`."""

    def __init__(self, client: bigquery.Client) -> None:
        self._client = client

    def list_customers(self) -> list[Customer]:
        sql = f"SELECT customer_id, tier, lifetime_value, open_orders, recent_journey FROM {fq('customers_context')} ORDER BY customer_id"
        return [_row_to_customer(r) for r in self._client.query(sql).result()]

    def get_customer(self, customer_id: str) -> Customer | None:
        sql = (
            f"SELECT customer_id, tier, lifetime_value, open_orders, recent_journey "
            f"FROM {fq('customers_context')} WHERE customer_id = @customer_id LIMIT 1"
        )
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id)]
        )
        rows = list(self._client.query(sql, job_config=cfg).result())
        return _row_to_customer(rows[0]) if rows else None


@lru_cache(maxsize=1)
def _cached_repo(client: bigquery.Client) -> CustomerRepository:
    return CustomerRepository(client)


def get_customer_repo(client: bigquery.Client = Depends(get_bq_client)) -> CustomerRepository:
    return _cached_repo(client)
