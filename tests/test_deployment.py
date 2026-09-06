"""Deployment settings remain explicit without changing research workflows."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from finagent.api.main import create_app
from finagent.api.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERCEL_ORIGIN = "https://fin-agent-iota.vercel.app"
LOCAL_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def test_platform_settings_prefer_port_and_merge_exact_frontend_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FINAGENT_ENV", "production")
    monkeypatch.setenv("FRONTEND_ORIGIN", VERCEL_ORIGIN)
    monkeypatch.setenv("PORT", "12000")
    settings = Settings(project_root=tmp_path, database_url="sqlite:///research.db")
    assert settings.host == "0.0.0.0"
    assert settings.port == 12000
    assert settings.cors_origins == (*LOCAL_ORIGINS, VERCEL_ORIGIN)


def test_production_rejects_missing_or_wildcard_frontend_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FINAGENT_ENV", "production")
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    try:
        Settings(project_root=tmp_path)
    except ValueError as error:
        assert "FRONTEND_ORIGIN" in str(error)
    else:
        raise AssertionError("production must require an explicit frontend origin")

    monkeypatch.setenv("FRONTEND_ORIGIN", "*")
    try:
        Settings(project_root=tmp_path)
    except ValueError as error:
        assert "exact http(s) origins" in str(error)
    else:
        raise AssertionError("wildcard CORS must be rejected")


def test_configured_and_local_origins_receive_cors_responses(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'research.db'}",
        environment="production",
        cors_origins=(*LOCAL_ORIGINS, VERCEL_ORIGIN),
    )
    client = TestClient(create_app(settings))

    for path in ("/api/health", "/api/system"):
        response = client.get(path, headers={"Origin": VERCEL_ORIGIN})

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == VERCEL_ORIGIN
        assert response.headers["access-control-allow-credentials"] == "true"

    response = client.options(
        "/api/system",
        headers={
            "Origin": VERCEL_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type,x-request-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == VERCEL_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]

    for origin in LOCAL_ORIGINS:
        response = client.get("/api/health", headers={"Origin": origin})

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_unknown_origin_does_not_receive_cors_permission(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'research.db'}",
        environment="production",
        cors_origins=(*LOCAL_ORIGINS, VERCEL_ORIGIN),
    )
    client = TestClient(create_app(settings))
    unknown_origin = "https://untrusted.example.com"

    response = client.get("/api/health", headers={"Origin": unknown_origin})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

    response = client.options(
        "/api/health",
        headers={
            "Origin": unknown_origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_render_blueprint_uses_platform_port_and_persistent_disk() -> None:
    blueprint = yaml.safe_load((PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8"))
    service = blueprint["services"][0]
    assert service["runtime"] == "python"
    assert service["startCommand"] == "uvicorn finagent.api.main:app --host 0.0.0.0 --port $PORT"
    assert service["healthCheckPath"] == "/api/health"
    assert service["disk"]["mountPath"] == "/var/data"
    assert {entry["key"] for entry in service["envVars"]} >= {"FINAGENT_ENV", "FRONTEND_ORIGIN", "DATABASE_URL"}
