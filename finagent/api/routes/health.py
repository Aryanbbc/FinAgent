from fastapi import APIRouter, Depends

from finagent import __version__
from finagent.api.schemas import HealthResponse
from finagent.api.dependencies import get_service
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/health", response_model=HealthResponse)
def health(service: ResearchService = Depends(get_service)) -> dict[str, str | None]:
    return {"service": "finagent-local-research-api", "version": __version__, **service.health()}
