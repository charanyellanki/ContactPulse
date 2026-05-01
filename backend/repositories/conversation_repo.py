"""Conversation/trace repository — BigQuery-backed.

`conversations` and `conversation_traces` use a deliberately simple storage
schema (input_text/output_text/metadata JSON), but the API contract surfaces
the rich Pydantic discriminated-union TraceEvent the frontend already speaks.

This module owns the translation: BQ rows in, `TraceSummary` / `TraceDetail`
out. Repository pattern per ARCHITECTURE.md §11 — no SQL anywhere else.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import cast

from fastapi import Depends
from google.cloud import bigquery

from backend.models.common import (
    IntentOrAmbiguous,
    Journey,
    LoyaltyTier,
    Modality,
    Outcome,
)
from backend.models.conversation import (
    AgentResponseEvent,
    AgentResponsePayload,
    RetrievalEvent,
    RetrievalPayload,
    RouterCandidate,
    RouterEvent,
    RouterPayload,
    SttEvent,
    SttPayload,
    SynthesisCitation,
    SynthesisEvent,
    SynthesisPayload,
    TraceDetail,
    TraceEvent,
    TraceSummary,
    TtsEvent,
    TtsPayload,
    UserMessageEvent,
    UserMessagePayload,
    VerificationEvent,
    VerificationPayload,
)
from backend.models.customer import CustomerSummary
from backend.repositories.bigquery_client import fq, get_bq_client


def _customer_summary(customer_id: str | None, tier: str | None) -> CustomerSummary | None:
    if customer_id is None or tier is None:
        return None
    return CustomerSummary(
        customer_id=customer_id,
        display_label=f"Cust #{customer_id} · {tier.title()}",
        tier=cast(LoyaltyTier, tier),
    )


def _ts(value: object) -> str:
    """BigQuery returns timestamps as `datetime` (UTC). Normalize to ISO-8601."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _row_to_summary(row: bigquery.Row) -> TraceSummary:
    journey = cast(Journey, row["journey"])
    intent: IntentOrAmbiguous = cast(IntentOrAmbiguous, journey)
    return TraceSummary(
        trace_id=row["trace_id"],
        started_at=_ts(row["created_at"]),
        modality=cast(Modality, row["modality"]),
        customer=_customer_summary(row["customer_id"], row["tier"]),
        intent=intent,
        journey=journey,
        outcome=cast(Outcome, row["outcome"]),
        turn_count=int(row["turns"]),
        total_latency_ms=int(row["latency_p50_ms"]),
        total_cost_usd=float(row["cost_usd"]),
    )


# ─── Event row → discriminated-union TraceEvent translation ───────────────


def _parse_metadata(raw: object) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return {}


def _row_to_event(
    row: bigquery.Row,
    modality: Modality,
    customer: CustomerSummary | None,
) -> TraceEvent | None:
    """Translate one `conversation_traces` row to a rich TraceEvent.

    Returns None for stage rows that were emitted-but-skipped (e.g. STT/TTS
    on chat) — those exist in BigQuery for shape-consistency but should not
    surface to the frontend.
    """
    et = row["event_type"]
    md = _parse_metadata(row["metadata"])
    if md.get("skipped"):
        return None

    base = {
        "trace_id":          row["trace_id"],
        "turn_index":        0,
        "timestamp":         _ts(row["timestamp"]),
        "modality":          modality,
        "latency_ms":        int(row["latency_ms"]),
        "llm_input_tokens":  int(md.get("input_tokens", 0)),
        "llm_output_tokens": int(md.get("output_tokens", 0)),
        "llm_cost_usd":      float(md.get("cost_usd", 0.0)),
    }

    if et == "user_message":
        return UserMessageEvent(
            event_type="user_message",
            event_payload=UserMessagePayload(
                text=row["input_text"] or "",
                pii_redacted=bool(row["pii_redacted"]),
            ),
            **base,
        )
    if et == "stt":
        return SttEvent(
            event_type="stt",
            event_payload=SttPayload(
                audio_duration_ms=int(md.get("audio_duration_ms", 0)),
                transcript=row["output_text"] or "",
                confidence=float(md.get("confidence", 0.0)),
                pii_redacted=bool(row["pii_redacted"]),
            ),
            **base,
        )
    if et == "intent_routing":
        return RouterEvent(
            event_type="router",
            event_payload=RouterPayload(
                model=md.get("model", "gemini-2.0-flash"),
                intent=cast(IntentOrAmbiguous, md.get("intent", "ambiguous")),
                confidence=float(md.get("confidence", 0.0)),
                threshold=float(md.get("threshold", 0.7)),
                reasoning=md.get("reasoning", ""),
                candidates=[
                    RouterCandidate(
                        intent=cast(IntentOrAmbiguous, c["intent"]),
                        score=float(c["score"]),
                    )
                    for c in md.get("candidates", [])
                ],
            ),
            **base,
        )
    if et == "retrieval":
        passages = md.get("passages", [])
        return RetrievalEvent(
            event_type="retrieval",
            event_payload=RetrievalPayload(
                query=md.get("query", ""),
                k=int(md.get("k", len(passages))),
                passages=passages,  # Pydantic will validate per-passage shape
            ),
            **base,
        )
    if et == "synthesis":
        return SynthesisEvent(
            event_type="synthesis",
            event_payload=SynthesisPayload(
                model=md.get("model", "gemini-2.0-pro"),
                attempt=int(md.get("attempt", 1)),
                response_text=row["output_text"] or "",
                citations=[
                    SynthesisCitation(passage_id=c["passage_id"], span=c["span"])
                    for c in md.get("citations", [])
                ],
            ),
            **base,
        )
    if et == "grounding_verification":
        return VerificationEvent(
            event_type="verification",
            event_payload=VerificationPayload(
                model=md.get("model", "gemini-2.0-pro"),
                attempt=int(md.get("attempt", 1)),
                verdict=md.get("verdict", "pass"),
                score=float(md.get("score", 0.0)),
                threshold=float(md.get("threshold", 0.8)),
                rationale=md.get("rationale", ""),
                ungrounded_claims=md.get("ungrounded_claims", []),
            ),
            **base,
        )
    if et == "tts":
        return TtsEvent(
            event_type="tts",
            event_payload=TtsPayload(
                voice=md.get("voice", "en-US-Neural2-F"),
                audio_duration_ms=int(md.get("audio_duration_ms", 0)),
                audio_url=md.get("audio_url", ""),
            ),
            **base,
        )
    if et == "agent_response":
        return AgentResponseEvent(
            event_type="agent_response",
            event_payload=AgentResponsePayload(
                text=row["output_text"] or "",
                audio_url=md.get("audio_url"),
            ),
            **base,
        )
    # Unknown event_type — defensively drop rather than 500 the API.
    return None


