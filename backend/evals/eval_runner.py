"""Eval harness — runs `test_set.jsonl` through the agent pipeline.

Per query:
  1. Call `agent_service.handle_turn()` with the labeled utterance.
  2. Evaluate four dimensions:
       - intent_correct        — response.intent == expected_intent
       - retrieval_hit         — top retrieval score >= 0.5 (stub: True)
       - grounded              — response.grounded after the verifier
       - task_success / hallucinated  — Gemini Flash LLM-as-judge
       - outcome_correct       — derived outcome matches expected_outcome
  3. Aggregate to primary metrics (containment, refusal precision, etc.).
  4. Write one row to BigQuery `eval_runs` and per-query results to GCS.

Usage:
    python -m backend.evals.eval_runner            # run, write artifacts
    python -m backend.evals.eval_runner --dry-run  # run, skip BQ + GCS writes

Idempotent on the data side: each invocation produces a new run_id so prior
runs are never overwritten. The harness is intentionally serial — Gemini's
free-tier rate limits are tight enough that parallelism creates more problems
(429s, retries) than it solves at this scale (~300 calls total).
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from tqdm import tqdm

from backend.config import get_settings
from backend.evals import test_set_loader
from backend.llm import circuit_breaker
from backend.llm.client import AgentError, generate_json, load_prompt, render
from backend.models.agent import AgentRequest
from backend.repositories.bigquery_client import fq, get_bq_client
from backend.services.agent_service import REFUSAL_TEXT, handle_turn

log = logging.getLogger("eval_runner")

EVAL_CUSTOMER_ID = "#eval-runner"

# Outcome values used in the test set (capitalized) → internal lowercase.
_OUTCOME_NORMALIZE = {
    "contained":  "contained",
    "refused":    "refused",
    "escalated":  "escalated",
}


# ─── Per-query result ─────────────────────────────────────────────────────


@dataclass
class QueryResult:
    """One row of per-query results — flattened for JSONL serialization."""

    query_id: str
    journey: str
    utterance: str
    expected_intent: str
    expected_outcome: str

    response_text: str
    response_intent: str
    response_confidence: float
    response_grounded: bool
    response_escalate: bool
    derived_outcome: str
    latency_ms: int

    # Eval dimensions
    intent_correct: bool
    hit: bool
    grounded: bool
    task_success: str         # resolved | partial | failed | error
    tone_appropriate: str     # yes | no | unknown
    hallucinated: str         # yes | no | unknown
    outcome_correct: bool

    must_contain_ok: bool
    must_not_contain_ok: bool

    error: str | None = None


# ─── Outcome derivation ───────────────────────────────────────────────────


def _derive_outcome(*, response_text: str, escalate: bool) -> str:
    """Map AgentResponse → {contained, refused, escalated}.

    Refusal-text wins over escalate=True because grounding-failed responses
    set both flags but are semantically refusals (the agent declined to
    answer rather than handing off a successful conversation).
    """
    if response_text.strip() == REFUSAL_TEXT:
        return "refused"
    if escalate:
        return "escalated"
    return "contained"


# ─── LLM-as-judge ─────────────────────────────────────────────────────────


def _judge(
    *,
    utterance: str,
    response_text: str,
    expected_outcome: str,
    journey: str,
) -> dict[str, str]:
    """Call Gemini Flash with the eval rubric. Returns parsed JSON.

    On any failure, returns a sentinel dict so the caller can mark the query
    as "error" rather than crashing the run.
    """
    settings = get_settings()
    template = load_prompt("eval_judge")
    prompt = render(
        template,
        UTTERANCE=utterance,
        RESPONSE=response_text,
        EXPECTED_OUTCOME=expected_outcome,
        JOURNEY=journey,
    )
    try:
        parsed, _llm = generate_json(
            model=settings.gemini_flash_model,
            prompt=prompt,
            temperature=0.0,
            # 2.5-flash can spend ~150-300 tokens on internal thinking even
            # for short outputs; budget extra so the closing `}` isn't cut.
            max_output_tokens=1024,
        )
    except (AgentError, circuit_breaker.CircuitOpenError) as exc:
        log.warning("judge failed: %s", exc)
        return {
            "task_success": "error",
            "tone_appropriate": "unknown",
            "hallucinated": "unknown",
        }
    return {
        "task_success":     str(parsed.get("task_success", "error")).strip().lower(),
        "tone_appropriate": str(parsed.get("tone_appropriate", "unknown")).strip().lower(),
        "hallucinated":     str(parsed.get("hallucinated", "unknown")).strip().lower(),
    }


# ─── Per-query eval ───────────────────────────────────────────────────────


def _evaluate_one(query: dict[str, Any], *, run_id: str) -> QueryResult:
    """Run one labeled query through the pipeline and score it."""
    started = time.perf_counter()
    trace_id = f"trc_eval_{run_id}_{query['query_id']}"
    request = AgentRequest(
        trace_id=trace_id,
        customer_id=EVAL_CUSTOMER_ID,
        utterance=query["utterance"],
        modality="chat",
        history=[],
    )

    # Run the pipeline. Failures inside handle_turn already degrade safe
    # (escalation), so we mostly only catch unexpected exceptions here.
    try:
        response = handle_turn(request)
        response_text = response.response_text
        response_intent = response.intent
        response_confidence = response.confidence
        response_grounded = response.grounded
        response_escalate = response.escalate
        latency_ms = response.latency_ms
        run_error: str | None = None
    except Exception as exc:  # noqa: BLE001 — eval boundary
        log.exception("pipeline error on %s", query["query_id"])
        response_text = ""
        response_intent = "ambiguous"
        response_confidence = 0.0
        response_grounded = False
        response_escalate = True
        latency_ms = int((time.perf_counter() - started) * 1000)
        run_error = f"pipeline_exception: {exc}"

    derived_outcome = _derive_outcome(
        response_text=response_text, escalate=response_escalate
    )
    expected_outcome_lc = _OUTCOME_NORMALIZE.get(
        query["expected_outcome"].strip().lower(), query["expected_outcome"].strip().lower()
    )

    # Intent: the test set uses internal labels (order_status, product_qa,
    # service_request, out_of_scope). The pipeline emits "ambiguous" /
    # "escalate" on safety paths; those count as wrong intent unless the
    # test set expected escalation/out_of_scope explicitly.
    intent_correct = response_intent == query["expected_intent"]

    # Retrieval hit — stub per spec ("always True for now").
    hit = query["journey"] == "product_qa"

    # Must-contain / must-not-contain string checks
    text_lc = response_text.lower()
    must_contain_ok = all(s.lower() in text_lc for s in query.get("must_contain", []))
    must_not_contain_ok = all(s.lower() not in text_lc for s in query.get("must_not_contain", []))

    # LLM-as-judge — skip if the pipeline crashed (response_text is empty)
    if run_error is None and response_text.strip():
        judged = _judge(
            utterance=query["utterance"],
            response_text=response_text,
            expected_outcome=query["expected_outcome"],
            journey=query["journey"],
        )
    else:
        judged = {
            "task_success": "failed",
            "tone_appropriate": "unknown",
            "hallucinated": "unknown",
        }

    return QueryResult(
        query_id=query["query_id"],
        journey=query["journey"],
        utterance=query["utterance"],
        expected_intent=query["expected_intent"],
        expected_outcome=query["expected_outcome"],
        response_text=response_text,
        response_intent=response_intent,
        response_confidence=response_confidence,
        response_grounded=response_grounded,
        response_escalate=response_escalate,
        derived_outcome=derived_outcome,
        latency_ms=latency_ms,
        intent_correct=intent_correct,
        hit=hit,
        grounded=response_grounded,
        task_success=judged["task_success"],
        tone_appropriate=judged["tone_appropriate"],
        hallucinated=judged["hallucinated"],
        outcome_correct=derived_outcome == expected_outcome_lc,
        must_contain_ok=must_contain_ok,
        must_not_contain_ok=must_not_contain_ok,
        error=run_error,
    )


# ─── Aggregation ──────────────────────────────────────────────────────────


_TASK_SUCCESS_SCORE = {"resolved": 1.0, "partial": 0.5, "failed": 0.0, "error": 0.0}


@dataclass
class RunMetrics:
    run_id: str
    git_sha: str
    created_at: str

    total_queries: int
    containment_rate: float
    refusal_precision: float
    task_success_order_status: float
    task_success_product_qa: float
    task_success_service_request: float
    intent_accuracy: float
    retrieval_hit_rate: float
    hallucination_rate: float
    latency_p50_ms: int
    latency_p95_ms: int
    cost_per_call_usd: float

    per_journey_counts: dict[str, int] = field(default_factory=dict)


def _safe_div(num: float, den: float) -> float:
    return num / den if den > 0 else 0.0


def _journey_task_success(results: list[QueryResult], journey: str) -> float:
    rows = [r for r in results if r.journey == journey]
    if not rows:
        return 0.0
    scores = [_TASK_SUCCESS_SCORE.get(r.task_success, 0.0) for r in rows]
    return sum(scores) / len(scores)


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


def _aggregate(results: list[QueryResult], *, run_id: str) -> RunMetrics:
    total = len(results)

    contained = sum(1 for r in results if r.derived_outcome == "contained")
    total_refused = sum(1 for r in results if r.derived_outcome == "refused")
    correctly_refused = sum(
        1 for r in results
        if r.derived_outcome == "refused"
        and _OUTCOME_NORMALIZE.get(r.expected_outcome.lower(), "") == "refused"
    )

    intent_correct = sum(1 for r in results if r.intent_correct)

    pqa = [r for r in results if r.journey == "product_qa"]
    pqa_hits = sum(1 for r in pqa if r.hit)

    hallucinated = sum(1 for r in results if r.hallucinated == "yes")

    latencies = [r.latency_ms for r in results if r.latency_ms > 0]
    latencies.sort()

    def _pct(p: float) -> int:
        if not latencies:
            return 0
        # statistics.quantiles is overkill for 150 values — index directly.
        idx = max(0, min(len(latencies) - 1, int(round(p * (len(latencies) - 1)))))
        return int(latencies[idx])

    cost_per_call = _estimate_cost_per_call(total)

    per_journey_counts = {
        j: sum(1 for r in results if r.journey == j)
        for j in ("order_status", "product_qa", "service_request")
    }

    return RunMetrics(
        run_id=run_id,
        git_sha=_git_sha(),
        created_at=datetime.now(timezone.utc).isoformat(),
        total_queries=total,
        containment_rate=_safe_div(contained, total),
        refusal_precision=_safe_div(correctly_refused, total_refused),
        task_success_order_status=_journey_task_success(results, "order_status"),
        task_success_product_qa=_journey_task_success(results, "product_qa"),
        task_success_service_request=_journey_task_success(results, "service_request"),
        intent_accuracy=_safe_div(intent_correct, total),
        retrieval_hit_rate=_safe_div(pqa_hits, len(pqa)),
        hallucination_rate=_safe_div(hallucinated, total),
        latency_p50_ms=_pct(0.50),
        latency_p95_ms=_pct(0.95),
        cost_per_call_usd=round(cost_per_call, 6),
        per_journey_counts=per_journey_counts,
    )


def _estimate_cost_per_call(total: int) -> float:
    """Best-effort cost per call. Each pipeline invocation makes ~3-5 LLM
    calls (router + specialist synth + verifier ± retry); plus the eval
    judge. Use a fixed ~ $0.0014/call budget per ARCHITECTURE.md §12 since
    the LLMResult cost values are already logged into BQ traces — duplicating
    them here would require reading the traces back. Static estimate is
    fine for the run-summary metric (frontend already shows it as a band)."""
    if total == 0:
        return 0.0
    return 0.0014


# ─── Persistence ──────────────────────────────────────────────────────────


def _bq_insert(metrics: RunMetrics) -> None:
    """Insert one row into `eval_runs`. Uses load-job for idempotency."""
    client = get_bq_client()
    settings = get_settings()
    table_fqn = f"{settings.project_id}.{settings.bq_dataset}.eval_runs"

    row = {
        "run_id":                       metrics.run_id,
        "git_sha":                      metrics.git_sha,
        "created_at":                   metrics.created_at,
        "containment_rate":             metrics.containment_rate,
        "refusal_precision":            metrics.refusal_precision,
        "task_success_order_status":    metrics.task_success_order_status,
        "task_success_product_qa":      metrics.task_success_product_qa,
        "task_success_service_request": metrics.task_success_service_request,
        "intent_accuracy":              metrics.intent_accuracy,
        "retrieval_hit_rate":           metrics.retrieval_hit_rate,
        "hallucination_rate":           metrics.hallucination_rate,
        "latency_p50_ms":               metrics.latency_p50_ms,
        "latency_p95_ms":               metrics.latency_p95_ms,
        "cost_per_call_usd":            metrics.cost_per_call_usd,
    }

    from google.cloud import bigquery as bq
    job_config = bq.LoadJobConfig(
        source_format=bq.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bq.WriteDisposition.WRITE_APPEND,
        autodetect=False,
    )
    payload = (json.dumps(row) + "\n").encode("utf-8")
    job = client.load_table_from_file(BytesIO(payload), table_fqn, job_config=job_config)
    job.result()


def _gcs_write_results(
    *, run_id: str, results: list[QueryResult], metrics: RunMetrics
) -> str:
    """Upload per-query JSONL + summary JSON to GCS. Returns the results URI."""
    from google.cloud import storage
    from google.cloud.exceptions import NotFound

    settings = get_settings()
    client = storage.Client(project=settings.project_id)
    bucket_name = settings.gcs_evals_bucket
    try:
        bucket = client.get_bucket(bucket_name)
    except NotFound:
        log.info("creating GCS bucket %s", bucket_name)
        bucket = client.create_bucket(bucket_name, location=settings.gcp_region.upper())

    results_path = f"runs/{run_id}/results.jsonl"
    summary_path = f"runs/{run_id}/summary.json"

    results_blob = bucket.blob(results_path)
    ndjson = "\n".join(json.dumps(asdict(r)) for r in results) + "\n"
    results_blob.upload_from_string(ndjson, content_type="application/x-ndjson")

    summary_blob = bucket.blob(summary_path)
    summary_blob.upload_from_string(
        json.dumps(asdict(metrics), indent=2), content_type="application/json"
    )

    return f"gs://{bucket_name}/{results_path}"


# ─── Print helpers ────────────────────────────────────────────────────────


def _print_metrics(metrics: RunMetrics) -> None:
    print()
    print("=" * 70)
    print(f"  Eval run {metrics.run_id}    git={metrics.git_sha}    n={metrics.total_queries}")
    print("=" * 70)
    rows: list[tuple[str, str, str]] = [
        ("containment_rate",             f"{metrics.containment_rate:.3f}",          "(target ≥ 0.75)"),
        ("refusal_precision",            f"{metrics.refusal_precision:.3f}",         "(target ≥ 0.88)"),
        ("intent_accuracy",              f"{metrics.intent_accuracy:.3f}",           "(target ≥ 0.82)"),
        ("hallucination_rate",           f"{metrics.hallucination_rate:.3f}",        "(target ≤ 0.08)"),
        ("retrieval_hit_rate",           f"{metrics.retrieval_hit_rate:.3f}",        ""),
        ("task_success_order_status",    f"{metrics.task_success_order_status:.3f}", ""),
        ("task_success_product_qa",      f"{metrics.task_success_product_qa:.3f}",   ""),
        ("task_success_service_request", f"{metrics.task_success_service_request:.3f}", ""),
        ("latency_p50_ms",               f"{metrics.latency_p50_ms}",                ""),
        ("latency_p95_ms",               f"{metrics.latency_p95_ms}",                ""),
        ("cost_per_call_usd",            f"${metrics.cost_per_call_usd:.5f}",         ""),
    ]
    for name, value, note in rows:
        print(f"  {name:<32} {value:>10}   {note}")
    print()


# ─── Entrypoint ───────────────────────────────────────────────────────────


def run(
    *,
    test_set_path: Path | None = None,
    write_bq: bool = True,
    write_gcs: bool = True,
    limit: int | None = None,
) -> tuple[RunMetrics, list[QueryResult]]:
    """Run the harness end-to-end. Returns (metrics, per-query results)."""
    queries = test_set_loader.load(test_set_path)
    if limit is not None:
        queries = queries[:limit]

    run_id = f"evr_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    log.info("starting run %s — %d queries", run_id, len(queries))

    results: list[QueryResult] = []
    iterator = tqdm(queries, desc="evaluating", unit="q")
    for q in iterator:
        result = _evaluate_one(q, run_id=run_id)
        results.append(result)
        iterator.set_postfix_str(
            f"{result.journey[:3]} {result.task_success[:4]}", refresh=False
        )

    metrics = _aggregate(results, run_id=run_id)
    _print_metrics(metrics)

    if write_gcs:
        try:
            uri = _gcs_write_results(run_id=run_id, results=results, metrics=metrics)
            print(f"  wrote per-query results: {uri}")
        except Exception as exc:  # noqa: BLE001
            log.warning("GCS write failed (run continues): %s", exc)

    if write_bq:
        try:
            _bq_insert(metrics)
            print(f"  inserted BigQuery row: eval_runs/{metrics.run_id}")
        except Exception as exc:  # noqa: BLE001
            log.warning("BQ insert failed (run continues): %s", exc)

    return metrics, results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("google").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="skip BQ + GCS writes")
    parser.add_argument("--limit", type=int, default=None, help="evaluate at most N queries (smoke)")
    parser.add_argument("--test-set", type=Path, default=None, help="path to test_set.jsonl")
    args = parser.parse_args()

    run(
        test_set_path=args.test_set,
        write_bq=not args.dry_run,
        write_gcs=not args.dry_run,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
