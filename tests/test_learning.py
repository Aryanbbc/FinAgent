from __future__ import annotations

import copy
import json
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
from finagent.runner import load_configuration, run_experiment


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


def test_candidate_generation_interleaves_levers_and_removes_duplicate_configurations() -> None:
    configuration = _configuration()
    agent_input = LearningAgentInput(
        current_version_id="FinAgent-A0001",
        current_configuration=configuration,
        memory={"experiment_id": "EXP-000001"},
        critique={"reason_codes": ["HIGH_DRAWDOWN", "UNDERPERFORMS_BENCHMARK"]},
        boundaries={
            "maximum_position_size": {"values": [0.75]},
            "maximum_volatility": {"values": [0.4, 0.6]},
            "momentum_window": {"values": [3, 3, 6]},
        },
        search_mode="neighborhood",
        max_candidates=3,
    )

    candidates = LearningAgent().propose(agent_input)

    assert len(candidates) == 3
    assert [candidate.parameter_changes[0].parameter for candidate in candidates] == [
        "maximum_position_size",
        "maximum_volatility",
        "momentum_window",
    ]
    fingerprints = {
        yaml.safe_dump(candidate.configuration, sort_keys=True)
        for candidate in CandidateGenerator(mode="neighborhood", max_candidates=5).generate(
            LearningAgentInput(
                current_version_id=agent_input.current_version_id,
                current_configuration=configuration,
                memory=agent_input.memory,
                critique=agent_input.critique,
                boundaries={"momentum_window": {"values": [3, 3]}},
                search_mode="neighborhood",
                max_candidates=5,
            ),
            ("momentum_window",),
        )
    }
    assert len(fingerprints) == 1


def test_turnover_profiles_apply_only_allowlisted_consumed_changes_and_deduplicate() -> None:
    configuration = _configuration()
    profile = {
        "changes": {
            "execution_controls": {"minimum_holding_period_bars": 20, "reentry_cooldown_bars": 10},
            "strategy_weights": {"momentum": 0.1},
        }
    }
    agent_input = LearningAgentInput(
        current_version_id="FinAgent-A0001",
        current_configuration=configuration,
        memory={"experiment_id": "EXP-000001"},
        critique={"reason_codes": [CandidateReasonCode.EXCESSIVE_TURNOVER.value]},
        boundaries={},
        max_candidates=5,
        candidate_profiles=(profile, copy.deepcopy(profile)),
    )

    candidates = LearningAgent().propose(agent_input)

    assert len(candidates) == 1
    assert [change.parameter for change in candidates[0].parameter_changes] == ["execution_controls", "strategy_weights"]
    assert candidates[0].configuration["backtest"]["execution_controls"] == profile["changes"]["execution_controls"]
    assert candidates[0].configuration["agents"]["strategy"]["strategy_weights"] == {"momentum": 0.1}


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


def test_aapl_walk_forward_plan_has_multiple_forward_only_windows() -> None:
    configuration = WalkForwardConfig(train_size=504, test_size=126, step_size=126, min_windows=5)
    splits = chronological_splits(2176, configuration)

    assert len(splits) == 13
    assert all(split.train_end == split.test_start for split in splits)
    assert all(left.test_end <= right.test_start for left, right in zip(splits, splits[1:]))
    assert splits[0] == type(splits[0])(0, 504, 504, 630)
    assert splits[-1] == type(splits[-1])(1512, 2016, 2016, 2142)


