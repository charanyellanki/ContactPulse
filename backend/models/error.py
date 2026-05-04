"""Error-cluster model — operator-console error analysis surface."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .common import ClusterModality, FailureType


class ErrorCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    label: str
    failure_type: FailureType
    # Channel scope for the cluster — drives the page-level voice/chat filter
    # in the Operator Console. Defaults to "both" so legacy fixtures remain
    # visible under either filter until the clustering pipeline tags them.
    modality: ClusterModality = "both"
    count: int
    description: str
    sample_trace_ids: list[str]
