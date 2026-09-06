from fastapi import APIRouter

from finagent import __version__
from finagent.api.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/health", response_model=HealthResponse)
def health() -> dict[str, str]:
    return {"status": "ok", "service": "finagent-local-research-api", "version": __version__}

