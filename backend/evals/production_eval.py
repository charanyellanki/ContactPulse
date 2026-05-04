"""Production batch eval — sample real conversations from BigQuery, judge
them with the same LLM-as-judge rubric the golden-set runner uses, and
write a single `eval_runs` row tagged `source='production'`.

Design notes
------------
1. **Why batch, not stream.** Online eval against every turn is ~3× the
   inference cost and busts the voice latency budget. Industry standard is
   batch over a sample (random or stratified). See Vertex AI Conversational
   Insights: it ingests transcripts to BQ and runs scheduled analyses.

2. **Why no ground truth.** Production conversations carry the agent's
   *behavior* (intent picked, response, derived outcome) but not the
   *correct* answer. So label-dependent metrics (intent_accuracy,
   retrieval_hit_rate, refusal_precision) are NULL on production rows. The
   judge can still rate task_success / hallucination / tone with no labels;
   containment_rate / escalation_rate / latency / cost come from telemetry.

3. **Reconstruction.** Each conversation lives in two tables:
     - `conversations`        — one summary row (modality, journey, outcome,
                                cost, latency)
     - `conversation_traces`  — many event rows (`user_message`,
                                `agent_response`, etc.)
   We pick the user_message text + the final agent_response text from the
   trace events and feed those into the judge as (utterance, response_text).

4. **Async-safe.** The route invokes `run_production_batch_async()` via
   `BackgroundTasks`. Any failure is logged and surfaced via the eval row
   never appearing rather than a 500.
"""
from __future__ import annotations

import logging
import statistics
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Literal

from google.cloud import bigquery

from backend.config import get_settings
from backend.evals.eval_runner import (
    QueryResult,
    _OUTCOME_NORMALIZE,
    _journey_task_success,
    _judge,
    _safe_div,
)
from backend.repositories.bigquery_client import fq, get_bq_client

log = logging.getLogger(__name__)

ModalityFilter = Literal["voice", "chat", "all"]


# ─── Sample loader ─────────────────────────────────────────────────────────


@dataclass
class _ProductionTurn:
    """A reconstructed turn ready to feed into the LLM-as-judge."""
    trace_id:        str
    modality:        str
    journey:         str
    outcome:         str
    utterance:       str
    response_text:   str
    confidence:      float
    grounded:        bool
    escalate:        bool
    latency_ms:      int
    cost_usd:        float


# Cutoff lookup — find the most recent production batch eval that "covered"
# the requested modality:
#   - asking 'voice'  → prior 'voice' or 'all' run is a cutoff
#   - asking 'chat'   → prior 'chat' or 'all' run is a cutoff
#   - asking 'all'    → only a prior 'all' run is a cutoff (a voice run
#                       didn't cover chat traffic, so it can't bound an 'all'
#                       request)
# This avoids re-judging conversations a prior run already evaluated.
_LAST_RUN_SQL = f"""
SELECT MAX(created_at) AS last_at
FROM {fq('eval_runs')}
WHERE source = 'production'
  AND (
    sample_modality = @modality
    OR sample_modality = 'all'
    OR @modality = 'all'
  )
"""

# Incremental sample: conversations created after the cutoff (most recent
# production batch run). The cutoff is computed inline so we get a single
# round trip; falls back to a `since_hours` rolling window when no prior
# production batch exists yet (cold start).
_INCREMENTAL_SAMPLE_SQL = f"""
WITH cutoff AS (
  SELECT
    COALESCE(
      (
        SELECT MAX(created_at)
        FROM {fq('eval_runs')}
        WHERE source = 'production'
          AND (
            sample_modality = @modality
            OR (@modality != 'all' AND sample_modality = 'all')
          )
      ),
      TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @since_hours HOUR)
    ) AS since_at
),
candidates AS (
  SELECT trace_id, modality, customer_id, tier, journey, outcome,
         turns, latency_p50_ms, cost_usd, created_at
  FROM {fq('conversations')}
  WHERE created_at > (SELECT since_at FROM cutoff)
    AND (@modality = 'all' OR modality = @modality)
),
sample AS (
  SELECT * FROM candidates
  ORDER BY RAND()
  LIMIT @sample_size
)
SELECT s.*,
       u.input_text  AS utterance,
       a.output_text AS response_text,
       JSON_VALUE(r.metadata, '$.confidence') AS router_confidence,
       JSON_VALUE(v.metadata, '$.verdict')    AS verifier_verdict
FROM sample s
LEFT JOIN (
  SELECT trace_id, ANY_VALUE(input_text) AS input_text
  FROM {fq('conversation_traces')}
  WHERE event_type = 'user_message'
  GROUP BY trace_id
) u USING (trace_id)
LEFT JOIN (
  SELECT trace_id, ANY_VALUE(output_text) AS output_text
  FROM {fq('conversation_traces')}
  WHERE event_type = 'agent_response'
  GROUP BY trace_id
) a USING (trace_id)
LEFT JOIN (
  SELECT trace_id, ANY_VALUE(metadata) AS metadata
  FROM {fq('conversation_traces')}
  WHERE event_type = 'intent_routing'
  GROUP BY trace_id
) r USING (trace_id)
LEFT JOIN (
  SELECT trace_id, ANY_VALUE(metadata) AS metadata
  FROM {fq('conversation_traces')}
  WHERE event_type = 'grounding_verification'
  GROUP BY trace_id
) v USING (trace_id)
"""

