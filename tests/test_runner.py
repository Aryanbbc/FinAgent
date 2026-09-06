from __future__ import annotations

from pathlib import Path

import yaml

from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.regime.models import MarketRegime
from finagent.runner import run_experiment


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_v02_runner_persists_regime_results_without_changing_backtest_flow(tmp_path) -> None:
    database_path = tmp_path / "experiments.db"
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "experiment": {
                    "asset": "TEST",
                    "dataset": str(PROJECT_ROOT / "data/raw/example_ohlcv.csv"),
                    "starting_capital": 100000.0,
                    "random_seed": 42,
                },
                "database_path": str(database_path),
                "strategy": {
                    "name": "momentum",
                    "parameters": {"lookback_window": 5, "entry_threshold": 0.0, "exit_threshold": -0.02},
                },
                "regime": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    experiment_id, results = run_experiment(config_path, PROJECT_ROOT)
    repository = ExperimentRepository(Database(database_path))
    observations = repository.get_regime_observations(experiment_id)

    assert results["regime"]["enabled"] is True
    assert results["regime"]["observations"] == 40
    assert results["regime"]["latest"]["regime"] in {regime.value for regime in MarketRegime}
    assert len(observations) == 40
    assert results["metrics"]["number_of_trades"] == 1


def test_v01_style_run_remains_available_when_regime_analysis_is_disabled(tmp_path) -> None:
    database_path = tmp_path / "v01-style.db"
    config_path = tmp_path / "v01-style.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "experiment": {
                    "asset": "TEST",
                    "dataset": str(PROJECT_ROOT / "data/raw/example_ohlcv.csv"),
                    "starting_capital": 100000.0,
                    "random_seed": 42,
                },
                "database_path": str(database_path),
                "strategy": {
                    "name": "momentum",
                    "parameters": {"lookback_window": 5, "entry_threshold": 0.0, "exit_threshold": -0.02},
                },
                "regime": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    experiment_id, results = run_experiment(config_path, PROJECT_ROOT)

    assert results["regime"]["enabled"] is False
    assert results["agents"]["enabled"] is False
    assert results["metrics"]["number_of_trades"] == 1
    assert ExperimentRepository(Database(database_path)).get_regime_observations(experiment_id).empty


def test_v03_agent_mode_persists_a_full_decision_chain(tmp_path) -> None:
    database_path = tmp_path / "v03.db"
    config_path = tmp_path / "v03.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "experiment": {
                    "asset": "TEST",
                    "dataset": str(PROJECT_ROOT / "data/raw/example_ohlcv.csv"),
                    "starting_capital": 100000.0,
                    "random_seed": 42,
                },
                "database_path": str(database_path),
                "strategy": {
                    "name": "momentum",
                    "parameters": {"lookback_window": 5, "entry_threshold": 0.0, "exit_threshold": -0.02},
                },
                "regime": {"enabled": True},
                "agents": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    experiment_id, results = run_experiment(config_path, PROJECT_ROOT)
    decisions = ExperimentRepository(Database(database_path)).get_agent_decisions(experiment_id)

    assert results["agents"]["enabled"] is True
    assert results["agents"]["observations"] == 40
    assert results["agents"]["latest"]["proposal"]["selected_strategy"]
    assert len(decisions) == 40
    assert {"risk_reason_code", "strategy_reason_codes"}.issubset(decisions.columns)
