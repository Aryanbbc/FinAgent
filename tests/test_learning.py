from __future__ import annotations

import copy
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.learning.candidate_generator import CandidateGenerator, ConfigurationConstraintError
from finagent.learning.learning_agent import LearningAgent
from finagent.learning.models import (
    CandidateProposal,
    CandidateReasonCode,
    ConfigurationVersion,
    LearningAgentInput,
    PromotionStatus,
    ValidationMetrics,
    WalkForwardEvaluation,
    WalkForwardWindow,
)
from finagent.learning.promotion_gate import PromotionGate, PromotionGateConfig
from finagent.learning.walk_forward import WalkForwardConfig, WalkForwardEvaluator, chronological_splits
from finagent.learning.workflow import run_improvement
from finagent.runner import run_experiment


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _configuration() -> dict:
    return {
        "experiment": {"asset": "TEST", "dataset": str(PROJECT_ROOT / "data/raw/example_ohlcv.csv"), "starting_capital": 10000.0},
        "features": {"simple_return": True, "rolling_volatility": {"window": 5}},
        "strategy": {"name": "moving_average", "parameters": {"fast_window": 3, "slow_window": 8}},
        "backtest": {"annualization_factor": 252, "transaction_costs": {"percentage_fee": 0.001, "fixed_fee": 0.0}},
        "regime": {"enabled": True},
        "agents": {
            "enabled": False,
            "strategy": {
                "available_strategies": {
                    "moving_average": {"fast_window": 3, "slow_window": 8},
                    "momentum": {"lookback_window": 4, "entry_threshold": 0.0, "exit_threshold": -0.02},
                    "mean_reversion": {"lookback_window": 5, "entry_zscore": -1.0, "exit_zscore": 0.0},
                },
                "regime_strategy_map": {"bull": "momentum", "bear": "moving_average"},
                "strategy_weights": {},
            },
            "risk": {"minimum_confidence": 0.15, "max_position_size": 1.0, "max_volatility": 0.5},
        },
    }


def _learning_input(configuration: dict | None = None) -> LearningAgentInput:
    return LearningAgentInput(
        current_version_id="FinAgent-A0001",
        current_configuration=configuration or _configuration(),
        memory={"experiment_id": "EXP-000001"},
        critique={"reason_codes": ["UNDERPERFORMS_BENCHMARK"]},
        boundaries={
            "moving_average_fast_window": {"values": [2, 4]},
            "momentum_window": {"values": [3, 6]},
        },
        search_mode="neighborhood",
        max_candidates=4,
    )


def _window(index: int, parent: ValidationMetrics, candidate: ValidationMetrics) -> WalkForwardWindow:
    return WalkForwardWindow(
        index,
        "2024-01-01T00:00:00+00:00",
        "2024-01-05T00:00:00+00:00",
        "2024-01-06T00:00:00+00:00",
        "2024-01-10T00:00:00+00:00",
        5,
        5,
        parent,
        candidate,
    )


def _evaluation(candidate_id: str = "CAND-0001", improved: bool = True) -> WalkForwardEvaluation:
    parent = ValidationMetrics(0.01, 0.5, -0.05, 0.5, 1.0, 3)
    candidate = ValidationMetrics(0.03 if improved else 0.0, 0.9 if improved else 0.2, -0.04, 0.4, 1.0, 3)
    return WalkForwardEvaluation(
        candidate_id,
        "FinAgent-A0001",
        (_window(1, parent, candidate), _window(2, parent, candidate)),
        parent,
        candidate,
    )


def test_candidate_generation_is_allowlisted_and_reproducible() -> None:
    agent_input = _learning_input()
    generated_once = LearningAgent().propose(agent_input)
    generated_twice = LearningAgent().propose(agent_input)

    assert generated_once == generated_twice
    assert generated_once[0].candidate_id == "CAND-0001"
    assert {change.parameter for candidate in generated_once for change in candidate.parameter_changes} <= {
        "moving_average_fast_window",
        "momentum_window",
    }
    assert agent_input.current_configuration == _configuration()
    with pytest.raises(ConfigurationConstraintError, match="Unapproved"):
        CandidateGenerator().generate(agent_input, ("arbitrary_code",))


