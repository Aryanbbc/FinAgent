from fastapi import APIRouter, Depends

from finagent.api.dependencies import get_service
from finagent.api.schemas import ConfigResponse, ConfigurationVersion, SystemResponse, VersionsResponse
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/versions", response_model=VersionsResponse)
def versions(service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return {"items": service.versions()}


@router.get("/versions/{version_id}", response_model=ConfigurationVersion)
def version(version_id: str, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.version(version_id)


@router.get("/config", response_model=ConfigResponse)
def configuration(service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.configuration()


@router.get("/system", response_model=SystemResponse)
def system(service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.system()

