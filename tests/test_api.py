"""Integration coverage for the V0.7 FastAPI facade over the established workflows."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from finagent.api.main import create_app
from finagent.api.settings import Settings
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

    settings = Settings(project_root=PROJECT_ROOT, database_url=f"sqlite:///{temporary / 'api.db'}")
    return TestClient(create_app(settings)), experiment_id, validation.experiment_id


def test_health_and_openapi(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    assert api.get("/api/health").json()["status"] == "ok"
    assert api.get("/openapi.json").status_code == 200


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


def test_missing_artifacts_return_consistent_404(client: tuple[TestClient, str, str]) -> None:
    api, _, _ = client
    response = api.get("/api/experiments/EXP-999999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"
