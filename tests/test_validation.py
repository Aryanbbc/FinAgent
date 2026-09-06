from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from finagent.data.loader import CSVDataLoader
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.learning.models import PromotionRobustnessEvidence
from finagent.learning.models import ValidationMetrics, WalkForwardEvaluation, WalkForwardWindow
from finagent.learning.promotion_gate import PromotionGate, PromotionGateConfig
from finagent.learning.walk_forward import ChronologicalSplit, WalkForwardConfig, chronological_splits
from finagent.runner import load_configuration, run_experiment
from finagent.validation.analysis import (
    BootstrapConfig,
    RobustnessScoreConfig,
    RobustnessScorer,
    SensitivityAnalyzer,
    ablation_study,
    benchmark_suite,
    bootstrap_confidence_intervals,
)
from finagent.validation.engine import simulate_configuration
from finagent.validation.leakage import LeakageValidationError, run_leakage_checks, validate_preprocessing_scope, validate_splits
from finagent.validation.models import AssetValidationResult, MetricSnapshot, SensitivityPoint
from finagent.validation.report import ResearchReportExporter
from finagent.validation.workflow import run_research_validation


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source_configuration(tmp_path: Path) -> Path:
    path = tmp_path / "source.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "experiment": {
                    "asset": "PRIMARY",
                    "dataset": str(PROJECT_ROOT / "data/raw/example_ohlcv.csv"),
                    "starting_capital": 10000.0,
                    "random_seed": 7,
                },
                "database_path": str(tmp_path / "experiments.db"),
                "strategy": {"name": "momentum", "parameters": {"lookback_window": 5, "entry_threshold": 0.0, "exit_threshold": -0.02}},
                "agents": {"enabled": False},
                "critic": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    return path


