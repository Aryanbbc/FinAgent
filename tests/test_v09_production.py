"""Focused V0.9 production-polish coverage over the existing deterministic engine."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from finagent.api.main import create_app
from finagent.api.settings import Settings
from finagent.configuration import ConfigurationValidationError, validate_research_configuration
from finagent.database.db import Database
from finagent.runner import load_configuration, run_experiment

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def polished_client(tmp_path: Path) -> TestClient:
    config = yaml.safe_load((PROJECT_ROOT / "config" / "experiments.yaml").read_text(encoding="utf-8"))
    config["database_path"] = str(tmp_path / "research.db")
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    run_experiment(config_path, PROJECT_ROOT)
    run_experiment(config_path, PROJECT_ROOT)
    return TestClient(create_app(Settings(project_root=PROJECT_ROOT, database_url=f"sqlite:///{tmp_path / 'research.db'}", data_cache_directory=tmp_path / "cache")))


def test_standardized_errors_request_ids_and_paginated_filters(polished_client: TestClient) -> None:
    missing = polished_client.get("/api/experiments/EXP-999999")
    assert missing.status_code == 404
    assert missing.headers["X-Request-ID"]
    assert missing.json()["error_code"] == "NOT_FOUND"
    assert missing.json()["detail"]["code"] == "NOT_FOUND"  # V0.7/V0.8 client bridge

    invalid = polished_client.get("/api/experiments?sort_by=unsafe")
    assert invalid.status_code == 422
    assert invalid.json()["error_code"] == "REQUEST_VALIDATION_ERROR"

    listing = polished_client.get("/api/experiments?limit=1&status=critiqued&regime=sideways&sort_by=sharpe_ratio")
    assert listing.status_code == 200
    assert listing.json()["pagination"] == {"limit": 1, "offset": 0, "total": 2}
    identifier = listing.json()["items"][0]["experiment_id"]
    decisions = polished_client.get(f"/api/experiments/{identifier}/agent-decisions?limit=1")
    assert decisions.status_code == 200
    assert decisions.json()["pagination"]["total"] > 0


def test_health_reports_local_database_and_registry_status(polished_client: TestClient) -> None:
    response = polished_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database_status"] == "ok"
    system = polished_client.get("/api/system").json()
    assert system["database_integrity"] == "ok"
    assert "V0.8 data registry" in system["enabled_modules"]


def test_configuration_validation_rejects_unsafe_values_and_explains_warnings() -> None:
    configuration = load_configuration("config/experiments.yaml", PROJECT_ROOT)
    zero = copy.deepcopy(configuration)
    zero["backtest"]["position_fraction"] = 0
    assert "position_fraction is zero" in validate_research_configuration(zero).warnings[0]
    invalid = copy.deepcopy(configuration)
    invalid["experiment"]["starting_capital"] = 0
    with pytest.raises(ConfigurationValidationError, match="starting_capital"):
        validate_research_configuration(invalid)
    unsafe = copy.deepcopy(configuration)
    unsafe["application"]["live_trading_enabled"] = True
    with pytest.raises(ConfigurationValidationError, match="must remain false"):
        validate_research_configuration(unsafe)


def test_database_health_backup_and_environment_checker(tmp_path: Path) -> None:
    database = Database(tmp_path / "maintained.db")
    assert database.health_check()["status"] == "ok"
    target = database.backup_to(tmp_path / "backups" / "maintained.db")
    assert target.is_file()
    command = [str(PROJECT_ROOT / ".venv" / "bin" / "python"), "scripts/check_environment.py", "--database", str(tmp_path / "environment.db"), "--json"]
    result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["status"] == "ok"


def test_demo_configuration_is_bundled_and_valid() -> None:
    config = load_configuration("config/demo.yaml", PROJECT_ROOT)
    assert config["application"]["demo_mode"] is True
    assert config["experiment"]["dataset"] == "data/raw/example_ohlcv.csv"
