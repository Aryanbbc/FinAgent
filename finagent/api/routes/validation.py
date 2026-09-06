from fastapi import APIRouter, Depends, Query

from finagent.api.dependencies import get_service
from finagent.api.schemas import ExecutionResponse, PaginationMeta, RunRequest, ValidationDetail, ValidationListResponse
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api", tags=["Research Validation"])


@router.get("/validation", response_model=ValidationListResponse)
def validations(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), service: ResearchService = Depends(get_service)) -> dict[str, object]:
    items, total = service.validations(limit, offset)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.post("/validation/run", response_model=ExecutionResponse, status_code=202)
def run(request: RunRequest, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.run_validation(request.config_path)


@router.get("/validation/{experiment_id}", response_model=ValidationDetail)
def validation(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.validation_for_experiment(experiment_id)

