from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse

from finagent.api.dependencies import get_service
from finagent.api.security import require_report_rate_limit
from finagent.api.schemas import ReportResponse
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/reports", tags=["Reports"])
_experiment_id = Path(..., min_length=10, max_length=32, pattern=r"^EXP-[0-9]{6}$")


@router.get("/{experiment_id}", response_model=ReportResponse, dependencies=[Depends(require_report_rate_limit)])
def report(experiment_id: str = _experiment_id, service: ResearchService = Depends(get_service)) -> dict[str, str]:
    return service.report(experiment_id)


@router.get("/{experiment_id}/download", response_class=FileResponse, include_in_schema=False, dependencies=[Depends(require_report_rate_limit)])
def download(experiment_id: str = _experiment_id, service: ResearchService = Depends(get_service)) -> FileResponse:
    path = service.report_path(experiment_id)
    return FileResponse(path, media_type="text/markdown", filename=path.name)
