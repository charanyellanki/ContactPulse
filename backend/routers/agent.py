"""Agent turn route — chat (`/agent/turn`).

Voice has moved to a streaming WebSocket — see `backend/routers/voice_live.py`
(`WS /agent/voice/live`) and CLAUDE.md §14. The legacy push-to-talk endpoint
(`POST /agent/voice`) was removed alongside its STT/TTS batch helpers.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.models.agent import AgentRequest, AgentResponse
from backend.services import agent_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/turn", response_model=AgentResponse)
def post_turn(request: AgentRequest) -> AgentResponse:
    return agent_service.handle_turn(request)
