"""Single BigQuery client for the process.

CLAUDE.md §6: BigQuery access goes through repositories. Repositories share
one client, instantiated lazily and cached. Auth is Application Default
Credentials — no service-account JSON is read or shipped.
"""
from __future__ import annotations

from functools import lru_cache

from google.cloud import bigquery

from backend.config import get_settings


@lru_cache(maxsize=1)
def get_bq_client() -> bigquery.Client:
    """Cached BigQuery client. Uses ADC; project from Settings."""
    settings = get_settings()
    return bigquery.Client(project=settings.project_id)


def fq(table: str) -> str:
    """Fully-qualified `project.dataset.table` reference for SQL strings."""
    settings = get_settings()
    return f"`{settings.project_id}.{settings.bq_dataset}.{table}`"