# Preview query — just the count + cutoff timestamp so the UI can render
# "12 new voice conversations since 2026-05-04 14:24" before the user clicks.
_PREVIEW_SQL = f"""
WITH cutoff AS (
  SELECT
    COALESCE(
      (
        SELECT MAX(created_at)
        FROM {fq('eval_runs')}
        WHERE source = 'production'
          AND (
            sample_modality = @modality
            OR (@modality != 'all' AND sample_modality = 'all')
          )
      ),
      TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @since_hours HOUR)
    ) AS since_at
)
SELECT
  (SELECT since_at FROM cutoff) AS since_at,
  (SELECT COUNT(*) FROM {fq('conversations')}
     WHERE created_at > (SELECT since_at FROM cutoff)
       AND (@modality = 'all' OR modality = @modality)) AS new_count
"""


def preview_incremental(
    *, modality: ModalityFilter, since_hours: int = 168
) -> dict:
    """Cheap count-only query — drives the UI's 'N new <modality> turns
    since <timestamp>' callout. Costs effectively nothing."""
    client = get_bq_client()
    cfg = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("modality",    "STRING", modality),
            bigquery.ScalarQueryParameter("since_hours", "INT64", int(since_hours)),
        ]
    )
    row = next(iter(client.query(_PREVIEW_SQL, job_config=cfg).result()))
    since_at = row["since_at"]
    return {
        "since_at": since_at.isoformat() if since_at else None,
        "new_count": int(row["new_count"] or 0),
        "modality": modality,
    }


def load_production_sample(
    *,
    sample_size: int,
    modality: ModalityFilter,
    since_hours: int,
) -> list[_ProductionTurn]:
    """Pull an *incremental* random sample — only conversations created
    after the most recent production batch run for this modality (or, on
    cold start, after `since_hours` ago). Returns empty if no new
    conversations match the filter, which is the desired no-op behavior:
    no eval row gets written, the UI surfaces "no new conversations"."""
    client = get_bq_client()
    cfg = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("sample_size", "INT64", int(sample_size)),
            bigquery.ScalarQueryParameter("modality",    "STRING", modality),
            bigquery.ScalarQueryParameter("since_hours", "INT64", int(since_hours)),
        ]
    )
    rows = list(client.query(_INCREMENTAL_SAMPLE_SQL, job_config=cfg).result())
    out: list[_ProductionTurn] = []
    for r in rows:
        utterance = r["utterance"] or ""
        if not utterance.strip():
            # Skip seeded conversations whose user_message wasn't reconstructed.
            continue
        out.append(
            _ProductionTurn(
                trace_id=r["trace_id"],
                modality=r["modality"],
                journey=r["journey"],
                outcome=r["outcome"],
                utterance=utterance,
                response_text=r["response_text"] or "",
                confidence=float(r["router_confidence"] or 0.0),
                grounded=(r["verifier_verdict"] == "pass"),
                escalate=(r["outcome"] == "escalated"),
                latency_ms=int(r["latency_p50_ms"] or 0),
                cost_usd=float(r["cost_usd"] or 0.0),
            )
        )
    return out


# ─── Judge each sampled turn ───────────────────────────────────────────────


