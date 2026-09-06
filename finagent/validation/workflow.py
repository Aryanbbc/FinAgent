"""Explicit V0.6 multi-asset research-validation workflow."""

from __future__ import annotations

import copy
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from finagent.data.loader import CSVDataLoader
from finagent.data.registry import DatasetRegistry
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.learning.walk_forward import WalkForwardConfig, chronological_splits
from finagent.runner import load_configuration, run_experiment
from finagent.validation.analysis import (
    BootstrapConfig,
    RobustnessScoreConfig,
    RobustnessScorer,
    SensitivityAnalyzer,
    ablation_study,
    aggregate_metrics,
    benchmark_suite,
    bootstrap_confidence_intervals,
    build_manifest,
)
from finagent.validation.engine import configuration_for_asset, simulate_configuration, test_window_snapshot
from finagent.validation.leakage import run_leakage_checks, validate_preprocessing_scope
from finagent.validation.models import (
    AssetValidationResult,
    AssetSpec,
    LeakageCheckResult,
    ResearchValidationResult,
    ResearchWindowResult,
)


def run_research_validation(
    config_path: str | Path,
    project_root: str | Path,
    logger: logging.Logger | None = None,
) -> ResearchValidationResult | None:
    """Run one user-requested V0.6 validation suite and persist it against a baseline experiment."""
    root = Path(project_root)
    requested = Path(config_path)
    if not requested.is_absolute():
        requested = root / requested
    with requested.open(encoding="utf-8") as handle:
        validation_file = yaml.safe_load(handle) or {}
    validation_configuration = dict(validation_file.get("validation", {}))
    if not bool(validation_configuration.get("enabled", False)):
        if logger:
            logger.info("event=RESEARCH_VALIDATION_DISABLED config=%s", requested)
        return None

    source = validation_file.get("source_experiment_config", "config/experiments.yaml")
    source_configuration = load_configuration(source, root)
    # The standard experiment is retained unchanged and becomes the report/export anchor.
    experiment_id, _ = run_experiment(source, root, logger)
    database_value = source_configuration.get("database_path", "data/finagent.db")
    database_path = Path(database_value)
    if not database_path.is_absolute():
        database_path = root / database_path
    repository = ExperimentRepository(Database(database_path))

    asset_specs = _asset_specs(validation_configuration, source_configuration, root)
    simulations = []
    asset_results = []
    windows = []
    all_leakage_checks: list[str] = []
    walk_forward_raw = dict(validation_configuration.get("walk_forward", {}))
    walk_forward = WalkForwardConfig.from_mapping(walk_forward_raw)
    for spec in asset_specs:
        dataset_path = Path(spec.dataset)
        if not dataset_path.is_absolute():
            dataset_path = root / dataset_path
        market_data = CSVDataLoader().load(dataset_path)
        asset_configuration = configuration_for_asset(source_configuration, spec.asset, spec.dataset)
        simulation = simulate_configuration(market_data, asset_configuration, spec.asset)
        simulations.append(simulation)
        splits = chronological_splits(len(market_data), walk_forward)
        if bool(validation_configuration.get("leakage_checks", {}).get("enabled", True)):
            leakage = run_leakage_checks(
                market_data,
                simulation.featured_data,
                asset_configuration.get("features", {}),
                int(asset_configuration.get("backtest", {}).get("annualization_factor", 252)),
                splits,
                allow_overlapping_tests=not walk_forward.non_overlapping_test_windows,
            )
            all_leakage_checks.extend(leakage.checks)
        for index, split in enumerate(splits, start=1):
            validate_preprocessing_scope(split.train_end - 1, split.test_start)
            available_data = market_data.iloc[split.train_start : split.test_end].reset_index(drop=True)
            window_simulation = simulate_configuration(available_data, asset_configuration, spec.asset)
            train_data = market_data.iloc[split.train_start : split.train_end]
            test_data = market_data.iloc[split.test_start : split.test_end]
            windows.append(
                ResearchWindowResult(
                    asset=spec.asset,
                    window_index=index,
                    window_mode=walk_forward.window_mode,
                    train_start=pd.Timestamp(train_data["timestamp"].iloc[0]).isoformat(),
                    train_end=pd.Timestamp(train_data["timestamp"].iloc[-1]).isoformat(),
                    test_start=pd.Timestamp(test_data["timestamp"].iloc[0]).isoformat(),
                    test_end=pd.Timestamp(test_data["timestamp"].iloc[-1]).isoformat(),
                    train_observations=len(train_data),
                    test_observations=len(test_data),
                    metrics=test_window_snapshot(window_simulation.backtest, len(train_data), asset_configuration),
                )
            )
        maximum_drawdown = float(validation_configuration.get("asset_pass", {}).get("maximum_drawdown", 0.30))
        minimum_trades = int(validation_configuration.get("asset_pass", {}).get("minimum_trades", 0))
        minimum_sharpe = validation_configuration.get("asset_pass", {}).get("minimum_sharpe")
        snapshot = simulation.metric_snapshot
        asset_results.append(
            AssetValidationResult(
                asset=spec.asset,
                dataset=spec.dataset,
                start_date=market_data["timestamp"].iloc[0].date().isoformat(),
                end_date=market_data["timestamp"].iloc[-1].date().isoformat(),
                metrics=snapshot,
                benchmark_metrics=simulation.benchmark_snapshot,
                passed=(
                    snapshot.sharpe_ratio is not None
                    and snapshot.maximum_drawdown is not None
                    and snapshot.maximum_drawdown >= -maximum_drawdown
                    and snapshot.number_of_trades >= minimum_trades
                    and (
                        minimum_sharpe is None
                        or (snapshot.sharpe_ratio is not None and snapshot.sharpe_ratio >= float(minimum_sharpe))
                    )
                ),
                regime_distribution=(
                    {str(key): int(value) for key, value in simulation.regime_history["regime"].value_counts().items()}
                    if not simulation.regime_history.empty
                    else {}
                ),
                agent_observations=len(simulation.backtest.agent_decisions),
            )
        )
        if logger:
            logger.info("event=VALIDATION_ASSET_EVALUATED asset=%s rows=%s windows=%s", spec.asset, len(market_data), len(splits))

    simulations_by_asset = [(item.asset, item.market_data) for item in simulations]
    sensitivity = ()
    sensitivity_raw = dict(validation_configuration.get("sensitivity", {}))
    if bool(sensitivity_raw.get("enabled", False)):
        sensitivity = SensitivityAnalyzer().analyze(
            simulations_by_asset, source_configuration, dict(sensitivity_raw.get("parameters", {}))
        )
    scorer = RobustnessScorer(RobustnessScoreConfig.from_mapping(dict(validation_configuration.get("robustness", {}))))
    robustness = scorer.calculate(asset_results, [item.metrics for item in windows], sensitivity)
    intervals = ()
    bootstrap_raw = dict(validation_configuration.get("bootstrap", {}))
    if bool(bootstrap_raw.get("enabled", False)):
        intervals = bootstrap_confidence_intervals(
            _pooled_equity_curve(simulations),
            int(source_configuration.get("backtest", {}).get("annualization_factor", 252)),
            BootstrapConfig.from_mapping(bootstrap_raw),
        )
    ablations = ()
    if bool(validation_configuration.get("ablation", {}).get("enabled", False)):
        ablations = ablation_study(simulations_by_asset, source_configuration, scorer)
    benchmarks = ()
    if bool(validation_configuration.get("benchmarks", {}).get("enabled", False)):
        benchmarks = benchmark_suite(simulations, source_configuration)
    manifest = build_manifest(
        experiment_id,
        source_configuration,
        asset_results,
        "multi_asset" if len(asset_results) > 1 else "single_asset_validation",
        walk_forward_raw,
        root,
    )
    if bootstrap_raw:
        manifest = replace(manifest, random_seeds={**manifest.random_seeds, "bootstrap": int(bootstrap_raw.get("random_seed", 42))})
    leakage = LeakageCheckResult(
        passed=True,
        checks=tuple(dict.fromkeys(all_leakage_checks)) or ("validation_not_configured",),
        errors=(),
    )
    validation = ResearchValidationResult(
        validation_id=repository.next_validation_id(),
        experiment_id=experiment_id,
        asset_results=tuple(asset_results),
        aggregate_metrics=aggregate_metrics([item.metrics for item in asset_results]),
        windows=tuple(windows),
        leakage=leakage,
        sensitivity=tuple(sensitivity),
        confidence_intervals=tuple(intervals),
        robustness=robustness,
        ablations=tuple(ablations),
        benchmarks=tuple(benchmarks),
        manifest=manifest,
    )
    repository.save_manifest(manifest)
    repository.save_research_validation(validation, source_configuration)
    experiment = repository.get_experiment(experiment_id)
    if experiment is not None:
        results = copy.deepcopy(experiment.results)
        results["research_validation"] = {
            "enabled": True,
            "validation_id": validation.validation_id,
            "robustness_score": validation.robustness.score,
            "asset_count": len(validation.asset_results),
            "leakage_passed": validation.leakage.passed,
        }
        repository.update_experiment_results(experiment_id, results)
    if logger:
        logger.info(
            "event=RESEARCH_VALIDATION_SAVED validation_id=%s experiment_id=%s assets=%s robustness=%.3f",
            validation.validation_id,
            experiment_id,
            len(asset_results),
            validation.robustness.score,
        )
    return validation


