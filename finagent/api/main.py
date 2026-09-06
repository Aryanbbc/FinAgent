"""FastAPI application for local FinAgent historical-research artifacts."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from finagent.api.routes import data, experiments, health, improvements, reports, system, validation
from finagent.api.settings import Settings
from finagent.data.market_provider import MarketDataProviderError
from finagent.data.registry import DatasetNotFoundError
from finagent.services.research_service import InvalidConfigurationError, NotFoundError, ResearchService


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or Settings()
    app = FastAPI(title="FinAgent Local Research API", version="0.8.0", description="Local-only historical research, dataset management, and controlled V0.1–V0.7 workflow access.")
    app.state.research_service = ResearchService(runtime)
    app.add_middleware(CORSMiddleware, allow_origins=list(runtime.cors_origins), allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": {"code": "NOT_FOUND", "message": str(error)}})

    @app.exception_handler(InvalidConfigurationError)
    async def bad_config(_: Request, error: InvalidConfigurationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": {"code": "INVALID_CONFIG_PATH", "message": str(error)}})

    @app.exception_handler(DatasetNotFoundError)
    async def dataset_not_found(_: Request, error: DatasetNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": {"code": "DATASET_NOT_FOUND", "message": str(error)}})

    @app.exception_handler(MarketDataProviderError)
    async def provider_error(_: Request, error: MarketDataProviderError) -> JSONResponse:
        status = 503 if error.code in {"PROVIDER_UNAVAILABLE", "RATE_LIMIT"} else 400
        return JSONResponse(status_code=status, content={"detail": {"code": error.code, "message": str(error)}})

    for router in (health.router, experiments.router, improvements.router, validation.router, reports.router, data.router, system.router):
        app.include_router(router)
    return app


app = create_app()
