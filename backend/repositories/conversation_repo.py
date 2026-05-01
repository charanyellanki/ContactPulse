"""Conversation/trace repository.

Fixture-backed for the UI-first scaffold (CLAUDE.md §2 step 1). Will be
re-implemented against the BigQuery `conversation_traces` table per
ARCHITECTURE.md §5 — method signatures stay the same.
"""
from __future__ import annotations

from backend.fixtures import CONVERSATIONS, TRACE_DETAILS
from backend.models.conversation import TraceDetail, TraceSummary


def list_conversations(limit: int | None = None) -> list[TraceSummary]:
    if limit is None:
        return list(CONVERSATIONS)
    return list(CONVERSATIONS[:limit])


def get_trace_detail(trace_id: str) -> TraceDetail | None:
    return TRACE_DETAILS.get(trace_id)
