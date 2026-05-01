"""Agent turn route — handles a single utterance from the live conversation
flow (Customer Experience view). Mocked end-to-end for the scaffold."""
from __future__ import annotations

from fastapi import APIRouter

from backend.models.agent import AgentRequest, AgentResponse
from backend.services import agent_service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/turn", response_model=AgentResponse)
def post_turn(request: AgentRequest) -> AgentResponse:
    return agent_service.handle_turn(request)
