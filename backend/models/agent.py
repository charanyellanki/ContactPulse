"""Agent turn I/O — request/response for POST /agent/turn.

Not yet in frontend types.ts (the live-conversation flow lands in step 3 of the
UI-first scaffolding order). The shape uses the same enums as TraceSummary so
AgentResponse rows can be folded into a TraceDetail without translation.
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


class VoiceRequest(BaseModel):
    """Voice turn request — base64-encoded WAV bytes from MediaRecorder."""
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    customer_id: str | None = None
    audio_base64: str
    history: list[AgentTurnHistoryItem] = Field(default_factory=list)


class VoiceResponse(AgentResponse):
    """Voice turn response — agent fields plus TTS audio + STT transcript."""
    model_config = ConfigDict(extra="forbid")

    utterance: str  # what STT heard (post-DLP redaction is applied downstream)
    audio_base64: str
    audio_mime: str = "audio/mpeg"
    stt_latency_ms: int
    tts_latency_ms: int
