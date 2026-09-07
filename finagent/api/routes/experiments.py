"""Experiment and decision-history routes; all computation stays in ResearchService."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from finagent.api.dependencies import get_service
from finagent.api.security import audit_admin_action, require_admin, require_mutation_rate_limit
from finagent.api.schemas import (
    AgentDecisionsResponse,
    ActivityResponse,
    CritiqueResponse,
    ExecutionResponse,
    ExperimentDetail,
    ExperimentListResponse,
    OhlcvSeriesResponse,
    PaginationMeta,
    RegimesResponse,
    RunRequest,
    TradesResponse,
)
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/experiments", tags=["Experiments"])
_experiment_id = Path(..., min_length=10, max_length=32, pattern=r"^EXP-[0-9]{6}$")


@router.get("", response_model=ExperimentListResponse)
def list_experiments(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), search: str | None = Query(default=None, max_length=120),
    strategy: str | None = Query(default=None, max_length=40), asset: str | None = Query(default=None, max_length=64), start_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"), end_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    regime: str | None = Query(default=None, pattern=r"^(bull|bear|sideways|high_volatility|low_volatility|stress)$"), status: str | None = Query(default=None, pattern=r"^(validated|unvalidated|critiqued|without_critique)$"),
    version: str | None = Query(default=None, max_length=64), sort_by: str = Query("created_at", pattern=r"^(created_at|total_return|sharpe_ratio|maximum_drawdown|start_date)$"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
    service: ResearchService = Depends(get_service),
) -> dict[str, object]:
    items, total = service.list_experiments(limit=limit, offset=offset, search=search, strategy=strategy, asset=asset, start_date=start_date, end_date=end_date, regime=regime, status=status, version=version, sort_by=sort_by, sort_order=sort_order)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.post(
    "/run",
    response_model=ExecutionResponse,
    dependencies=[Depends(require_admin), Depends(require_mutation_rate_limit)],
)
def run(request: RunRequest, http_request: Request, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    audit_admin_action(http_request, "ADMIN_EXPERIMENT_RUN")
    return service.run_experiment(request.config_path, request.model_dump(exclude_none=True))


@router.get("/{experiment_id}", response_model=ExperimentDetail)
def experiment(experiment_id: str = _experiment_id, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.experiment_detail(experiment_id)


@router.get("/{experiment_id}/market-data", response_model=OhlcvSeriesResponse)
def market_data(
    experiment_id: str = _experiment_id,
    start_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(default=1200, ge=2, le=5000),
    service: ResearchService = Depends(get_service),
) -> dict[str, object]:
    return service.experiment_market_data(experiment_id, start_date=start_date, end_date=end_date, limit=limit)


@router.get("/{experiment_id}/trades", response_model=TradesResponse)
def trades(experiment_id: str = _experiment_id, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return {"experiment_id": experiment_id, "items": service.trades(experiment_id)}


@router.get("/{experiment_id}/regimes", response_model=RegimesResponse)
def regimes(experiment_id: str = _experiment_id, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.regimes(experiment_id)


@router.get("/{experiment_id}/agent-decisions", response_model=AgentDecisionsResponse)
def agent_decisions(experiment_id: str = _experiment_id, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), service: ResearchService = Depends(get_service)) -> dict[str, object]:
    items, total = service.agent_decisions(experiment_id, limit, offset)
    return {"experiment_id": experiment_id, "items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.get("/{experiment_id}/critique", response_model=CritiqueResponse)
def critique(experiment_id: str = _experiment_id, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.critique(experiment_id)


@router.get("/activity/recent", response_model=ActivityResponse)
def activity(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None, max_length=48),
    source: str | None = Query(default=None, max_length=48),
    search: str | None = Query(default=None, max_length=120),
    service: ResearchService = Depends(get_service),
) -> dict[str, object]:
    items, total = service.activity(limit=limit, offset=offset, event_type=event_type, source=source, search=search)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}
