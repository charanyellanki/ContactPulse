"""Eval-run repository — fixture-backed stub.

Real implementation will read the BigQuery `eval_runs` long-format table per
ARCHITECTURE.md §5 and aggregate to summaries / details. Per-journey and
long-format rows are synthesized here from the primary metrics until the
real harness writes them.
"""
from __future__ import annotations

from backend.fixtures import EVAL_RUNS
from backend.models.common import Journey
from backend.models.eval import (
    EvalRunDetail,
    EvalRunMetricRow,
    EvalRunPerJourney,
    EvalRunSummary,
)


_JOURNEY_TASK_SUCCESS_OFFSETS: dict[Journey, float] = {
    "order_status": 0.05,
    "product_qa": -0.02,
    "service_request": -0.08,
    "escalate": 0.0,
    "out_of_scope": 0.0,
}

_JOURNEY_QUERY_COUNT_SHARES: dict[Journey, float] = {
    "order_status": 0.40,
    "product_qa": 0.35,
    "service_request": 0.18,
    "escalate": 0.04,
    "out_of_scope": 0.03,
}


def list_eval_runs() -> list[EvalRunSummary]:
    return list(EVAL_RUNS)


def get_eval_run(run_id: str) -> EvalRunDetail | None:
    summary = next((r for r in EVAL_RUNS if r.run_id == run_id), None)
    if summary is None:
        return None
    return _expand_to_detail(summary)


def _expand_to_detail(summary: EvalRunSummary) -> EvalRunDetail:
    pm = summary.primary_metrics
    base_success = pm.intent_accuracy

    per_journey: list[EvalRunPerJourney] = []
    for journey, offset in _JOURNEY_TASK_SUCCESS_OFFSETS.items():
        if journey in ("escalate", "out_of_scope"):
            continue
        success = max(0.0, min(1.0, base_success + offset))
        share = _JOURNEY_QUERY_COUNT_SHARES[journey]
        per_journey.append(
            EvalRunPerJourney(
                journey=journey,
                task_success=round(success, 3),
                query_count=int(round(summary.total_queries * share)),
            )
        )

    rows: list[EvalRunMetricRow] = []
    for metric_name, value in (
        ("containment", pm.containment),
        ("refusal_precision", pm.refusal_precision),
        ("intent_accuracy", pm.intent_accuracy),
        ("retrieval_hit_rate_at_5", pm.retrieval_hit_rate_at_5),
        ("hallucination_rate_post_verifier", pm.hallucination_rate_post_verifier),
        ("latency_p95_ms", float(pm.latency_p95_ms)),
        ("cost_per_call_usd", pm.cost_per_call_usd),
    ):
        rows.append(
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
        rows.append(
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
        rows=rows,
    )
