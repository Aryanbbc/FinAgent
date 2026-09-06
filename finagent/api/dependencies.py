"""FastAPI dependencies shared by thin route modules."""

from __future__ import annotations

from fastapi import Request

from finagent.services.research_service import ResearchService


def get_service(request: Request) -> ResearchService:
    return request.app.state.research_service