# ─── Repository ───────────────────────────────────────────────────────────


_LIST_SUMMARIES_SQL = f"""
SELECT
  c.trace_id,
  c.modality,
  c.customer_id,
  c.tier,
  c.journey,
  c.outcome,
  c.turns,
  c.latency_p50_ms,
  c.cost_usd,
  c.created_at
FROM {fq('conversations')} c
ORDER BY c.created_at DESC
LIMIT @limit
"""

_GET_SUMMARY_SQL = f"""
SELECT
  c.trace_id,
  c.modality,
  c.customer_id,
  c.tier,
  c.journey,
  c.outcome,
  c.turns,
  c.latency_p50_ms,
  c.cost_usd,
  c.created_at
FROM {fq('conversations')} c
WHERE c.trace_id = @trace_id
LIMIT 1
"""

_GET_EVENTS_SQL = f"""
SELECT event_id, trace_id, event_type, input_text, output_text, metadata,
       latency_ms, pii_redacted, timestamp
FROM {fq('conversation_traces')}
WHERE trace_id = @trace_id
ORDER BY timestamp ASC
"""


class ConversationRepository:
    def __init__(self, client: bigquery.Client) -> None:
        self._client = client

    def list_conversations(self, limit: int | None = None) -> list[TraceSummary]:
        cfg = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("limit", "INT64", int(limit) if limit else 200)
            ]
        )
        return [_row_to_summary(r) for r in self._client.query(_LIST_SUMMARIES_SQL, job_config=cfg).result()]

    def get_conversation(self, trace_id: str) -> TraceSummary | None:
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("trace_id", "STRING", trace_id)]
        )
        rows = list(self._client.query(_GET_SUMMARY_SQL, job_config=cfg).result())
        return _row_to_summary(rows[0]) if rows else None

    def get_trace_events(
        self,
        trace_id: str,
        modality: Modality,
        customer: CustomerSummary | None,
    ) -> list[TraceEvent]:
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("trace_id", "STRING", trace_id)]
        )
        rows = self._client.query(_GET_EVENTS_SQL, job_config=cfg).result()
        events: list[TraceEvent] = []
        for r in rows:
            ev = _row_to_event(r, modality, customer)
            if ev is not None:
                events.append(ev)
        return events

    def get_trace_detail(self, trace_id: str) -> TraceDetail | None:
        """Compose summary + events for the `/traces/{trace_id}` endpoint."""
        summary = self.get_conversation(trace_id)
        if summary is None:
            return None
        events = self.get_trace_events(trace_id, summary.modality, summary.customer)
        ended_at = events[-1].timestamp if events else summary.started_at
        return TraceDetail(
            **summary.model_dump(),
            ended_at=ended_at,
            events=events,
        )


@lru_cache(maxsize=1)
def _cached_repo(client: bigquery.Client) -> ConversationRepository:
    return ConversationRepository(client)


def get_conversation_repo(
    client: bigquery.Client = Depends(get_bq_client),
) -> ConversationRepository:
    return _cached_repo(client)
