"""Error-cluster model — operator-console error analysis surface."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .common import FailureType


class ErrorCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    label: str
    failure_type: FailureType
    count: int
    description: str
    sample_trace_ids: list[str]
