"""Reusable causal simulation adapter used by V0.6 validation analyses."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import pandas as pd

from finagent.agents.factory import build_agent_decision_system
from finagent.backtesting.costs import TransactionCostModel
from finagent.backtesting.engine import BacktestEngine, BacktestResult, ExecutionControlConfig
from finagent.evaluation.benchmark import buy_and_hold_benchmark
from finagent.evaluation.metrics import calculate_metrics
from finagent.features.pipeline import FeaturePipeline
from finagent.regime.detector import RuleBasedRegimeDetector, RuleBasedRegimeDetectorConfig
from finagent.strategies.factory import create_strategy
from finagent.validation.models import MetricSnapshot


@dataclass(frozen=True)
class SimulationResult:
    asset: str
    market_data: pd.DataFrame
    featured_data: pd.DataFrame
    backtest: BacktestResult
    metrics: dict[str, Any]
    benchmark_curve: pd.DataFrame
    benchmark_metrics: dict[str, Any]
    regime_history: pd.DataFrame
    costs: TransactionCostModel

    @property
    def metric_snapshot(self) -> MetricSnapshot:
        return MetricSnapshot.from_metrics(self.metrics, _transaction_cost(self.backtest.trades))

    @property
    def benchmark_snapshot(self) -> MetricSnapshot:
        return MetricSnapshot.from_metrics(self.benchmark_metrics, 0.0)


def simulate_configuration(market_data: pd.DataFrame, configuration: dict[str, Any], asset: str | None = None) -> SimulationResult:
    """Run existing V0.1–V0.3 causal components with identical capital and cost assumptions."""
    if market_data.empty:
        raise ValueError("Cannot simulate an empty validation dataset")
    backtest_configuration = configuration.get("backtest", {})
    annualization = int(backtest_configuration.get("annualization_factor", 252))
    featured_data = FeaturePipeline(annualization).generate(market_data, configuration.get("features", {}))
    regime_configuration = configuration.get("regime", {})
    detector = RuleBasedRegimeDetector(RuleBasedRegimeDetectorConfig.from_mapping(regime_configuration, annualization))
    agents_enabled = bool(configuration.get("agents", {}).get("enabled", False))
    if agents_enabled and not regime_configuration.get("enabled", True):
        raise ValueError("Agent-mode evaluation requires regime.enabled")
    strategy_configuration = configuration["strategy"]
    costs = TransactionCostModel(**backtest_configuration.get("transaction_costs", {}))
    starting_capital = float(configuration["experiment"]["starting_capital"])
    backtest = BacktestEngine(
        strategy=create_strategy(strategy_configuration["name"], strategy_configuration.get("parameters", {})),
        starting_capital=starting_capital,
        transaction_costs=costs,
        position_fraction=float(backtest_configuration.get("position_fraction", 1.0)),
        agent_decision_system=build_agent_decision_system(configuration, detector) if agents_enabled else None,
        execution_controls=ExecutionControlConfig.from_mapping(backtest_configuration.get("execution_controls", {})),
    ).run(featured_data)
    metrics = calculate_metrics(backtest.equity_curve, backtest.trades, annualization, initial_equity=starting_capital)
    benchmark_curve = buy_and_hold_benchmark(market_data, starting_capital, costs)
    benchmark_metrics = calculate_metrics(
        benchmark_curve.rename(columns={"benchmark_equity": "equity"}), None, annualization, initial_equity=starting_capital
    )
    regime_history = (
        detector.detect_history(featured_data)
        if regime_configuration.get("enabled", True)
        else pd.DataFrame(columns=["timestamp", "regime", "confidence"])
    )
    return SimulationResult(
        asset=asset or str(configuration["experiment"].get("asset", "UNKNOWN")),
        market_data=market_data,
        featured_data=featured_data,
        backtest=backtest,
        metrics=metrics,
        benchmark_curve=benchmark_curve,
        benchmark_metrics=benchmark_metrics,
        regime_history=regime_history,
        costs=costs,
    )


def configuration_for_asset(configuration: dict[str, Any], asset: str, dataset: str) -> dict[str, Any]:
    """Return an isolated configuration snapshot that differs only in declared asset/dataset identity."""
    result = copy.deepcopy(configuration)
    result.setdefault("experiment", {})["asset"] = asset
    result["experiment"]["dataset"] = dataset
    return result


def test_window_snapshot(result: BacktestResult, train_observations: int, configuration: dict[str, Any]) -> MetricSnapshot:
    """Calculate metrics strictly from a test segment, carrying only the causal portfolio state from train."""
    if train_observations < 1 or train_observations >= len(result.equity_curve):
        raise ValueError("Walk-forward train segment must leave a held-out test observation")
    test_curve = result.equity_curve.iloc[train_observations:].copy()
    initial_equity = float(result.equity_curve.iloc[train_observations - 1]["equity"])
    first_test_timestamp = pd.Timestamp(test_curve.iloc[0]["timestamp"])
    trades = result.trades
    test_trades = trades.loc[pd.to_datetime(trades["timestamp"], utc=True) >= first_test_timestamp] if not trades.empty else trades
    metrics = calculate_metrics(
        test_curve,
        test_trades,
        int(configuration.get("backtest", {}).get("annualization_factor", 252)),
        initial_equity=initial_equity,
    )
    return MetricSnapshot.from_metrics(metrics, _transaction_cost(test_trades))


def _transaction_cost(trades: pd.DataFrame) -> float:
    return float(trades["transaction_cost"].astype(float).sum()) if not trades.empty else 0.0