def _validation_configuration(tmp_path: Path, source: Path) -> Path:
    path = tmp_path / "validation.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "source_experiment_config": str(source),
                "validation": {
                    "enabled": True,
                    "assets": [
                        {"asset": "PRIMARY", "dataset": str(PROJECT_ROOT / "data/raw/example_ohlcv.csv")},
                        {"asset": "SECONDARY", "dataset": str(PROJECT_ROOT / "data/raw/example_ohlcv_secondary.csv")},
                    ],
                    "asset_pass": {"maximum_drawdown": 0.20, "minimum_trades": 0},
                    "walk_forward": {
                        "window_mode": "rolling",
                        "train_size": 15,
                        "test_size": 10,
                        "step_size": 10,
                        "minimum_train_length": 15,
                        "minimum_test_length": 10,
                        "non_overlapping_test_windows": True,
                    },
                    "leakage_checks": {"enabled": True},
                    "sensitivity": {"enabled": True, "parameters": {"momentum_window": [4, 5]}},
                    "bootstrap": {"enabled": True, "samples": 20, "confidence_level": 0.95, "random_seed": 3},
                    "robustness": {"maximum_drawdown": 0.20},
                    "ablation": {"enabled": True},
                    "benchmarks": {"enabled": True},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_multi_asset_validation_aggregates_persists_manifest_and_exports_report(tmp_path) -> None:
    source = _source_configuration(tmp_path)
    result = run_research_validation(_validation_configuration(tmp_path, source), PROJECT_ROOT)
    assert result is not None
    assert len(result.asset_results) == 2
    assert len(result.windows) == 4
    assert len(result.sensitivity) == 2
    assert len(result.ablations) == 5
    assert len(result.benchmarks) == 10
    assert result.leakage.passed
    assert result.manifest.evaluation_mode == "multi_asset"

    repository = ExperimentRepository(Database(tmp_path / "experiments.db"))
    assert repository.get_research_validation(result.validation_id) == result
    assert repository.get_manifest(result.experiment_id) is not None
    report_path = ResearchReportExporter(repository).export(result.experiment_id, tmp_path / "report.md")
    assert "Multi-Asset Summary" in report_path.read_text(encoding="utf-8")


def test_rolling_and_expanding_walk_forward_splits_are_deterministic() -> None:
    rolling = chronological_splits(40, WalkForwardConfig(15, 10, 10, window_mode="rolling"))
    expanding = chronological_splits(40, WalkForwardConfig(15, 10, 10, window_mode="expanding"))
    assert [(item.train_start, item.train_end, item.test_start, item.test_end) for item in rolling] == [(0, 15, 15, 25), (10, 25, 25, 35)]
    assert [(item.train_start, item.train_end, item.test_start, item.test_end) for item in expanding] == [(0, 15, 15, 25), (0, 25, 25, 35)]
    with pytest.raises(ValueError, match="step_size"):
        WalkForwardConfig(15, 10, 5, non_overlapping_test_windows=True)


def test_leakage_checks_detect_duplicates_overlap_feature_lookahead_and_preprocessing_scope() -> None:
    market_data = CSVDataLoader().load(PROJECT_ROOT / "data/raw/example_ohlcv.csv")
    configuration = {"simple_return": True, "rolling_volatility": {"window": 3}}
    from finagent.features.pipeline import FeaturePipeline

    featured = FeaturePipeline(252).generate(market_data, configuration)
    splits = chronological_splits(len(market_data), WalkForwardConfig(15, 10, 10))
    assert run_leakage_checks(market_data, featured, configuration, 252, splits).passed
    future_leaky = featured.copy()
    future_leaky.loc[3, "simple_return"] = 999.0
    with pytest.raises(LeakageValidationError, match="Feature look-ahead"):
        run_leakage_checks(market_data, future_leaky, configuration, 252, splits)
    duplicated = market_data.copy()
    duplicated.loc[1, "timestamp"] = duplicated.loc[0, "timestamp"]
    with pytest.raises(LeakageValidationError, match="Duplicated timestamps"):
        validate_splits(duplicated, splits)
    with pytest.raises(LeakageValidationError, match="Overlapping out-of-sample"):
        validate_splits(market_data, (ChronologicalSplit(0, 15, 15, 25), ChronologicalSplit(10, 20, 20, 30)))
    with pytest.raises(LeakageValidationError, match="Preprocessing"):
        validate_preprocessing_scope(15, 15)


def test_bootstrap_is_reproducible_and_clearly_estimated() -> None:
    curve = pd.DataFrame({"equity": [100, 101, 100, 103, 102, 105, 106]})
    configuration = BootstrapConfig(samples=100, confidence_level=0.90, random_seed=12)
    first = bootstrap_confidence_intervals(curve, 252, configuration)
    second = bootstrap_confidence_intervals(curve, 252, configuration)
    assert first == second
    assert first[0].estimated is True
    assert first[0].lower is not None and first[0].upper is not None


def test_sensitivity_robustness_ablation_and_benchmark_suite_share_simulation_assumptions(tmp_path) -> None:
    source = _source_configuration(tmp_path)
    configuration = load_configuration(source, PROJECT_ROOT)
    data = CSVDataLoader().load(PROJECT_ROOT / "data/raw/example_ohlcv.csv")
    sensitivity = SensitivityAnalyzer().analyze([("PRIMARY", data)], configuration, {"momentum_window": [4, 5, 6]})
    assert [item.value for item in sensitivity] == [4, 5, 6]
    assert all(0 <= item.stability_score <= 1 for item in sensitivity)
    simulation = simulate_configuration(data, configuration, "PRIMARY")
    suite = benchmark_suite((simulation,), configuration)
    finagent = next(item for item in suite if item.benchmark == "finagent")
    momentum = next(item for item in suite if item.benchmark == "momentum")
    assert finagent.metrics == momentum.metrics
    scorer = RobustnessScorer(RobustnessScoreConfig())
    asset = AssetValidationResult("PRIMARY", "data", "2024-01-01", "2024-02-01", finagent.metrics, simulation.benchmark_snapshot, True, {}, 0)
    score = scorer.calculate((asset,), (finagent.metrics,), sensitivity)
    assert 0 <= score.score <= 1
    assert set(score.components) == set(score.weights)
    assert len(ablation_study([("PRIMARY", data)], configuration, scorer)) == 5


def test_optional_v06_promotion_guardrails_leave_v05_defaults_unchanged() -> None:
    parent = ValidationMetrics(0.01, 0.5, -0.05, 0.5, 1.0, 3)
    candidate = ValidationMetrics(0.03, 0.9, -0.04, 0.4, 1.0, 3)
    window = WalkForwardWindow(
        1, "2024-01-01", "2024-01-05", "2024-01-06", "2024-01-10", 5, 5, parent, candidate
    )
    evaluation = WalkForwardEvaluation("CAND-0001", "FinAgent-A0001", (window,), parent, candidate)
    assert PromotionGate(PromotionGateConfig(minimum_window_pass_rate=1.0)).decide(evaluation).status.value == "PROMOTED"
    guarded = PromotionGate(PromotionGateConfig(minimum_window_pass_rate=1.0, minimum_robustness_score=0.8, minimum_assets=2))
    decision = guarded.decide(evaluation, PromotionRobustnessEvidence(robustness_score=0.5, asset_count=1))
    assert decision.status.value == "REJECTED"
    assert {code.value for code in decision.reason_codes} >= {"ROBUSTNESS_SCORE_TOO_LOW", "INSUFFICIENT_ASSET_COVERAGE"}


def test_single_asset_runner_remains_compatible_and_persists_a_manifest(tmp_path) -> None:
    source = _source_configuration(tmp_path)
    experiment_id, result = run_experiment(source, PROJECT_ROOT)
    assert result["manifest"]["enabled"] is True
    repository = ExperimentRepository(Database(tmp_path / "experiments.db"))
    manifest = repository.get_manifest(experiment_id)
    assert manifest is not None
    assert manifest.evaluation_mode == "single_asset"
