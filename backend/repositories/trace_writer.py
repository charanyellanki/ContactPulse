"""Trace event writer — appends rows to `conversation_traces` as the agent
pipeline runs.

The read side (`conversation_repo`) already maps rows → discriminated-union
TraceEvents. This writer goes the other direction: each pipeline step produces
a row matching the same schema, so the existing Operator Console rendering
just works for live conversations too.

Streaming inserts are used here (not load jobs) because (a) the row count per
turn is tiny — 6-9 rows — and (b) we want them visible immediately so the
Trace Drill-Down view in the Operator Console can pick them up while the
conversation is still going. Streaming-buffer "freshness" cost is negligible
at our volumes.

In-process tap (`trace_buffer` contextvar) — every event written by this
module is also appended to the active per-task buffer when one is set. The
eval runner uses this to compute real per-query cost (summed `metadata.cost_usd`)
and real retrieval-hit-rate (passages from the `retrieval` event) without
round-tripping through BigQuery. Production callers leave the contextvar
unset and the tap is a no-op.
"""
from __future__ import annotations

import contextvars
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Iterator

from fastapi import Depends
from google.cloud import bigquery

from backend.repositories.bigquery_client import get_bq_client

log = logging.getLogger(__name__)


# ─── In-process trace tap ─────────────────────────────────────────────────

_trace_buffer: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar(
    "contactpulse_trace_buffer", default=None
)


@contextmanager
def capture_trace_events() -> Iterator[list[dict]]:
    """Capture every event written via `TraceWriter.write_event` for the
    duration of the `with` block. Returns the list the events accumulate into.

    Used by the eval harness to read real per-query cost and retrieval data
    without an extra BigQuery round-trip. The buffer holds a *copy* of each
    row's `metadata` (so callers can mutate freely without corrupting the
    BQ-bound row).
    """
    buf: list[dict] = []
    token = _trace_buffer.set(buf)
    try:
        yield buf
    finally:
        _trace_buffer.reset(token)


def _ts_iso(ts: datetime) -> str:
    utc = ts.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


class TraceWriter:
    """Streams `conversation_traces` rows."""

    def __init__(self, client: bigquery.Client) -> None:
        self._client = client
        # Build the FQN once per instance — saves a Settings lookup per write.
        from backend.config import get_settings

        s = get_settings()
        self._table = f"{s.project_id}.{s.bq_dataset}.conversation_traces"
        self._summary_table = f"{s.project_id}.{s.bq_dataset}.conversations"

    def write_conversation_summary(
        self,
        *,
        trace_id: str,
        modality: str,
        customer_id: str | None,
        tier: str | None,
        journey: str | None,
        outcome: str,
        turns: int,
        latency_p50_ms: int,
        cost_usd: float,
    ) -> None:
        """Append one row to `conversations` so the turn shows up in the
        Operator Console's Live Conversations view. Best-effort — a failed
        summary write must not kill the customer turn the user already saw.

        Each turn through the agent currently produces one summary row
        (the demo is single-turn). When multi-turn lands, this becomes a
        MERGE keyed on trace_id.
        """
        row = {
            "trace_id":       trace_id,
            "modality":       modality,
            "customer_id":    customer_id,
            "tier":           tier,
            "journey":        journey or "out_of_scope",
            "outcome":        outcome,
            "turns":          int(turns),
            "latency_p50_ms": int(latency_p50_ms),
            "cost_usd":       float(cost_usd),
            "created_at":     _ts_iso(datetime.now(timezone.utc)),
        }
        try:
            errors = self._client.insert_rows_json(self._summary_table, [row])
            if errors:
                log.warning("conversation summary insert errors: %s", errors)
        except Exception:
            log.exception(
                "conversation summary insert failed trace_id=%s", trace_id
            )

    def write_event(
        self,
        *,
        trace_id: str,
        event_type: str,
        latency_ms: int,
        metadata: dict,
        input_text: str | None = None,
        output_text: str | None = None,
        pii_redacted: bool = False,
    ) -> None:
        """Insert one trace event. Errors are logged, not raised — a failed
        trace write must not kill an otherwise-good customer turn."""
        # In-process tap — append a structured copy before serializing.
        buf = _trace_buffer.get()
        if buf is not None:
            buf.append(
                {
                    "trace_id":     trace_id,
                    "event_type":   event_type,
                    "latency_ms":   int(latency_ms),
                    "metadata":     dict(metadata),
                    "input_text":   input_text,
                    "output_text":  output_text,
                    "pii_redacted": bool(pii_redacted),
                }
            )

        row = {
            "event_id":     str(uuid.uuid4()),
            "trace_id":     trace_id,
            "event_type":   event_type,
            "input_text":   input_text,
            "output_text":  output_text,
            "metadata":     json.dumps(metadata),
            "latency_ms":   int(latency_ms),
            "pii_redacted": bool(pii_redacted),
            "timestamp":    _ts_iso(datetime.now(timezone.utc)),
        }
        try:
            errors = self._client.insert_rows_json(self._table, [row])
            if errors:
                log.warning("trace insert errors: %s", errors)
        except Exception:
            log.exception("trace insert failed trace_id=%s event_type=%s",
                          trace_id, event_type)


@lru_cache(maxsize=1)
def _cached_writer(client: bigquery.Client) -> TraceWriter:
    return TraceWriter(client)


def get_trace_writer(client: bigquery.Client = Depends(get_bq_client)) -> TraceWriter:
    return _cached_writer(client)