def test_walk_forward_treats_flat_complete_oos_window_as_zero_sharpe() -> None:
    raw_data = pd.read_csv(PROJECT_ROOT / "data/raw/example_ohlcv.csv")
    raw_data["timestamp"] = pd.to_datetime(raw_data["timestamp"], utc=True)
    raw_data[["open", "high", "low", "close"]] = 100.0
    configuration = _configuration()
    candidate = CandidateProposal(
        "CAND-0001", "FinAgent-A0001", configuration, (), (CandidateReasonCode.NEIGHBORHOOD_SEARCH,)
    )

    evaluation = WalkForwardEvaluator(WalkForwardConfig(train_size=15, test_size=10, step_size=10, min_windows=2)).evaluate(
        raw_data, configuration, candidate
    )

    assert all(window.candidate_metrics.sharpe_ratio == 0.0 for window in evaluation.windows)
    assert evaluation.candidate_aggregate.sharpe_ratio == 0.0


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
    assert repository.candidate_configuration_fingerprints(baseline.version_id) == {
        json.dumps(candidate.configuration, sort_keys=True, separators=(",", ":"))
    }
    assert repository.candidate_configuration_fingerprints("FinAgent-A9999") == set()
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
    repository = ExperimentRepository(Database(database_path))
    assert repository.latest_candidate_evaluation() == result.decisions[0]
    assert [version.version_id for version in repository.configuration_version_history()] == ["FinAgent-A0001"]

    # A second invocation must retain the immutable evidence and skip the
    # exact configuration rather than evaluating the same OOS path again.
    repeated = run_improvement(improvement_path, PROJECT_ROOT)
    assert repeated is not None
    assert repeated.candidates == repeated.evaluations == repeated.decisions == ()


