"""Eval-run models. Long-format BigQuery rows + aggregated summaries."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .common import Journey

# 'golden' = curated test set with labels (intent_accuracy / refusal_precision /
# retrieval_hit_rate are populated). 'production' = sampled live conversations
# without labels (those metrics are null on the wire).
EvalRunSource = Literal["golden", "production"]
SampleModality = Literal["voice", "chat", "all"]


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
    # Label-dependent metrics — null on production rows because production
    # conversations have no ground truth.
    refusal_precision: float | None
    intent_accuracy: float | None
    retrieval_hit_rate_at_5: float | None
    hallucination_rate_post_verifier: float | None
    latency_p95_ms: int | None
    cost_per_call_usd: float | None


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
    # Source classifier — drives Operator Console badge + filtering.
    source: EvalRunSource = "golden"
    sample_modality: SampleModality | None = None
    primary_metrics: EvalRunPrimaryMetrics


class EvalRunDetail(EvalRunSummary):
    per_journey: list[EvalRunPerJourney]
    rows: list[EvalRunMetricRow]
