"""Eval-run routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.evals.production_eval import (
    ModalityFilter,
    preview_incremental,
    run_production_batch,
)
from backend.models.eval import EvalRunDetail, EvalRunSummary
from backend.repositories.eval_repo import EvalRunRepository, get_eval_repo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/runs", response_model=list[EvalRunSummary])
def list_eval_runs(repo: EvalRunRepository = Depends(get_eval_repo)) -> list[EvalRunSummary]:
    return repo.list_eval_runs()


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
def get_eval_run(
    run_id: str,
    repo: EvalRunRepository = Depends(get_eval_repo),
) -> EvalRunDetail:
    detail = repo.get_eval_run(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Eval run '{run_id}' not found")
    return detail


# ─── Production batch eval — UI-triggered ────────────────────────────────


class BatchEvalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modality: ModalityFilter = "voice"
    sample_size: int = Field(default=10, ge=1, le=50)
    since_hours: int = Field(default=24, ge=1, le=168)


class BatchEvalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str            # "running" | "skipped"
    sample_size: int
    modality: ModalityFilter
    since_hours: int
    message: str


def _kick_off_batch(req: BatchEvalRequest) -> None:
    """Wrapper for FastAPI BackgroundTasks — never raises, only logs."""
    try:
        run_production_batch(
            sample_size=req.sample_size,
            modality=req.modality,
            since_hours=req.since_hours,
        )
    except Exception:                         # noqa: BLE001 — background task
        log.exception("production batch eval failed")


@router.post("/batch", response_model=BatchEvalResponse, status_code=202)
def post_batch_eval(
    req: BatchEvalRequest, background: BackgroundTasks
) -> BatchEvalResponse:
    """Kick off an *incremental* production batch eval in the background.

    Incremental semantics: samples conversations created AFTER the most
    recent production batch eval row for this modality (cold start: falls
    back to the `since_hours` rolling window). Re-clicking with no new
    conversations is a no-op — no row gets written, the eval table stays
    stable. This is how Conversational Insights and other production EVA
    pipelines behave.

    Industry pattern: the same `run_production_batch()` function would be
    invoked on a Cloud Scheduler → Cloud Run Job cron in production. The
    UI button is the on-demand demo trigger.
    """
    background.add_task(_kick_off_batch, req)
    return BatchEvalResponse(
        status="running",
        sample_size=req.sample_size,
        modality=req.modality,
        since_hours=req.since_hours,
        message=(
            f"Judging up to {req.sample_size} new {req.modality} conversation(s) "
            f"since the last batch run. A new eval_runs row appears when complete; "
            f"if no new conversations, no row is written."
        ),
    )


class BatchEvalPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modality: ModalityFilter
    since_at: str | None    # ISO timestamp of the last batch run, or fallback
    new_count: int          # how many conversations a Run would consider


@router.get("/batch/preview", response_model=BatchEvalPreviewResponse)
def get_batch_preview(
    modality: ModalityFilter = "voice",
    since_hours: int = 168,
) -> BatchEvalPreviewResponse:
    """How many new conversations a batch eval would judge right now.

    Drives the OC's 'N new voice conversations since <timestamp>' callout
    so the user can decide whether clicking is worth it. Cheap query — one
    COUNT(*) over the cutoff window."""
    p = preview_incremental(modality=modality, since_hours=since_hours)
    return BatchEvalPreviewResponse(**p)
