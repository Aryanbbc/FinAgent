"""Security controls around the public API facade, not research behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finagent.api.main import create_app
from finagent.api.security import BoundedRateLimiter
from finagent.api.settings import Settings
from finagent.learning.candidate_generator import CandidateGenerator
from finagent.utils.logging import redact


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_KEY = "security-test-admin-key"
PAYLOAD = {
    "provider": "local_csv",
    "symbol": "EXAMPLE",
    "start_date": "2024-01-01",
    "end_date": "2024-03-01",
    "source_path": "data/raw/example_ohlcv.csv",
}


def _client(tmp_path: Path, *, production: bool = False, rate_limit: int = 20) -> TestClient:
    environment = "production" if production else "development"
    return TestClient(
        create_app(
            Settings(
                project_root=PROJECT_ROOT,
                database_url=f"sqlite:///{tmp_path / 'security.db'}",
                data_cache_directory=tmp_path / "cache",
                environment=environment,
                cors_origins=("http://localhost:3000", "http://127.0.0.1:3000", "https://terminal.example"),
                admin_api_key=ADMIN_KEY,
                mutation_rate_limit=rate_limit,
                mutation_rate_window_seconds=300,
            )
        )
    )


def _admin_headers() -> dict[str, str]:
    return {"X-FinAgent-Admin-Key": ADMIN_KEY}


def test_privileged_routes_require_a_valid_administrator_key(tmp_path: Path) -> None:
    client = _client(tmp_path)
    missing = client.post("/api/data/fetch", json=PAYLOAD)
    invalid = client.post("/api/data/fetch", json=PAYLOAD, headers={"X-FinAgent-Admin-Key": "wrong-key"})
    accepted = client.post(
        "/api/data/fetch",
        json={**PAYLOAD, "provider": "unknown_feed"},
        headers=_admin_headers(),
    )
    assert missing.status_code == invalid.status_code == 401
    assert missing.json()["error_code"] == "ADMIN_AUTH_REQUIRED"
    # Authentication passed; the following validation came from the provider,
    # not an authorization failure.
    assert accepted.status_code == 400
    assert accepted.json()["error_code"] == "UNKNOWN_PROVIDER"
    assert client.get("/api/health").status_code == 200


def test_production_requires_a_key_and_auth_bypass_is_development_only(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="FINAGENT_ADMIN_API_KEY"):
        Settings(
            project_root=PROJECT_ROOT,
            database_url=f"sqlite:///{tmp_path / 'missing-key.db'}",
            environment="production",
            cors_origins=("http://localhost:3000", "https://terminal.example"),
        )
    with pytest.raises(ValueError, match="development"):
        Settings(
            project_root=PROJECT_ROOT,
            database_url=f"sqlite:///{tmp_path / 'invalid-bypass.db'}",
            environment="test",
            admin_api_key=ADMIN_KEY,
            admin_auth_disabled=True,
        )


def test_mutation_rate_limit_is_bounded_and_returns_retry_after(tmp_path: Path) -> None:
    client = _client(tmp_path, rate_limit=1)
    payload = {"config_path": "config/missing.yaml"}
    first = client.post("/api/experiments/run", json=payload, headers=_admin_headers())
    limited = client.post("/api/experiments/run", json=payload, headers=_admin_headers())
    assert first.status_code == 400
    assert limited.status_code == 429
    assert limited.json()["error_code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1


def test_limiter_storage_is_capped_and_expires_old_requests() -> None:
    limiter = BoundedRateLimiter(limit=1, window_seconds=10, max_clients=2)
    assert limiter.check("one", now=0) is None
    assert limiter.check("two", now=0) is None
    assert limiter.check("three", now=0) is None
    assert len(limiter._requests) == 2  # implementation cap, not request input
    assert limiter.check("three", now=11) is None


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "symbol": "AAPL;DROP TABLE experiments"},
        {**PAYLOAD, "start_date": "2024-02-30"},
        {**PAYLOAD, "start_date": "2010-01-01", "end_date": "2025-01-02"},
        {**PAYLOAD, "source_path": "../../.env"},
    ],
)
def test_input_and_path_guardrails_reject_malformed_requests(tmp_path: Path, payload: dict[str, str]) -> None:
    client = _client(tmp_path)
    response = client.post("/api/data/fetch", json=payload, headers=_admin_headers())
    assert response.status_code in {400, 422}
    assert response.json()["error_code"] in {"INVALID_CONFIGURATION", "REQUEST_VALIDATION_ERROR"}


def test_route_path_and_sql_like_filters_are_not_interpreted_as_code(tmp_path: Path) -> None:
    client = _client(tmp_path)
    path = client.post("/api/experiments/run", json={"config_path": "config/../../outside.yaml"}, headers=_admin_headers())
    search = client.get("/api/experiments?search=%27%20OR%201%3D1%20--")
    assert path.status_code == 422
    assert search.status_code == 200
    assert search.json()["pagination"]["total"] == 0


def test_production_errors_and_system_metadata_do_not_reflect_paths_or_secrets(tmp_path: Path) -> None:
    client = _client(tmp_path, production=True)
    response = client.post("/api/data/fetch", json={**PAYLOAD, "source_path": "../../.env"}, headers=_admin_headers())
    system = client.get("/api/system")
    assert response.status_code == 400
    assert response.json()["message"] == "The request could not be processed."
    assert "source_path" not in response.json()["message"]
    assert system.status_code == 200
    assert system.json()["database_path"] == "redacted"
    assert "postgres" not in system.json()["database_path"].lower()
    for header in ("x-content-type-options", "referrer-policy", "x-frame-options", "permissions-policy", "content-security-policy", "strict-transport-security"):
        assert header in system.headers


def test_logging_redacts_credentials_and_candidate_generation_stays_bounded() -> None:
    value = "postgresql://researcher:password@example.test/finagent?api_key=top-secret Bearer token-value"
    sanitized = redact(value)
    assert "password" not in sanitized
    assert "top-secret" not in sanitized
    assert "token-value" not in sanitized
    with pytest.raises(ValueError, match="between 1 and 5"):
        CandidateGenerator(max_candidates=6)
