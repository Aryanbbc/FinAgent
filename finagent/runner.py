"""Configuration-driven orchestration for a complete V0.1 experiment."""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from finagent.backtesting.costs import TransactionCostModel
from finagent.backtesting.engine import BacktestEngine
from finagent.data.loader import CSVDataLoader
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.evaluation.benchmark import buy_and_hold_benchmark
from finagent.evaluation.metrics import calculate_metrics
from finagent.features.pipeline import FeaturePipeline
from finagent.strategies.factory import create_strategy


def _deep_merge(base: dict[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def load_configuration(config_path: str | Path, project_root: str | Path) -> dict[str, Any]:
    """Load an experiment YAML file over the repository's V0.1 defaults."""
    root = Path(project_root)
    requested_path = Path(config_path)
    if not requested_path.is_absolute():
        requested_path = root / requested_path
    default_path = root / "config" / "default.yaml"
    with default_path.open(encoding="utf-8") as handle:
        default_config = yaml.safe_load(handle) or {}
    with requested_path.open(encoding="utf-8") as handle:
        experiment_config = yaml.safe_load(handle) or {}
    return _deep_merge(default_config, experiment_config)


def _curve_records(curve: pd.DataFrame, value_column: str) -> list[dict[str, object]]:
    return [
        {"timestamp": pd.Timestamp(row["timestamp"]).isoformat(), value_column: float(row[value_column])}
        for _, row in curve.iterrows()
    ]


def run_experiment(
    config_path: str | Path,
    project_root: str | Path,
    logger: logging.Logger | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run, evaluate, persist, and return a V0.1 historical-data experiment."""
    root = Path(project_root)
    configuration = load_configuration(config_path, root)
    experiment_config = configuration["experiment"]
    backtest_config = configuration.get("backtest", {})
    asset = str(experiment_config["asset"])
    dataset_value = str(experiment_config["dataset"])
    dataset_path = Path(dataset_value)
    if not dataset_path.is_absolute():
        dataset_path = root / dataset_path
    random_seed = experiment_config.get("random_seed")
    if random_seed is not None:
        np.random.seed(int(random_seed))

    if logger:
        logger.info("event=EXPERIMENT_STARTED asset=%s strategy=%s", asset, configuration["strategy"]["name"])
    market_data = CSVDataLoader().load(dataset_path)
    if logger:
        logger.info("event=DATA_LOADED rows=%s dataset=%s", len(market_data), dataset_path)
    featured_data = FeaturePipeline(int(backtest_config.get("annualization_factor", 252))).generate(
        market_data, configuration.get("features", {})
    )
    if logger:
        logger.info("event=FEATURES_GENERATED columns=%s", len(featured_data.columns))

    strategy_config = configuration["strategy"]
    strategy = create_strategy(strategy_config["name"], strategy_config.get("parameters"))
    costs = TransactionCostModel(**backtest_config.get("transaction_costs", {}))
    starting_capital = float(experiment_config["starting_capital"])
    result = BacktestEngine(
        strategy=strategy,
        starting_capital=starting_capital,
        transaction_costs=costs,
        position_fraction=float(backtest_config.get("position_fraction", 1.0)),
    ).run(featured_data)
    if logger:
        logger.info("event=EXPERIMENT_COMPLETED trades=%s", len(result.trades))

    annualization_factor = int(backtest_config.get("annualization_factor", 252))
    metrics = calculate_metrics(result.equity_curve, result.trades, annualization_factor, initial_equity=starting_capital)
    benchmark_curve = buy_and_hold_benchmark(market_data, starting_capital, costs)
    benchmark_metrics = calculate_metrics(
        benchmark_curve.rename(columns={"benchmark_equity": "equity"}), None, annualization_factor, initial_equity=starting_capital
    )

    results: dict[str, Any] = {
        "metrics": metrics,
        "benchmark_metrics": benchmark_metrics,
        "equity_curve": _curve_records(result.equity_curve, "equity"),
        "benchmark_curve": _curve_records(benchmark_curve, "benchmark_equity"),
        "final_portfolio": {
            "cash": float(result.final_portfolio.cash or 0.0),
            "holdings": result.final_portfolio.holdings,
            "entry_price": result.final_portfolio.entry_price,
            "realized_pnl": result.final_portfolio.realized_pnl,
            "unrealized_pnl": result.final_portfolio.unrealized_pnl,
        },
    }
    repository = ExperimentRepository(Database(root / configuration.get("database_path", "data/finagent.db")))
    experiment_id = repository.save_experiment(
        strategy=strategy.name,
        asset=asset,
        dataset=dataset_value,
        start_date=market_data["timestamp"].iloc[0].date().isoformat(),
        end_date=market_data["timestamp"].iloc[-1].date().isoformat(),
        starting_capital=starting_capital,
        random_seed=int(random_seed) if random_seed is not None else None,
        configuration=configuration,
        results=results,
        metrics=metrics,
        trades=result.trades,
    )
    if logger:
        logger.info("event=EXPERIMENT_SAVED experiment_id=%s", experiment_id)
    return experiment_id, results
