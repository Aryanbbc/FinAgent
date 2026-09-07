"""FastAPI application for FinAgent historical-research artifacts."""

from __future__ import annotations

import logging
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from finagent.api.routes import data, experiments, health, improvements, live, reports, system, validation
from finagent.api.security import BoundedRateLimiter
from finagent.api.settings import Settings
from finagent.configuration import ConfigurationValidationError
from finagent.data.market_provider import MarketDataProviderError
from finagent.data.registry import DatasetNotFoundError
from finagent.database.db import DatabaseError
from finagent.services.research_service import InvalidConfigurationError, NotFoundError, ResearchService
from finagent.utils.logging import configure_logging, log_event


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or Settings()
    logger = configure_logging()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        """Verify the selected backend and idempotent schema before accepting requests."""
        try:
            application.state.research_service.ensure_database_ready()
        except DatabaseError as error:
            logger.error("event=DATABASE_STARTUP_FAILED backend=%s error=%s", runtime.database_backend, error)
            raise RuntimeError(f"FinAgent database startup failed ({runtime.database_backend})") from error
        await application.state.research_service.start_live_monitoring()
        try:
            yield
        finally:
            await application.state.research_service.stop_live_monitoring()

    app = FastAPI(
        title="FinAgent Research API",
        version="1.1.0",
        description="Deterministic historical research plus opt-in live market intelligence. No trading execution is available.",
        lifespan=lifespan,
    )
    app.state.settings = runtime
    app.state.logger = logger
    app.state.mutation_limiter = BoundedRateLimiter(
        limit=runtime.mutation_rate_limit,
        window_seconds=runtime.mutation_rate_window_seconds,
    )
    app.state.report_limiter = BoundedRateLimiter(limit=10, window_seconds=300)
    try:
        app.state.research_service = ResearchService(runtime)
    except DatabaseError as error:
        logger.error("event=DATABASE_INITIALIZATION_FAILED backend=%s error=%s", runtime.database_backend, error)
        raise RuntimeError(f"FinAgent database startup failed ({runtime.database_backend})") from error
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def error_response(request: Request, status_code: int, code: str, message: str, details: object | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        payload = {
            "error_code": code,
            "message": message,
            "details": details,
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "detail": {"code": code, "message": message},
        }
        log_event(logger, "API_ERROR", logging.WARNING if status_code < 500 else logging.ERROR, request_id=request_id, path=request.url.path, status_code=status_code, artifact_id=code)
        return JSONResponse(status_code=status_code, content=payload, headers=headers)

    def public_message(message: str) -> str:
        """Keep deployment errors useful without reflecting paths or backend details."""
        if runtime.environment == "production":
            return "The request could not be processed."
        return message

    def validation_details(errors: list[dict[str, object]]) -> list[dict[str, object]]:
        """Pydantic's raw input/context may contain untrusted paths or secrets."""
        return [
            {key: item[key] for key in ("loc", "msg", "type") if key in item}
            for item in errors
        ]

    @app.middleware("http")
    async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = supplied_request_id if re.fullmatch(r"[A-Za-z0-9-]{8,64}", supplied_request_id) else uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log_event(logger, "API_UNHANDLED_ERROR", logging.ERROR, request_id=request_id, method=request.method, path=request.url.path)
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'"
        )
        if runtime.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        log_event(logger, "API_REQUEST", request_id=request_id, method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=duration_ms)
        return response

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, error: NotFoundError) -> JSONResponse:
        code = "REPORT_NOT_FOUND" if str(error).startswith("Report not found") else "NOT_FOUND"
        return error_response(request, 404, code, public_message(str(error)))

    @app.exception_handler(InvalidConfigurationError)
    async def bad_config(request: Request, error: InvalidConfigurationError) -> JSONResponse:
        return error_response(request, 400, "INVALID_CONFIGURATION", public_message(str(error)))

    @app.exception_handler(ConfigurationValidationError)
    async def configuration_validation(request: Request, error: ConfigurationValidationError) -> JSONResponse:
        return error_response(request, 400, "INVALID_RESEARCH_CONFIGURATION", public_message(str(error)))

    @app.exception_handler(DatasetNotFoundError)
    async def dataset_not_found(request: Request, error: DatasetNotFoundError) -> JSONResponse:
        return error_response(request, 404, "DATASET_NOT_FOUND", public_message(str(error)))

    @app.exception_handler(MarketDataProviderError)
    async def provider_error(request: Request, error: MarketDataProviderError) -> JSONResponse:
        status = error.status if error.status is not None else (503 if error.retryable else 400)
        # Internal provider failures without a meaningful upstream HTTP status
        # remain a service availability response rather than leaking a 200/3xx.
        if status < 400 or status > 599:
            status = 503 if error.retryable else 400
        return error_response(request, status, error.code, public_message(str(error)), error.details())

    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "REQUEST_VALIDATION_ERROR", "Request validation failed", validation_details(error.errors()))

    @app.exception_handler(HTTPException)
    async def http_exception(request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == 401:
            return error_response(request, 401, "ADMIN_AUTH_REQUIRED", "An administrator key is required for this action.", headers=error.headers)
        if error.status_code == 429:
            message = "Too many report requests. Retry after the indicated delay." if error.headers and error.headers.get("X-FinAgent-Rate-Limit-Scope") == "reports" else "Too many privileged research requests. Retry after the indicated delay."
            headers = dict(error.headers or {})
            headers.pop("X-FinAgent-Rate-Limit-Scope", None)
            return error_response(request, 429, "RATE_LIMITED", message, headers=headers)
        message = error.detail if isinstance(error.detail, str) else "Request rejected"
        return error_response(request, error.status_code, "HTTP_ERROR", public_message(message), headers=error.headers)

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(DatabaseError)
    async def database_error(request: Request, error: sqlite3.Error | DatabaseError) -> JSONResponse:
        return error_response(request, 503, "DATABASE_UNAVAILABLE", "The configured research database is temporarily unavailable")

    @app.exception_handler(ValueError)
    async def value_error(request: Request, error: ValueError) -> JSONResponse:
        code = "VALIDATION_FAILURE" if "/validation" in request.url.path else "INVALID_REQUEST"
        return error_response(request, 400, code, public_message(str(error)))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        log_event(logger, "API_UNEXPECTED_ERROR", logging.ERROR, request_id=getattr(request.state, "request_id", None), path=request.url.path, artifact_id=type(error).__name__)
        return error_response(request, 500, "INTERNAL_ERROR", "An unexpected local application error occurred. Check local logs for details.")

    for router in (health.router, experiments.router, improvements.router, validation.router, reports.router, data.router, live.router, system.router):
        app.include_router(router)
    return app


app = create_app()
