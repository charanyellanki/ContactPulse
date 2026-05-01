"""Eval-run models. Long-format BigQuery rows + aggregated summaries."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .common import Journey


class EvalRunMetricRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_timestamp: str
    git_sha: str
    config_hash: str
    metric_name: str
    metric_value: float
    journey: Journey | None


class EvalRunPrimaryMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    containment: float
    refusal_precision: float
    intent_accuracy: float
    retrieval_hit_rate_at_5: float
    hallucination_rate_post_verifier: float
    latency_p95_ms: int
    cost_per_call_usd: float


class EvalRunPerJourney(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journey: Journey
    task_success: float
    query_count: int


class EvalRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_timestamp: str
    git_sha: str
    config_hash: str
    total_queries: int
    primary_metrics: EvalRunPrimaryMetrics


class EvalRunDetail(EvalRunSummary):
    per_journey: list[EvalRunPerJourney]
    rows: list[EvalRunMetricRow]
