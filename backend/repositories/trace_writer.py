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
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends
from google.cloud import bigquery

from backend.repositories.bigquery_client import get_bq_client

log = logging.getLogger(__name__)


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
