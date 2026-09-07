"""Local historical-dataset API routes backed by the V0.8 service layer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from finagent.api.dependencies import get_service
from finagent.api.schemas import (
    CollectionsResponse,
    DataFetchRequest,
    DataFetchResponse,
    DataProviderResponse,
    DataValidateRequest,
    DatasetDetail,
    DatasetListResponse,
    DatasetSummary,
    OhlcvSeriesResponse,
    PaginationMeta,
)
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/data", tags=["Historical Data"])


@router.get("/providers", response_model=list[DataProviderResponse])
def providers(service: ResearchService = Depends(get_service)) -> list[dict[str, object]]:
    return service.data_providers()


@router.get("/datasets", response_model=DatasetListResponse)
def datasets(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), provider: str | None = None, symbol: str | None = None, status: str | None = Query(default=None, pattern=r"^(valid|warning|invalid)$"), start_date: str | None = None, end_date: str | None = None, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    items, total = service.data_datasets(limit, offset, provider=provider, symbol=symbol, status=status, start_date=start_date, end_date=end_date)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def dataset(dataset_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.data_dataset(dataset_id)


@router.get("/datasets/{dataset_id}/ohlcv", response_model=OhlcvSeriesResponse)
def ohlcv(
    dataset_id: str,
    start_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(default=1200, ge=2, le=5000),
    service: ResearchService = Depends(get_service),
) -> dict[str, object]:
    """Bound a persisted OHLCV response for responsive terminal charts."""
    return service.data_ohlcv(dataset_id, start_date=start_date, end_date=end_date, limit=limit)


@router.post("/fetch", response_model=DataFetchResponse)
def fetch(request: DataFetchRequest, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.fetch_data(request.model_dump())


@router.post("/validate", response_model=DatasetSummary)
def validate(request: DataValidateRequest, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.validate_data(request.dataset_id, request.missing_data_policy)


@router.get("/collections", response_model=CollectionsResponse)
def collections(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), service: ResearchService = Depends(get_service)) -> dict[str, object]:
    items, total = service.data_collections(limit, offset)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}