def test_candidate_constraints_reject_invalid_strategy_and_risk_configuration() -> None:
    invalid = _configuration()
    invalid["agents"]["strategy"]["available_strategies"]["moving_average"]["fast_window"] = 8
    with pytest.raises(ConfigurationConstraintError, match="fast_window"):
        CandidateGenerator.validate_configuration(invalid)
    invalid = _configuration()
    invalid["agents"]["risk"]["max_position_size"] = 1.1
    with pytest.raises(ConfigurationConstraintError, match="position size"):
        CandidateGenerator.validate_configuration(invalid)


def test_grid_generation_supports_only_configured_weights_and_regime_mappings() -> None:
    agent_input = _learning_input()
    agent_input = LearningAgentInput(
        current_version_id=agent_input.current_version_id,
        current_configuration=agent_input.current_configuration,
        memory=agent_input.memory,
        critique=agent_input.critique,
        boundaries={
            "strategy_weights": {"values": [{"momentum": 0.5}]},
            "regime_strategy_mappings": {"values": [{"bull": "moving_average", "bear": "moving_average"}]},
        },
        search_mode="grid",
        max_candidates=2,
    )
    candidates = CandidateGenerator(mode="grid", max_candidates=2).generate(
        agent_input, ("strategy_weights", "regime_strategy_mappings")
    )
    assert len(candidates) == 1
    assert {change.parameter for change in candidates[0].parameter_changes} == {
        "strategy_weights",
        "regime_strategy_mappings",
    }
    assert candidates[0].configuration["agents"]["strategy"]["strategy_weights"] == {"momentum": 0.5}


def test_walk_forward_splits_are_chronological_non_overlapping_and_no_lookahead() -> None:
    configuration = WalkForwardConfig(train_size=15, test_size=10, step_size=10, min_windows=2)
    splits = chronological_splits(40, configuration)
    assert [(item.train_start, item.train_end, item.test_start, item.test_end) for item in splits] == [
        (0, 15, 15, 25),
        (10, 25, 25, 35),
    ]
    assert splits[0].test_end <= splits[1].test_start

    raw_data = pd.read_csv(PROJECT_ROOT / "data/raw/example_ohlcv.csv")
    raw_data["timestamp"] = pd.to_datetime(raw_data["timestamp"], utc=True)
    candidate = CandidateProposal(
        "CAND-0001", "FinAgent-A0001", _configuration(), (), (CandidateReasonCode.NEIGHBORHOOD_SEARCH,)
    )
    evaluator = WalkForwardEvaluator(configuration)
    first_evaluation = evaluator.evaluate(raw_data, _configuration(), candidate)
    changed_future = raw_data.copy()
    changed_future.loc[25:, "close"] *= 100
    second_evaluation = evaluator.evaluate(changed_future, _configuration(), candidate)
    assert first_evaluation.windows[0].candidate_metrics == second_evaluation.windows[0].candidate_metrics


def test_promotion_gate_requires_consistent_risk_adjusted_oos_results() -> None:
    gate = PromotionGate(PromotionGateConfig(minimum_sharpe_improvement=0.1, minimum_window_pass_rate=1.0, minimum_trades=2))
    accepted = gate.decide(_evaluation())
    rejected = gate.decide(_evaluation(improved=False))

    assert accepted.status == PromotionStatus.PROMOTED
    assert CandidateReasonCode.PROMOTED in accepted.reason_codes
    assert rejected.status == PromotionStatus.REJECTED
    assert CandidateReasonCode.OUT_OF_SAMPLE_SHARPE_NOT_IMPROVED in rejected.reason_codes
    assert CandidateReasonCode.INCONSISTENT_OUT_OF_SAMPLE_RESULTS in rejected.reason_codes


