from fastapi import APIRouter, Depends, Query, Request

from finagent.api.dependencies import get_service
from finagent.api.security import audit_admin_action, require_admin, require_mutation_rate_limit
from finagent.api.schemas import ExecutionResponse, ImprovementContext, ImprovementDetail, ImprovementsResponse, PaginationMeta, RunRequest
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/improvements", tags=["Self-Improvement"])


@router.get("", response_model=ImprovementsResponse)
def improvements(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), status: str | None = Query(default=None, pattern=r"^(BASELINE|PROMOTED|REJECTED)$"), version: str | None = None, start_date: str | None = None, end_date: str | None = None, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    items, total = service.improvements(limit, offset, status=status, version=version, start_date=start_date, end_date=end_date)
    return {"items": items, "pagination": PaginationMeta(limit=limit, offset=offset, total=total)}


@router.get("/context", response_model=ImprovementContext)
def improvement_context(service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.improvement_context()


@router.post(
    "/run",
    response_model=ExecutionResponse,
    dependencies=[Depends(require_admin), Depends(require_mutation_rate_limit)],
)
def run(request: RunRequest, http_request: Request, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    audit_admin_action(http_request, "ADMIN_IMPROVEMENT_RUN")
    return service.run_improvement(request.config_path)


@router.get("/{run_id}", response_model=ImprovementDetail)
def improvement(run_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.improvement(run_id)
