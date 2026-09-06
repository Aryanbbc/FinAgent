"""Experiment and decision-history routes; all computation stays in ResearchService."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from finagent.api.dependencies import get_service
from finagent.api.schemas import (
    AgentDecisionsResponse,
    CritiqueResponse,
    ExecutionResponse,
    ExperimentDetail,
    ExperimentListResponse,
    PaginationMeta,
    RegimesResponse,
    RunRequest,
    TradesResponse,
)
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/experiments", tags=["Experiments"])


@router.get("", response_model=ExperimentListResponse)
def list_experiments(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), search: str | None = None,
    strategy: str | None = None, asset: str | None = None, start_date: str | None = None, end_date: str | None = None,
    service: ResearchService = Depends(get_service),
) -> dict[str, object]:
    items, total = service.list_experiments(limit=limit, offset=offset, search=search, strategy=strategy, asset=asset, start_date=start_date, end_date=end_date)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.post("/run", response_model=ExecutionResponse)
def run(request: RunRequest, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.run_experiment(request.config_path)


@router.get("/{experiment_id}", response_model=ExperimentDetail)
def experiment(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.experiment_detail(experiment_id)


@router.get("/{experiment_id}/trades", response_model=TradesResponse)
def trades(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return {"experiment_id": experiment_id, "items": service.trades(experiment_id)}


@router.get("/{experiment_id}/regimes", response_model=RegimesResponse)
def regimes(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.regimes(experiment_id)


@router.get("/{experiment_id}/agent-decisions", response_model=AgentDecisionsResponse)
def agent_decisions(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return {"experiment_id": experiment_id, "items": service.agent_decisions(experiment_id)}


@router.get("/{experiment_id}/critique", response_model=CritiqueResponse)
def critique(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.critique(experiment_id)
