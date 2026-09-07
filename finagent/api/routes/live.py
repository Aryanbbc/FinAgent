"""Typed non-executing live market intelligence endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from finagent.api.dependencies import get_service
from finagent.api.schemas import (
    LiveEventsResponse,
    LiveHistoryResponse,
    LiveSignalsResponse,
    LiveSnapshotResponse,
    LiveStatusResponse,
    LiveSymbolsResponse,
)
from finagent.services.research_service import ResearchService

router = APIRouter(prefix="/api/live", tags=["Live market intelligence"])
_symbol = Path(..., min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._^=-]+$")


@router.get("/status", response_model=LiveStatusResponse)
def status(service: ResearchService = Depends(get_service)) -> dict[str, object]:
    """Return bounded feed state; disabled mode is a valid non-error response."""
    return service.live_status()


@router.get("/symbols", response_model=LiveSymbolsResponse)
def symbols(service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return {"items": service.live_symbols()}


@router.get("/snapshot/{symbol}", response_model=LiveSnapshotResponse)
def snapshot(symbol: str = _symbol, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return service.live_snapshot(symbol)


@router.get("/history/{symbol}", response_model=LiveHistoryResponse)
def history(symbol: str = _symbol, service: ResearchService = Depends(get_service)) -> dict[str, object]:
    return {"symbol": symbol.upper(), "items": service.live_history(symbol)}


@router.get("/signals/{symbol}", response_model=LiveSignalsResponse)
def signals(
    symbol: str = _symbol,
    limit: int = Query(50, ge=1, le=500),
    service: ResearchService = Depends(get_service),
) -> dict[str, object]:
    return {"symbol": symbol.upper(), "items": service.live_signals(symbol, limit)}


@router.get("/events/{symbol}", response_model=LiveEventsResponse)
def events(
    symbol: str = _symbol,
    limit: int = Query(100, ge=1, le=500),
    service: ResearchService = Depends(get_service),
) -> dict[str, object]:
    return {"symbol": symbol.upper(), "items": service.live_events(symbol, limit)}
