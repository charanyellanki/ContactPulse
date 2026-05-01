"""Conversation/trace routes — mounted at /traces to match the frontend
API client (frontend/src/api/queries.ts useConversations / useTrace)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.conversation import TraceDetail, TraceSummary
from backend.repositories.conversation_repo import (
    ConversationRepository,
    get_conversation_repo,
)

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=list[TraceSummary])
def list_traces(
    limit: int | None = Query(default=None, ge=1, le=200),
    repo: ConversationRepository = Depends(get_conversation_repo),
) -> list[TraceSummary]:
    return repo.list_conversations(limit=limit)


@router.get("/{trace_id}", response_model=TraceDetail)
def get_trace(
    trace_id: str,
    repo: ConversationRepository = Depends(get_conversation_repo),
) -> TraceDetail:
    detail = repo.get_trace_detail(trace_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
    return detail
