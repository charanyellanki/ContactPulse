"""Eval-run routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.models.eval import EvalRunDetail, EvalRunSummary
from backend.repositories.eval_repo import EvalRunRepository, get_eval_repo

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