def test_promotion_gate_rejects_insufficient_walk_forward_sample() -> None:
    unavailable = ValidationMetrics(None, None, None, None, 0.0, 0)
    evaluation = WalkForwardEvaluation("CAND-0001", "FinAgent-A0001", (), unavailable, unavailable)
    decision = PromotionGate(PromotionGateConfig(minimum_windows=2)).decide(evaluation)
    assert decision.status == PromotionStatus.REJECTED
    assert CandidateReasonCode.INSUFFICIENT_SAMPLE in decision.reason_codes
    assert CandidateReasonCode.INVALID_METRICS in decision.reason_codes


def test_sqlite_persists_validation_and_versions_immutably(tmp_path) -> None:
    repository = ExperimentRepository(Database(tmp_path / "learning.db"))
    baseline = ConfigurationVersion(
        "FinAgent-A0001",
        None,
        None,
        _configuration(),
        None,
        PromotionStatus.BASELINE,
        (CandidateReasonCode.MEMORY_RETRIEVED,),
        datetime.now(UTC).isoformat(),
    )
    repository.save_configuration_version(baseline)
    candidate = CandidateProposal(
        "CAND-0001",
        baseline.version_id,
        _configuration(),
        (),
        (CandidateReasonCode.NEIGHBORHOOD_SEARCH,),
    )
    repository.save_candidate_configuration(candidate)
    decision = PromotionGate(PromotionGateConfig(minimum_window_pass_rate=1.0)).decide(_evaluation())
    repository.save_walk_forward_evaluation(_evaluation(), decision)

    assert repository.current_configuration_version() == baseline
    assert repository.get_candidate_configuration(candidate.candidate_id) == candidate
    assert len(repository.get_validation_windows(candidate.candidate_id)) == 2
    assert repository.get_candidate_evaluation(candidate.candidate_id) == decision
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_configuration_version(baseline)


def test_learning_can_be_disabled_and_opt_in_workflow_preserves_old_runner(tmp_path) -> None:
    database_path = tmp_path / "experiments.db"
    experiment_config = _configuration()
    experiment_config.update({"database_path": str(database_path), "critic": {"enabled": True}})
    source_path = tmp_path / "source.yaml"
    source_path.write_text(yaml.safe_dump(experiment_config), encoding="utf-8")
    experiment_id, results = run_experiment(source_path, PROJECT_ROOT)
    assert results["agents"]["enabled"] is False
    assert results["memory"]["enabled"] is True

    disabled_path = tmp_path / "disabled.yaml"
    disabled_path.write_text(yaml.safe_dump({"source_experiment_config": str(source_path), "learning": {"enabled": False}}), encoding="utf-8")
    assert run_improvement(disabled_path, PROJECT_ROOT) is None

    improvement_path = tmp_path / "improvement.yaml"
    improvement_path.write_text(
        yaml.safe_dump(
            {
                "source_experiment_config": str(source_path),
                "database_path": str(database_path),
                "learning": {
                    "enabled": True,
                    "memory_experiment_id": experiment_id,
                    "search": {"mode": "neighborhood", "max_candidates": 1, "boundaries": {"momentum_window": {"values": [3]}}},
                    "walk_forward": {"train_size": 15, "test_size": 10, "step_size": 10, "min_windows": 2},
                    "promotion_gate": {"minimum_sharpe_improvement": 10.0, "minimum_window_pass_rate": 1.0, "minimum_trades": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    result = run_improvement(improvement_path, PROJECT_ROOT)
    assert result is not None
    assert result.current_version.version_id == "FinAgent-A0001"
    assert len(result.candidates) == len(result.evaluations) == len(result.decisions) == 1
    assert result.promoted_version is None
    assert ExperimentRepository(Database(database_path)).latest_candidate_evaluation() == result.decisions[0]
