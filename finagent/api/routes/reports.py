from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from finagent.api.dependencies import get_service
from finagent.api.schemas import ReportResponse
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/{experiment_id}", response_model=ReportResponse)
def report(experiment_id: str, service: ResearchService = Depends(get_service)) -> dict[str, str]:
    return service.report(experiment_id)


@router.get("/{experiment_id}/download", response_class=FileResponse, include_in_schema=False)
def download(experiment_id: str, service: ResearchService = Depends(get_service)) -> FileResponse:
    path = service.report_path(experiment_id)
    return FileResponse(path, media_type="text/markdown", filename=path.name)

