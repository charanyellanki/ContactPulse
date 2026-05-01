"""Conversation trace models — the unifying primitive across CE and OC views.

Mirrors frontend/src/api/types.ts. Timestamps stay as ISO-8601 strings on the
wire (matching the existing zod schemas) rather than datetime, so fixtures
round-trip without serialization drift.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .common import (
    EscalationReason,
    IntentOrAmbiguous,
    Journey,
    Modality,
    Outcome,
    VerificationVerdict,
)
from .customer import CustomerSummary


# ─── Event payloads ────────────────────────────────────────────────────────


class UserMessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    pii_redacted: bool


class SttPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio_duration_ms: int
    transcript: str
    confidence: float
    pii_redacted: bool


class CustomerContextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer: CustomerSummary | None
    recent_orders_count: int
    prior_contacts_count: int
    is_anonymous: bool


class RouterCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: IntentOrAmbiguous
    score: float


class RouterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    intent: IntentOrAmbiguous
    confidence: float
    threshold: float
    reasoning: str
    candidates: list[RouterCandidate]


class RetrievalPassage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passage_id: str
    source: str
    content: str
    semantic_score: float
    keyword_score: float
    fused_score: float
    rerank_score: float


class RetrievalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    k: int
    passages: list[RetrievalPassage]


class SynthesisCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passage_id: str
    span: str


class SynthesisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    attempt: int
    response_text: str
    citations: list[SynthesisCitation]


class UngroundedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str
    reason: str


class VerificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    attempt: int
    verdict: VerificationVerdict
    score: float
    threshold: float
    rationale: str
    ungrounded_claims: list[UngroundedClaim]


class EscalationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: EscalationReason
    detail: str


class TtsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice: str
    audio_duration_ms: int
    audio_url: str


class AgentResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    audio_url: str | None = None


# ─── TraceEvent: discriminated union over event_type ───────────────────────


class _TraceEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: str
    turn_index: int
    timestamp: str
    modality: Modality
    latency_ms: int
    llm_input_tokens: int
    llm_output_tokens: int
    llm_cost_usd: float


class UserMessageEvent(_TraceEventBase):
    event_type: Literal["user_message"]
    event_payload: UserMessagePayload


class SttEvent(_TraceEventBase):
    event_type: Literal["stt"]
    event_payload: SttPayload


class CustomerContextEvent(_TraceEventBase):
    event_type: Literal["customer_context"]
    event_payload: CustomerContextPayload


class RouterEvent(_TraceEventBase):
    event_type: Literal["router"]
    event_payload: RouterPayload


class RetrievalEvent(_TraceEventBase):
    event_type: Literal["retrieval"]
    event_payload: RetrievalPayload


class SynthesisEvent(_TraceEventBase):
    event_type: Literal["synthesis"]
    event_payload: SynthesisPayload


class VerificationEvent(_TraceEventBase):
    event_type: Literal["verification"]
    event_payload: VerificationPayload


class EscalationEvent(_TraceEventBase):
    event_type: Literal["escalation"]
    event_payload: EscalationPayload


class TtsEvent(_TraceEventBase):
    event_type: Literal["tts"]
    event_payload: TtsPayload


class AgentResponseEvent(_TraceEventBase):
    event_type: Literal["agent_response"]
    event_payload: AgentResponsePayload


TraceEvent = Annotated[
    Union[
        UserMessageEvent,
        SttEvent,
        CustomerContextEvent,
        RouterEvent,
        RetrievalEvent,
        SynthesisEvent,
        VerificationEvent,
        EscalationEvent,
        TtsEvent,
        AgentResponseEvent,
    ],
    Field(discriminator="event_type"),
]


# ─── Trace summary / detail (GET /traces, GET /traces/{id}) ────────────────


class TraceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: str
    started_at: str
    modality: Modality
    customer: CustomerSummary | None
    intent: IntentOrAmbiguous | None
    journey: Journey | None
    outcome: Outcome
    turn_count: int
    total_latency_ms: int
    total_cost_usd: float


class TraceDetail(TraceSummary):
    ended_at: str | None
    events: list[TraceEvent]
