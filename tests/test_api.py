"""Integration coverage for the V0.7 FastAPI facade over the established workflows."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from finagent.api.main import create_app
from finagent.api.settings import Settings
from finagent.services.research_service import ResearchService
from finagent.runner import run_experiment
from finagent.validation.workflow import run_research_validation

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> tuple[TestClient, str, str]:
    """Populate an isolated DB through unmodified V0.1–V0.6 workflows."""
    temporary = tmp_path_factory.mktemp("api")
    experiment_config = yaml.safe_load((PROJECT_ROOT / "config" / "experiments.yaml").read_text(encoding="utf-8"))
    experiment_config["database_path"] = str(temporary / "api.db")
    experiment_path = temporary / "experiment.yaml"
    experiment_path.write_text(yaml.safe_dump(experiment_config), encoding="utf-8")
    experiment_id, _ = run_experiment(experiment_path, PROJECT_ROOT)

    validation_config = yaml.safe_load((PROJECT_ROOT / "config" / "validation.yaml").read_text(encoding="utf-8"))
    validation_config["source_experiment_config"] = str(experiment_path)
    validation_config["validation"]["bootstrap"]["samples"] = 10
    validation_path = temporary / "validation.yaml"
    validation_path.write_text(yaml.safe_dump(validation_config), encoding="utf-8")
    validation = run_research_validation(validation_path, PROJECT_ROOT)
    assert validation is not None

    settings = Settings(
        project_root=PROJECT_ROOT,
        database_url=f"sqlite:///{temporary / 'api.db'}",
        data_cache_directory=temporary / "cache",
        admin_api_key="api-test-key",
        # This shared integration fixture invokes several different protected
        # routes; dedicated security coverage verifies the production default.
        mutation_rate_limit=20,
    )
    return TestClient(create_app(settings), headers={"X-FinAgent-Admin-Key": "api-test-key"}), experiment_id, validation.experiment_id


def test_health_and_openapi(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    assert api.get("/api/health").json()["status"] == "ok"
    assert api.get("/openapi.json").status_code == 200


def test_system_exposes_a_stable_non_sensitive_database_identity(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    first = api.get("/api/system").json()["database_identity"]
    second = api.get("/api/system").json()["database_identity"]
    assert first == second
    assert first.startswith("sqlite:")
    assert "/" not in first and "api.db" not in first
    payload = api.get("/api/system").json()
    assert all(isinstance(payload[key], int) and payload[key] >= 0 for key in ("critique_count", "experiment_memory_count", "candidate_evaluation_count"))


def test_list_and_experiment_detail_preserve_existing_results(client: tuple[TestClient, str, str]) -> None:
    api, experiment_id, _ = client
    listing = api.get("/api/experiments?strategy=momentum")
    assert listing.status_code == 200
    assert listing.json()["pagination"]["total"] >= 1
    detail = api.get(f"/api/experiments/{experiment_id}")
    assert detail.status_code == 200
    assert detail.json()["experiment_id"] == experiment_id
    assert detail.json()["metrics"]["number_of_trades"] >= 0


def test_agents_critique_and_regimes_are_exposed_as_structured_records(client: tuple[TestClient, str, str]) -> None:
    api, experiment_id, _ = client
    assert api.get(f"/api/experiments/{experiment_id}/agent-decisions").json()["items"]
    critique = api.get(f"/api/experiments/{experiment_id}/critique")
    assert critique.status_code == 200
    assert "reason_codes" in critique.json()
    assert api.get(f"/api/experiments/{experiment_id}/regimes").json()["distribution"]


def test_validation_and_control_request_validation(client: tuple[TestClient, str, str]) -> None:
    api, _, validation_experiment_id = client
    response = api.get(f"/api/validation/{validation_experiment_id}")
    assert response.status_code == 200
    assert "robustness" in response.json()
    assert api.post("/api/experiments/run", json={"config_path": "../../outside.yaml"}).status_code == 422
    assert api.post("/api/improvements/run", json={}).status_code == 422
    assert api.post("/api/validation/run", json={"config_path": "config/missing.yaml"}).status_code == 400


def test_improvement_context_exposes_only_persisted_summary_fields(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    response = api.get("/api/improvements/context")
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates_generated"] >= payload["candidates_evaluated"]
    assert payload["gate_thresholds_persisted"] is False
    assert payload["cycle_boundaries_persisted"] is False


def test_missing_artifacts_return_consistent_404(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    response = api.get("/api/experiments/EXP-999999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_v08_data_routes_register_local_csv_without_network(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    providers = api.get("/api/data/providers").json()
    assert {item["provider"] for item in providers} >= {"auto", "local_csv", "stooq", "twelve_data", "yahoo_finance"}
    twelve = next(item for item in providers if item["provider"] == "twelve_data")
    assert twelve["requires_credentials"] is True
    assert "api_key" not in twelve and "TWELVE_DATA_API_KEY" not in twelve
    fetched = api.post(
        "/api/data/fetch",
        json={
            "provider": "local_csv", "symbol": "EXAMPLE", "start_date": "2024-01-01", "end_date": "2024-03-01",
            "interval": "1d", "source_path": "data/raw/example_ohlcv.csv", "force_refresh": False,
        },
    )
    assert fetched.status_code == 200
    assert fetched.json()["requested_provider"] == "local_csv"
    assert fetched.json()["actual_provider"] == "local_csv"
    assert not fetched.json()["fallback_used"]
    dataset_id = fetched.json()["dataset"]["dataset_id"]
    assert api.get("/api/data/datasets").json()["pagination"]["total"] == 1
    detail = api.get(f"/api/data/datasets/{dataset_id}")
    assert detail.status_code == 200 and detail.json()["sample_rows"]
    assert detail.json()["metadata"]["actual_provider"] == "local_csv"
    series = api.get(f"/api/data/datasets/{dataset_id}/ohlcv?limit=20")
    assert series.status_code == 200 and 0 < len(series.json()["items"]) <= 20
    assert api.post("/api/data/validate", json={"dataset_id": dataset_id}).status_code == 200
    # Controlled API runs bind to Settings.DATABASE_URL and can select durable
    # registry data instead of relying on a YAML-configured local CSV path.
    run = api.post("/api/experiments/run", json={"config_path": "config/experiments.yaml", "dataset_id": dataset_id})
    assert run.status_code == 200
    assert run.json()["metadata"]["dataset_id"] == dataset_id
    assert api.get(f"/api/experiments/{run.json()['experiment_id']}").status_code == 200


def test_registry_selected_dataset_is_authoritative_for_experiment_asset(client: tuple[TestClient, str, str]) -> None:
    """A template's EXAMPLE asset cannot contaminate a selected AAPL dataset."""
    api, _, _ = client
    fetched = api.post(
        "/api/data/fetch",
        json={
            "provider": "local_csv", "symbol": "AAPL", "start_date": "2024-01-01", "end_date": "2024-03-01",
            "interval": "1d", "source_path": "data/raw/example_ohlcv.csv", "force_refresh": False,
        },
    )
    assert fetched.status_code == 200
    run = api.post(
        "/api/experiments/run",
        json={"config_path": "config/experiments.yaml", "dataset_id": fetched.json()["dataset"]["dataset_id"]},
    )
    assert run.status_code == 200
    assert api.get(f"/api/experiments/{run.json()['experiment_id']}").json()["asset"] == "AAPL"


