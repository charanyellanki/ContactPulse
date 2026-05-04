"""Agent turn I/O — request/response for POST /agent/turn.

The shape uses the same enums as TraceSummary so AgentResponse rows can be
folded into a TraceDetail without translation. Voice is realtime via the
`WS /agent/voice/live` WebSocket (see CLAUDE.md §14) and uses its own framing.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .common import IntentOrAmbiguous, Modality


class AgentTurnHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    text: str


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    customer_id: str | None = None
    utterance: str
    modality: Modality
    history: list[AgentTurnHistoryItem] = Field(default_factory=list)


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    response_text: str
    intent: IntentOrAmbiguous
    confidence: float
    grounded: bool
    escalate: bool
    latency_ms: int