def test_explicit_aapl_parent_source_persists_real_candidate_evidence(tmp_path) -> None:
    """Exercise the same explicit parent binding used by the protected API route."""
    database_path = tmp_path / "aapl.db"
    data_path = tmp_path / "aapl.csv"
    timestamps = pd.date_range("2021-01-04", periods=80, freq="B", tz="UTC")
    close = pd.Series(range(80), dtype=float).mul(0.3).add(120.0)
    pd.DataFrame({
        "timestamp": timestamps, "open": close - 0.2, "high": close + 0.5,
        "low": close - 0.5, "close": close, "volume": 1_000.0,
    }).to_csv(data_path, index=False)
    source = _configuration()
    source["experiment"].update({"asset": "AAPL", "dataset": str(data_path)})
    source.update({"database_path": str(database_path), "critic": {"enabled": True}})
    source_path = tmp_path / "aapl_experiment.yaml"
    source_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    experiment_id, _ = run_experiment(source_path, PROJECT_ROOT)
    persisted_source = load_configuration(source_path, PROJECT_ROOT)

    improvement_path = tmp_path / "aapl_improvement.yaml"
    improvement_path.write_text(
        yaml.safe_dump(
            {
                # The persisted source override below is authoritative; this
                # unrelated path proves the workflow never falls back to it.
                "source_experiment_config": "config/experiments.yaml",
                "learning": {
                    "enabled": True,
                    "search": {"mode": "neighborhood", "max_candidates": 1, "boundaries": {"moving_average_fast_window": {"values": [2]}}},
                    "walk_forward": {"train_size": 20, "test_size": 10, "step_size": 10, "min_windows": 2},
                    # Deliberately strict: this confirms that rejection still
                    # persists evidence and never creates a promoted version.
                    "promotion_gate": {"minimum_sharpe_improvement": 10.0, "minimum_window_pass_rate": 1.0, "minimum_trades": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    result = run_improvement(
        improvement_path,
        PROJECT_ROOT,
        source_configuration=persisted_source,
        memory_experiment_id=experiment_id,
    )

    assert result is not None
    assert result.current_version.configuration["experiment"]["asset"] == "AAPL"
    assert len(result.candidates) == len(result.evaluations) == len(result.decisions) == 1
    assert result.promoted_version is None
    repository = ExperimentRepository(Database(database_path))
    assert repository.get_experiment_memory(experiment_id) is not None
    assert repository.get_candidate_evaluation(result.candidates[0].candidate_id) == result.decisions[0]
    assert repository.get_validation_windows(result.candidates[0].candidate_id)


def test_learning_uses_only_matching_asset_dataset_memory_and_baseline(tmp_path) -> None:
    database_path = tmp_path / "isolated.db"
    source = _configuration()
    source.update({"database_path": str(database_path), "critic": {"enabled": True}})
    source_path = tmp_path / "source.yaml"
    source_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    source_experiment_id, _ = run_experiment(source_path, PROJECT_ROOT)

    unrelated = copy.deepcopy(source)
    unrelated["experiment"]["asset"] = "EXAMPLE"
    unrelated_path = tmp_path / "unrelated.yaml"
    unrelated_path.write_text(yaml.safe_dump(unrelated), encoding="utf-8")
    unrelated_experiment_id, _ = run_experiment(unrelated_path, PROJECT_ROOT)

    repository = ExperimentRepository(Database(database_path))
    unrelated_configuration = load_configuration(unrelated_path, PROJECT_ROOT)
    repository.save_configuration_version(
        ConfigurationVersion(
            "FinAgent-A0001",
            None,
            None,
            unrelated_configuration,
            None,
            PromotionStatus.BASELINE,
            (CandidateReasonCode.MEMORY_RETRIEVED,),
            datetime.now(UTC).isoformat(),
        )
    )
    source_configuration = load_configuration(source_path, PROJECT_ROOT)
    assert repository.latest_experiment_memory_for_source(
        asset="TEST",
        dataset=source_configuration["experiment"]["dataset"],
        configuration=source_configuration,
    ).experiment_id == source_experiment_id
    assert repository.latest_experiment_memory().experiment_id == unrelated_experiment_id

    improvement_path = tmp_path / "improvement.yaml"
    improvement_path.write_text(
        yaml.safe_dump(
            {
                "source_experiment_config": str(source_path),
                "database_path": str(database_path),
                "learning": {
                    "enabled": True,
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
    assert result.current_version.version_id == "FinAgent-A0002"
    assert result.current_version.configuration["experiment"]["asset"] == "TEST"
    assert result.candidates[0].parent_version_id == "FinAgent-A0002"


def test_duplicate_out_of_sample_outcomes_are_rejected_and_only_one_version_is_promoted(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "outcomes.db"
    experiment_config = _configuration()
    experiment_config.update({"database_path": str(database_path), "critic": {"enabled": True}})
    source_path = tmp_path / "source.yaml"
    source_path.write_text(yaml.safe_dump(experiment_config), encoding="utf-8")
    run_experiment(source_path, PROJECT_ROOT)

    def identical_outcomes(self, market_data, parent_configuration, candidate):
        return _evaluation(candidate.candidate_id, improved=True)

    monkeypatch.setattr(WalkForwardEvaluator, "evaluate", identical_outcomes)
    improvement_path = tmp_path / "improvement.yaml"
    improvement_path.write_text(
        yaml.safe_dump(
            {
                "source_experiment_config": str(source_path),
                "database_path": str(database_path),
                "learning": {
                    "enabled": True,
                    "search": {"mode": "neighborhood", "max_candidates": 2, "boundaries": {"momentum_window": {"values": [3, 6]}}},
                    "walk_forward": {"train_size": 15, "test_size": 10, "step_size": 10, "min_windows": 2},
                    "promotion_gate": {"minimum_sharpe_improvement": 0.1, "minimum_window_pass_rate": 1.0, "minimum_trades": 2},
                },
            }
        ),
        encoding="utf-8",
    )
    result = run_improvement(improvement_path, PROJECT_ROOT)

    assert result is not None
    assert result.promoted_version is not None
    assert result.decisions[0].status == PromotionStatus.PROMOTED
    assert result.decisions[1].status == PromotionStatus.REJECTED
    assert CandidateReasonCode.DUPLICATE_OUT_OF_SAMPLE_OUTCOME in result.decisions[1].reason_codes
    assert [version.status for version in ExperimentRepository(Database(database_path)).configuration_version_history()] == [
        PromotionStatus.BASELINE,
        PromotionStatus.PROMOTED,
    ]


def test_aapl_configs_share_a_dedicated_database_and_strict_chronological_plan() -> None:
    experiment = yaml.safe_load((PROJECT_ROOT / "config/aapl_experiment.yaml").read_text(encoding="utf-8"))
    improvement = yaml.safe_load((PROJECT_ROOT / "config/aapl_improvement.yaml").read_text(encoding="utf-8"))

    assert experiment["experiment"]["asset"] == "AAPL"
    assert experiment["database_path"] == improvement["database_path"] == "data/aapl_research.db"
    assert improvement["learning"]["walk_forward"] == {
        "train_size": 504,
        "test_size": 126,
        "step_size": 126,
        "min_windows": 5,
    }
    profiles = improvement["learning"]["search"]["profiles"]
    assert len(profiles) == 5
    assert [
        profile["changes"]["strategy_weights"]["moving_average"]
        for profile in profiles
    ] == [0.05, 0.15, 0.25, 0.35, 0.50]
    assert all("execution_controls" in profile["changes"] for profile in profiles)