def test_data_provider_failures_return_structured_provenance(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    response = api.post(
        "/api/data/fetch",
        json={"provider": "unknown_feed", "symbol": "AAPL", "start_date": "2024-01-01", "end_date": "2024-01-10"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "UNKNOWN_PROVIDER"
    assert payload["details"] == {
        "provider": "unknown_feed", "status": None, "reason": "Unknown historical data provider: unknown_feed",
        "retryable": False, "fallback_used": False,
    }


def test_read_filters_reject_invalid_dates_and_normalize_asset_case(client: tuple[TestClient, str, str]) -> None:
    api, experiment_id, _ = client
    assert api.get("/api/data/datasets?start_date=2024-99-01").status_code == 400
    assert api.get("/api/experiments?start_date=2024-99-01").status_code == 400
    filtered = api.get("/api/experiments?asset=example")
    assert filtered.status_code == 200
    assert experiment_id in {item["experiment_id"] for item in filtered.json()["items"]}


def test_terminal_read_endpoints_use_persisted_market_and_activity_data(client: tuple[TestClient, str, str]) -> None:
    """The terminal receives bounded canonical data without recomputing research."""
    api, experiment_id, _ = client
    market = api.get(f"/api/experiments/{experiment_id}/market-data?limit=50")
    assert market.status_code == 200
    assert market.json()["items"]
    assert len(market.json()["items"]) <= 50
    activity = api.get("/api/experiments/activity/recent?limit=100")
    assert activity.status_code == 200
    types = {item["event_type"] for item in activity.json()["items"]}
    assert {"EXPERIMENT_COMPLETED", "TRADE_SIMULATED", "SIGNAL_CREATED"} <= types


def test_experiment_market_data_allows_project_controlled_cache_sources(tmp_path: Path) -> None:
    """Legacy direct-path experiments can still drive the terminal chart safely.

    AAPL's isolated reproducible configuration predates registry-backed
    dataset IDs and intentionally reads an immutable file under data/cache.
    The API must expose that controlled source, while never accepting an
    arbitrary file path from a persisted experiment record.
    """
    cache_path = tmp_path / "data" / "cache" / "aapl_fixture.csv"
    cache_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp": ["2024-01-02T00:00:00+00:00", "2024-01-03T00:00:00+00:00"],
            "open": [100.0, 101.0], "high": [102.0, 103.0], "low": [99.0, 100.0],
            "close": [101.0, 102.0], "volume": [1_000.0, 1_200.0],
        }
    ).to_csv(cache_path, index=False)
    settings = Settings(
        project_root=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'cache-source.db'}",
        data_cache_directory=tmp_path / "data" / "cache",
    )
    service = ResearchService(settings)
    service.ensure_database_ready()
    experiment_id = service.repository.save_experiment(
        strategy="momentum", asset="AAPL", dataset="data/cache/aapl_fixture.csv",
        start_date="2024-01-02", end_date="2024-01-03", starting_capital=100_000.0,
        random_seed=42, configuration={"experiment": {"asset": "AAPL"}}, results={}, metrics={},
        trades=pd.DataFrame(),
    )

    market_data = service.experiment_market_data(experiment_id, limit=50)

    assert [row["close"] for row in market_data["items"]] == [101.0, 102.0]


def test_controlled_terminal_run_overrides_are_bounded_and_recorded(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    response = api.post(
        "/api/experiments/run",
        json={
            "config_path": "config/experiments.yaml", "strategy_name": "moving_average", "agents_enabled": False,
            "starting_capital": 125000, "percentage_fee": 0.002, "fixed_fee": 2.0,
            "position_fraction": 0.5, "start_date": "2024-01-10", "end_date": "2024-03-01",
        },
    )
    assert response.status_code == 200
    detail = api.get(f"/api/experiments/{response.json()['experiment_id']}").json()
    assert detail["strategy"] == "moving_average"
    assert detail["starting_capital"] == 125000
    assert detail["start_date"] >= "2024-01-10"
