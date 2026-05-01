"""Error-cluster routes — operator console error analysis surface."""
from __future__ import annotations

from fastapi import APIRouter

from backend.fixtures import ERROR_CLUSTERS
from backend.models.error import ErrorCluster

router = APIRouter(prefix="/errors", tags=["errors"])


@router.get("/clusters", response_model=list[ErrorCluster])
def list_error_clusters() -> list[ErrorCluster]:
    return list(ERROR_CLUSTERS)
