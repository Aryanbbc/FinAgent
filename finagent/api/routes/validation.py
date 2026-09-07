from fastapi import APIRouter, Depends, Query, Request

from finagent.api.dependencies import get_service
from finagent.api.security import audit_admin_action, require_admin, require_mutation_rate_limit
from finagent.api.schemas import ExecutionResponse, PaginationMeta, RunRequest, ValidationDetail, ValidationListResponse
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api", tags=["Research Validation"])


@router.get("/validation", response_model=ValidationListResponse)
def validations(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), asset: str | None = None, status: str | None = Query(default=None, pattern=r"^(passed|failed)$"), start_date: str | None = None, end_date: str | None = None, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    items, total = service.validations(limit, offset, asset=asset, status=status, start_date=start_date, end_date=end_date)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.post(
    "/validation/run",
    response_model=ExecutionResponse,
    dependencies=[Depends(require_admin), Depends(require_mutation_rate_limit)],
)
def run(request: RunRequest, http_request: Request, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    audit_admin_action(http_request, "ADMIN_VALIDATION_RUN")
    return service.run_validation(request.config_path)


@router.get("/validation/{experiment_id}", response_model=ValidationDetail)
def validation(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.validation_for_experiment(experiment_id)