def _judge_turn(turn: _ProductionTurn) -> QueryResult:
    """Run the LLM-as-judge over a sampled production turn. Reuses the
    golden-set's `_judge()` so the rubric is identical."""
    if not turn.response_text.strip():
        # Nothing for the judge to score; mark as failed without an LLM call.
        judged = {"task_success": "failed", "tone_appropriate": "unknown", "hallucinated": "unknown"}
        judge_cost = 0.0
    else:
        judged, judge_cost = _judge(
            utterance=turn.utterance,
            response_text=turn.response_text,
            expected_outcome=turn.outcome,  # what actually happened — for the rubric's "did the agent achieve it?" framing
            journey=turn.journey,
        )

    return QueryResult(
        query_id=turn.trace_id,
        journey=turn.journey,
        utterance=turn.utterance,
        expected_intent="(production)",     # no ground truth label
        expected_outcome=turn.outcome,
        response_text=turn.response_text,
        response_intent=turn.journey or "ambiguous",
        response_confidence=turn.confidence,
        response_grounded=turn.grounded,
        response_escalate=turn.escalate,
        derived_outcome=turn.outcome,
        latency_ms=turn.latency_ms,
        cost_usd=round(turn.cost_usd + judge_cost, 6),
        intent_correct=False,    # NULL semantics — excluded from aggregation
        hit=None,                # excluded from aggregation
        grounded=turn.grounded,
        task_success=judged["task_success"],
        tone_appropriate=judged["tone_appropriate"],
        hallucinated=judged["hallucinated"],
        outcome_correct=False,   # no ground truth
        must_contain_ok=True,
        must_not_contain_ok=True,
        error=None,
    )


# ─── Aggregate + persist ───────────────────────────────────────────────────


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip() or "unknown"
    except FileNotFoundError:
        pass
    return "unknown"


def _aggregate_production(
    results: list[QueryResult], *, run_id: str, modality: ModalityFilter
) -> dict:
    """Aggregate a production sample. Label-dependent metrics are omitted
    (NULL in BQ); telemetry-derived metrics are populated."""
    n = len(results)
    contained = sum(1 for r in results if r.derived_outcome == "contained")
    hallucinated = sum(1 for r in results if r.hallucinated == "yes")

    latencies = sorted(r.latency_ms for r in results if r.latency_ms > 0)

    def _pct(p: float) -> int:
        if not latencies:
            return 0
        idx = max(0, min(len(latencies) - 1, int(round(p * (len(latencies) - 1)))))
        return int(latencies[idx])

    measured_costs = [r.cost_usd for r in results if r.cost_usd > 0]
    cost_mean = round(statistics.fmean(measured_costs), 6) if measured_costs else 0.0

    return {
        "run_id":                       run_id,
        "git_sha":                      _git_sha(),
        "created_at":                   datetime.now(timezone.utc).isoformat(),
        "source":                       "production",
        "sample_size":                  n,
        "sample_modality":              modality,
        # Telemetry / judge-derived metrics
        "containment_rate":             _safe_div(contained, n),
        "hallucination_rate":           _safe_div(hallucinated, n),
        "task_success_order_status":    _journey_task_success(results, "order_status")    or None,
        "task_success_product_qa":      _journey_task_success(results, "product_qa")      or None,
        "task_success_service_request": _journey_task_success(results, "service_request") or None,
        "latency_p50_ms":               _pct(0.50),
        "latency_p95_ms":               _pct(0.95),
        "cost_per_call_usd":            cost_mean,
        # Label-dependent metrics — None means NULL in the BQ row.
        "refusal_precision":            None,
        "intent_accuracy":              None,
        "retrieval_hit_rate":           None,
    }


def _bq_insert(metrics: dict) -> None:
    client = get_bq_client()
    settings = get_settings()
    table_fqn = f"{settings.project_id}.{settings.bq_dataset}.eval_runs"
    import json
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=False,
    )
    payload = (json.dumps(metrics) + "\n").encode("utf-8")
    job = client.load_table_from_file(BytesIO(payload), table_fqn, job_config=job_config)
    job.result()


# ─── Entry point ───────────────────────────────────────────────────────────


def run_production_batch(
    *,
    sample_size: int = 10,
    modality: ModalityFilter = "voice",
    since_hours: int = 24,
) -> dict:
    """Sample → judge → aggregate → write. Returns the metrics dict."""
    run_id = (
        f"evr_prod_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        f"_{uuid.uuid4().hex[:6]}"
    )
    log.info(
        "production batch eval starting run_id=%s modality=%s n=%d since_h=%d",
        run_id, modality, sample_size, since_hours,
    )

    sample = load_production_sample(
        sample_size=sample_size, modality=modality, since_hours=since_hours,
    )
    log.info("loaded %d new production turns (incremental)", len(sample))
    if not sample:
        log.warning(
            "no new conversations since last %s production batch — skipping write",
            modality,
        )
        return {"run_id": run_id, "sample_size": 0, "skipped": True}

    results = [_judge_turn(t) for t in sample]
    metrics = _aggregate_production(results, run_id=run_id, modality=modality)
    _bq_insert(metrics)
    log.info(
        "production batch eval complete run_id=%s containment=%.3f halluc=%.3f cost=$%.5f",
        run_id, metrics["containment_rate"], metrics["hallucination_rate"] or 0.0,
        metrics["cost_per_call_usd"] or 0.0,
    )
    return metrics
