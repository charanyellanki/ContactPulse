"""Order repository — BigQuery-backed.

CLAUDE.md §6: BigQuery access lives only in repositories. The OrderStatusAgent
calls `recent_orders_for_customer` and never sees raw SQL.
"""
from __future__ import annotations

from functools import lru_cache
from typing import cast

from fastapi import Depends
from google.cloud import bigquery

from backend.models.order import Order, OrderStatus
from backend.repositories.bigquery_client import fq, get_bq_client


def _ts(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _row_to_order(row: bigquery.Row) -> Order:
    return Order(
        order_id=row["order_id"],
        customer_id=row["customer_id"],
        sku=row["sku"],
        product_name=row["product_name"],
        quantity=int(row["quantity"]),
        status=cast(OrderStatus, row["status"]),
        order_date=cast(str, _ts(row["order_date"])),
        eta=_ts(row["eta"]),
        tracking_no=row["tracking_no"],
    )


_RECENT_ORDERS_SQL = f"""
SELECT order_id, customer_id, sku, product_name, quantity, status,
       order_date, eta, tracking_no
FROM {fq('orders')}
WHERE customer_id = @customer_id
ORDER BY order_date DESC
LIMIT 3
"""

_GET_ORDER_SQL = f"""
SELECT order_id, customer_id, sku, product_name, quantity, status,
       order_date, eta, tracking_no
FROM {fq('orders')}
WHERE order_id = @order_id
LIMIT 1
"""


class OrderRepository:
    def __init__(self, client: bigquery.Client) -> None:
        self._client = client

    def recent_orders_for_customer(self, customer_id: str) -> list[Order]:
        cfg = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id)
            ]
        )
        rows = self._client.query(_RECENT_ORDERS_SQL, job_config=cfg).result()
        return [_row_to_order(r) for r in rows]

    def get_order(self, order_id: str) -> Order | None:
        cfg = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("order_id", "STRING", order_id)
            ]
        )
        rows = list(self._client.query(_GET_ORDER_SQL, job_config=cfg).result())
        return _row_to_order(rows[0]) if rows else None


@lru_cache(maxsize=1)
def _cached_repo(client: bigquery.Client) -> OrderRepository:
    return OrderRepository(client)


def get_order_repo(client: bigquery.Client = Depends(get_bq_client)) -> OrderRepository:
    return _cached_repo(client)
