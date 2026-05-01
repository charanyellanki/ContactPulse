"""Agent turn routes — text (`/agent/turn`) and voice (`/agent/voice`).

Voice flow:
    audio_base64 (WAV)
      → STT (Google chirp v2)         → utterance text
        → AgentRequest(utterance=…)
          → agent_service.handle_turn  → AgentResponse
            → TTS (Google Neural2)    → MP3 bytes
              → VoiceResponse(audio_base64=…)

The text path (`/agent/turn`) is unchanged. Voice is a thin envelope around it
so the operator-facing trace looks identical regardless of channel.
"""
from __future__ import annotations

import base64
import logging
import time

from fastapi import APIRouter, HTTPException

from backend.config import get_settings
from backend.llm.client import AgentError
from backend.models.agent import (
    AgentRequest,
    AgentResponse,
    VoiceRequest,
    VoiceResponse,
)
from backend.repositories.bigquery_client import get_bq_client
from backend.repositories.trace_writer import TraceWriter
from backend.services import agent_service, voice_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/turn", response_model=AgentResponse)
def post_turn(request: AgentRequest) -> AgentResponse:
    return agent_service.handle_turn(request)


@router.post("/voice", response_model=VoiceResponse)
def post_voice(request: VoiceRequest) -> VoiceResponse:
    settings = get_settings()
    started = time.perf_counter()

    # ── 1. Decode base64 audio with size guard ──────────────────────────
    try:
        audio_bytes = base64.b64decode(request.audio_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="audio_base64 is not valid base64") from exc
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="audio payload is empty")
    if len(audio_bytes) > settings.voice_max_audio_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"audio exceeds {settings.voice_max_audio_bytes} bytes",
        )

    tw = TraceWriter(get_bq_client())

    # ── 2. STT ─────────────────────────────────────────────────────────
    try:
        stt = voice_service.transcribe(audio_bytes)
    except AgentError as exc:
        log.warning("voice: stt failed for trace %s: %s", request.trace_id, exc)
        raise HTTPException(status_code=502, detail="speech-to-text unavailable") from exc

    tw.write_event(
        trace_id=request.trace_id,
        event_type="stt",
        latency_ms=stt.latency_ms,
        metadata={
            "model":             settings.stt_model,
            "audio_duration_ms": stt.audio_duration_ms,
            "confidence":        stt.confidence,
        },
        output_text=stt.transcript,
    )

    if not stt.transcript:
        raise HTTPException(status_code=422, detail="no speech detected")

    # ── 3. Run the same pipeline as /agent/turn ─────────────────────────
    agent_resp: AgentResponse = agent_service.handle_turn(
        AgentRequest(
            trace_id=request.trace_id,
            customer_id=request.customer_id,
            utterance=stt.transcript,
            modality="voice",
            history=request.history,
        )
    )

    # ── 4. TTS ──────────────────────────────────────────────────────────
    try:
        tts = voice_service.synthesize(agent_resp.response_text)
    except AgentError as exc:
        log.warning("voice: tts failed for trace %s: %s", request.trace_id, exc)
        raise HTTPException(status_code=502, detail="text-to-speech unavailable") from exc

    tw.write_event(
        trace_id=request.trace_id,
        event_type="tts",
        latency_ms=tts.latency_ms,
        metadata={
            "voice":             tts.voice,
            "audio_bytes":       len(tts.audio_bytes),
            "speaking_rate":     settings.tts_speaking_rate,
        },
    )

    return VoiceResponse(
        trace_id=agent_resp.trace_id,
        response_text=agent_resp.response_text,
        intent=agent_resp.intent,
        confidence=agent_resp.confidence,
        grounded=agent_resp.grounded,
        escalate=agent_resp.escalate,
        latency_ms=int((time.perf_counter() - started) * 1000),
        utterance=stt.transcript,
        audio_base64=base64.b64encode(tts.audio_bytes).decode("ascii"),
        audio_mime="audio/mpeg",
        stt_latency_ms=stt.latency_ms,
        tts_latency_ms=tts.latency_ms,
    )
