from fastapi import APIRouter, Depends, Query

from finagent.api.dependencies import get_service
from finagent.api.schemas import ExecutionResponse, ImprovementDetail, ImprovementsResponse, PaginationMeta, RunRequest
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/improvements", tags=["Self-Improvement"])


@router.get("", response_model=ImprovementsResponse)
def improvements(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), service: ResearchService = Depends(get_service)) -> dict[str, object]:
    items, total = service.improvements(limit, offset)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.post("/run", response_model=ExecutionResponse, status_code=202)
def run(request: RunRequest, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.run_improvement(request.config_path)


@router.get("/{run_id}", response_model=ImprovementDetail)
def improvement(run_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.improvement(run_id)

