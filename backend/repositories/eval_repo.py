"""Eval-run repository — BigQuery-backed.

The storage schema (`eval_runs`) is one row per run with metrics as columns.
The API contract is `EvalRunSummary` (a `primary_metrics` dict) plus, on
detail, `per_journey` task-success rows and a long-format `rows` array. This
module owns the wide → long expansion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends
from google.cloud import bigquery

from backend.models.common import Journey
from backend.models.eval import (
    EvalRunDetail,
    EvalRunMetricRow,
    EvalRunPerJourney,
    EvalRunPrimaryMetrics,
    EvalRunSummary,
)
from backend.repositories.bigquery_client import fq, get_bq_client


# Columns absent from the simplified storage schema. Surface stable defaults
# so the API contract — and the frontend — keeps working until the eval
# harness lands and writes the full long-format table.
_DEFAULT_TOTAL_QUERIES = 150
_DEFAULT_CONFIG_HASH = "cfg_default"

_PER_JOURNEY_QUERY_SHARES: dict[Journey, float] = {
    "order_status":    0.40,
    "product_qa":      0.35,
    "service_request": 0.25,
}


def _ts(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _row_to_summary(row: bigquery.Row) -> EvalRunSummary:
    metrics = EvalRunPrimaryMetrics(
        containment=float(row["containment_rate"]),
        refusal_precision=float(row["refusal_precision"]),
        intent_accuracy=float(row["intent_accuracy"]),
        retrieval_hit_rate_at_5=float(row["retrieval_hit_rate"]),
        hallucination_rate_post_verifier=float(row["hallucination_rate"]),
        latency_p95_ms=int(row["latency_p95_ms"]),
        cost_per_call_usd=float(row["cost_per_call_usd"]),
    )
    return EvalRunSummary(
        run_id=row["run_id"],
        run_timestamp=_ts(row["created_at"]),
        git_sha=row["git_sha"],
        config_hash=_DEFAULT_CONFIG_HASH,
        total_queries=_DEFAULT_TOTAL_QUERIES,
        primary_metrics=metrics,
    )


def _expand_to_detail(row: bigquery.Row, summary: EvalRunSummary) -> EvalRunDetail:
    per_journey: list[EvalRunPerJourney] = [
        EvalRunPerJourney(
            journey="order_status",
            task_success=float(row["task_success_order_status"]),
            query_count=int(round(summary.total_queries * _PER_JOURNEY_QUERY_SHARES["order_status"])),
        ),
        EvalRunPerJourney(
            journey="product_qa",
            task_success=float(row["task_success_product_qa"]),
            query_count=int(round(summary.total_queries * _PER_JOURNEY_QUERY_SHARES["product_qa"])),
        ),
        EvalRunPerJourney(
            journey="service_request",
            task_success=float(row["task_success_service_request"]),
            query_count=int(round(summary.total_queries * _PER_JOURNEY_QUERY_SHARES["service_request"])),
        ),
    ]

    pm = summary.primary_metrics
    long_rows: list[EvalRunMetricRow] = []
    flat_metrics: list[tuple[str, float]] = [
        ("containment", pm.containment),
        ("refusal_precision", pm.refusal_precision),
        ("intent_accuracy", pm.intent_accuracy),
        ("retrieval_hit_rate_at_5", pm.retrieval_hit_rate_at_5),
        ("hallucination_rate_post_verifier", pm.hallucination_rate_post_verifier),
        ("latency_p95_ms", float(pm.latency_p95_ms)),
        ("cost_per_call_usd", pm.cost_per_call_usd),
    ]
    for metric_name, value in flat_metrics:
        long_rows.append(
            EvalRunMetricRow(
                run_id=summary.run_id,
                run_timestamp=summary.run_timestamp,
                git_sha=summary.git_sha,
                config_hash=summary.config_hash,
                metric_name=metric_name,
                metric_value=value,
                journey=None,
            )
        )
    for entry in per_journey:
        long_rows.append(
            EvalRunMetricRow(
                run_id=summary.run_id,
                run_timestamp=summary.run_timestamp,
                git_sha=summary.git_sha,
                config_hash=summary.config_hash,
                metric_name="task_success",
                metric_value=entry.task_success,
                journey=entry.journey,
            )
        )

    return EvalRunDetail(
        **summary.model_dump(),
        per_journey=per_journey,
        rows=long_rows,
    )


_LIST_SQL = f"""
SELECT *
FROM {fq('eval_runs')}
ORDER BY created_at DESC
"""

_GET_SQL = f"""
SELECT *
FROM {fq('eval_runs')}
WHERE run_id = @run_id
LIMIT 1
"""


class EvalRunRepository:
    def __init__(self, client: bigquery.Client) -> None:
        self._client = client

    def list_eval_runs(self) -> list[EvalRunSummary]:
        return [_row_to_summary(r) for r in self._client.query(_LIST_SQL).result()]

    def get_eval_run(self, run_id: str) -> EvalRunDetail | None:
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
        )
        rows = list(self._client.query(_GET_SQL, job_config=cfg).result())
        if not rows:
            return None
        row = rows[0]
        summary = _row_to_summary(row)
        return _expand_to_detail(row, summary)


@lru_cache(maxsize=1)
def _cached_repo(client: bigquery.Client) -> EvalRunRepository:
    return EvalRunRepository(client)


def get_eval_repo(client: bigquery.Client = Depends(get_bq_client)) -> EvalRunRepository:
    return _cached_repo(client)