def _asset_specs(
    validation_configuration: dict[str, Any], source_configuration: dict[str, Any], root: Path
) -> tuple[AssetSpec, ...]:
    collection_id = validation_configuration.get("dataset_collection_id")
    if collection_id:
        database_value = source_configuration.get("database_path", "data/finagent.db")
        database_path = Path(database_value)
        if not database_path.is_absolute():
            database_path = root / database_path
        registry = DatasetRegistry(Database(database_path))
        records = registry.get_collection(str(collection_id)).members
        return tuple(
            AssetSpec(str(member["symbol"]), registry.get_version(str(member["version_id"])).cache_path)
            for member in records
        )
    raw_assets = validation_configuration.get("assets", [])
    if not raw_assets:
        experiment = source_configuration["experiment"]
        if experiment.get("dataset_id"):
            database_value = source_configuration.get("database_path", "data/finagent.db")
            database_path = Path(database_value)
            if not database_path.is_absolute():
                database_path = root / database_path
            dataset = DatasetRegistry(Database(database_path)).latest(str(experiment["dataset_id"]))
            return (AssetSpec(str(experiment.get("asset") or dataset.symbol), dataset.cache_path),)
        return (AssetSpec(str(experiment["asset"]), str(experiment["dataset"])),)
    resolved_assets = []
    for item in raw_assets:
        if item.get("dataset_id"):
            database_value = source_configuration.get("database_path", "data/finagent.db")
            database_path = Path(database_value)
            if not database_path.is_absolute():
                database_path = root / database_path
            dataset = DatasetRegistry(Database(database_path)).latest(str(item["dataset_id"]))
            resolved_assets.append(AssetSpec(str(item.get("asset") or dataset.symbol), dataset.cache_path))
        else:
            resolved_assets.append(AssetSpec(str(item["asset"]), str(item["dataset"])))
    return tuple(resolved_assets)


def _pooled_equity_curve(simulations: list[Any]) -> pd.DataFrame:
    returns = pd.concat(
        [item.backtest.equity_curve["equity"].astype(float).pct_change(fill_method=None).dropna() for item in simulations],
        ignore_index=True,
    )
    if returns.empty:
        return pd.DataFrame({"equity": [1.0]})
    return pd.DataFrame({"equity": (1 + returns).cumprod()})
