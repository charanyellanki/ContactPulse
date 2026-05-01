"""Fixture loader — JSON on disk, validated against Pydantic models at import.

These are the same fixtures the frontend ships in src/fixtures/. Keeping a
backend copy makes the container self-contained for Cloud Run while the real
BigQuery repositories are still stubbed.

If a fixture fails to validate, the app fails fast at startup rather than
returning malformed responses to the UI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from backend.models.conversation import TraceDetail, TraceSummary
from backend.models.customer import Customer
from backend.models.error import ErrorCluster
from backend.models.eval import EvalRunSummary

_FIXTURES_DIR = Path(__file__).parent


def _read_json(name: str) -> Any:
    return json.loads((_FIXTURES_DIR / name).read_text())


_trace_summary_list = TypeAdapter(list[TraceSummary])
_eval_run_list = TypeAdapter(list[EvalRunSummary])
_error_cluster_list = TypeAdapter(list[ErrorCluster])
_customer_list = TypeAdapter(list[Customer])


CONVERSATIONS: list[TraceSummary] = _trace_summary_list.validate_python(
    _read_json("conversations.json")
)
EVAL_RUNS: list[EvalRunSummary] = _eval_run_list.validate_python(
    _read_json("eval_runs.json")
)
ERROR_CLUSTERS: list[ErrorCluster] = _error_cluster_list.validate_python(
    _read_json("error_clusters.json")
)
CUSTOMERS: list[Customer] = _customer_list.validate_python(_read_json("customers.json"))


def _load_trace_details() -> dict[str, TraceDetail]:
    out: dict[str, TraceDetail] = {}
    traces_dir = _FIXTURES_DIR / "traces"
    for path in sorted(traces_dir.glob("*.json")):
        detail = TraceDetail.model_validate(json.loads(path.read_text()))
        out[detail.trace_id] = detail
    return out


TRACE_DETAILS: dict[str, TraceDetail] = _load_trace_details()
