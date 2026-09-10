"""Chronological walk-forward evaluation with no shuffled or future observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from finagent.agents.factory import build_agent_decision_system
from finagent.backtesting.costs import TransactionCostModel
from finagent.backtesting.engine import BacktestEngine, BacktestResult, ExecutionControlConfig
from finagent.features.pipeline import FeaturePipeline
from finagent.learning.models import (
    CandidateProposal,
    ValidationMetrics,
    WalkForwardEvaluation,
    WalkForwardWindow,
)
from finagent.evaluation.metrics import calculate_metrics
from finagent.regime.detector import RuleBasedRegimeDetector, RuleBasedRegimeDetectorConfig
from finagent.strategies.factory import create_strategy


@dataclass(frozen=True)
class WalkForwardConfig:
    train_size: int
    test_size: int
    step_size: int
    min_windows: int = 1
    window_mode: str = "rolling"
    minimum_train_length: int | None = None
    minimum_test_length: int | None = None
    non_overlapping_test_windows: bool = True

    def __post_init__(self) -> None:
        if self.train_size < 1 or self.test_size < 2 or self.step_size < 1 or self.min_windows < 1:
            raise ValueError("Walk-forward train_size, test_size, step_size, and min_windows must be positive")
        if self.train_size > 10_000 or self.test_size > 5_000 or self.step_size > 5_000 or self.min_windows > 100:
            raise ValueError("Walk-forward settings exceed the configured resource limits")
        if self.window_mode not in {"rolling", "expanding"}:
            raise ValueError("window_mode must be 'rolling' or 'expanding'")
        if self.minimum_train_length is not None and self.train_size < self.minimum_train_length:
            raise ValueError("train_size must satisfy minimum_train_length")
        if self.minimum_test_length is not None and self.test_size < self.minimum_test_length:
            raise ValueError("test_size must satisfy minimum_test_length")
        if self.non_overlapping_test_windows and self.step_size < self.test_size:
            raise ValueError("step_size must be at least test_size so out-of-sample test windows never overlap")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "WalkForwardConfig":
        return cls(
            train_size=int(raw.get("train_size", 60)),
            test_size=int(raw.get("test_size", 20)),
            step_size=int(raw.get("step_size", raw.get("test_size", 20))),
            min_windows=int(raw.get("min_windows", 1)),
            window_mode=str(raw.get("window_mode", "rolling")),
            minimum_train_length=(int(raw["minimum_train_length"]) if raw.get("minimum_train_length") is not None else None),
            minimum_test_length=(int(raw["minimum_test_length"]) if raw.get("minimum_test_length") is not None else None),
            non_overlapping_test_windows=bool(raw.get("non_overlapping_test_windows", True)),
        )


@dataclass(frozen=True)
class ChronologicalSplit:
    """Integer positions; test starts strictly after every observation in train."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int


def chronological_splits(observations: int, configuration: WalkForwardConfig) -> tuple[ChronologicalSplit, ...]:
    """Create rolling or expanding forward-only windows without shuffle or implicit test reuse."""
    splits: list[ChronologicalSplit] = []
    train_start, train_end = 0, configuration.train_size
    while train_end + configuration.test_size <= observations:
        test_end = train_end + configuration.test_size
        splits.append(ChronologicalSplit(train_start, train_end, train_end, test_end))
        if configuration.window_mode == "expanding":
            train_end += configuration.step_size
        else:
            train_start += configuration.step_size
            train_end = train_start + configuration.train_size
    return tuple(splits)


class WalkForwardEvaluator:
    """Evaluate parent and candidate configurations only on their held-out chronological windows."""

    def __init__(self, configuration: WalkForwardConfig) -> None:
        self.configuration = configuration

    def evaluate(
        self,
        market_data: pd.DataFrame,
        parent_configuration: Mapping[str, Any],
        candidate: CandidateProposal,
    ) -> WalkForwardEvaluation:
        if not market_data["timestamp"].is_monotonic_increasing:
            raise ValueError("Walk-forward input must be chronologically ordered")
        windows: list[WalkForwardWindow] = []
        for index, split in enumerate(chronological_splits(len(market_data), self.configuration), start=1):
            # The simulation receives training plus its following test window only.  Nothing after test_end exists here.
            available_data = market_data.iloc[split.train_start : split.test_end].reset_index(drop=True)
            parent_result = _simulate(available_data, parent_configuration)
            candidate_result = _simulate(available_data, candidate.configuration)
            parent_metrics = _test_window_metrics(parent_result, split.train_end - split.train_start, parent_configuration)
            candidate_metrics = _test_window_metrics(candidate_result, split.train_end - split.train_start, candidate.configuration)
            train_data = market_data.iloc[split.train_start : split.train_end]
            test_data = market_data.iloc[split.test_start : split.test_end]
            windows.append(
                WalkForwardWindow(
                    window_index=index,
                    train_start=pd.Timestamp(train_data["timestamp"].iloc[0]).isoformat(),
                    train_end=pd.Timestamp(train_data["timestamp"].iloc[-1]).isoformat(),
                    test_start=pd.Timestamp(test_data["timestamp"].iloc[0]).isoformat(),
                    test_end=pd.Timestamp(test_data["timestamp"].iloc[-1]).isoformat(),
                    train_observations=len(train_data),
                    test_observations=len(test_data),
                    parent_metrics=parent_metrics,
                    candidate_metrics=candidate_metrics,
                )
            )
        if not windows:
            unavailable = ValidationMetrics(None, None, None, None, 0.0, 0)
            return WalkForwardEvaluation(
                candidate_id=candidate.candidate_id,
                parent_version_id=candidate.parent_version_id,
                windows=(),
                parent_aggregate=unavailable,
                candidate_aggregate=unavailable,
            )
        return WalkForwardEvaluation(
            candidate_id=candidate.candidate_id,
            parent_version_id=candidate.parent_version_id,
            windows=tuple(windows),
            parent_aggregate=_aggregate([window.parent_metrics for window in windows]),
            candidate_aggregate=_aggregate([window.candidate_metrics for window in windows]),
        )


def _simulate(market_data: pd.DataFrame, configuration: Mapping[str, Any]) -> BacktestResult:
    """Run the existing causal V0.1–V0.3 engine against one bounded data prefix."""
    backtest = configuration.get("backtest", {})
    annualization = int(backtest.get("annualization_factor", 252))
    featured_data = FeaturePipeline(annualization).generate(market_data, configuration.get("features", {}))
    regime = configuration.get("regime", {})
    detector = RuleBasedRegimeDetector(RuleBasedRegimeDetectorConfig.from_mapping(regime, annualization))
    agents_enabled = bool(configuration.get("agents", {}).get("enabled", False))
    if agents_enabled and not regime.get("enabled", True):
        raise ValueError("Agent-mode walk-forward evaluation requires regime.enabled")
    strategy_config = configuration["strategy"]
    return BacktestEngine(
        strategy=create_strategy(strategy_config["name"], strategy_config.get("parameters", {})),
        starting_capital=float(configuration["experiment"]["starting_capital"]),
        transaction_costs=TransactionCostModel(**backtest.get("transaction_costs", {})),
        position_fraction=float(backtest.get("position_fraction", 1.0)),
        agent_decision_system=build_agent_decision_system(configuration, detector) if agents_enabled else None,
        execution_controls=ExecutionControlConfig.from_mapping(backtest.get("execution_controls", {})),
    ).run(featured_data)


def _test_window_metrics(result: BacktestResult, train_size: int, configuration: Mapping[str, Any]) -> ValidationMetrics:
    if train_size < 1 or train_size >= len(result.equity_curve):
        raise ValueError("Walk-forward train_size must leave an out-of-sample equity observation")
    test_curve = result.equity_curve.iloc[train_size:].copy()
    initial_equity = float(result.equity_curve.iloc[train_size - 1]["equity"])
    first_test_timestamp = pd.Timestamp(test_curve.iloc[0]["timestamp"])
    trades = result.trades
    test_trades = trades.loc[pd.to_datetime(trades["timestamp"], utc=True) >= first_test_timestamp] if not trades.empty else trades
    annualization = int(configuration.get("backtest", {}).get("annualization_factor", 252))
    metrics = calculate_metrics(test_curve, test_trades, annualization, initial_equity=initial_equity)
    # A full held-out window can legitimately remain flat when the deterministic
    # risk layer rejects every proposal.  ``calculate_metrics`` reports an
    # undefined Sharpe for a zero-standard-deviation return series; for
    # walk-forward aggregation, zero is the conservative comparable value (it
    # is neither rewarded nor treated as missing evidence).  This does not
    # affect general experiment metrics and leaves zero-window samples invalid.
    if metrics["sharpe_ratio"] is None and len(test_curve) > 1:
        metrics["sharpe_ratio"] = 0.0
    transaction_cost = (
        float(test_trades["transaction_cost"].astype(float).sum()) if test_trades is not None and not test_trades.empty else 0.0
    )
    return ValidationMetrics.from_mapping(metrics, transaction_cost)


def _aggregate(metrics: list[ValidationMetrics]) -> ValidationMetrics:
    """Aggregate non-overlapping held-out windows; Sharpe is the window mean, risk limits use worst drawdown."""
    if not metrics:
        raise ValueError("Cannot aggregate zero walk-forward windows")
    total_return = 1.0
    for item in metrics:
        if item.total_return is None:
            return ValidationMetrics(None, None, None, None, 0.0, 0)
        total_return *= 1 + item.total_return
    sharpes = [item.sharpe_ratio for item in metrics]
    drawdowns = [item.maximum_drawdown for item in metrics]
    turnovers = [item.turnover for item in metrics]
    return ValidationMetrics(
        total_return=total_return - 1,
        sharpe_ratio=(sum(value for value in sharpes if value is not None) / len(sharpes))
        if all(value is not None for value in sharpes)
        else None,
        maximum_drawdown=min(value for value in drawdowns if value is not None) if all(value is not None for value in drawdowns) else None,
        turnover=sum(value for value in turnovers if value is not None) if all(value is not None for value in turnovers) else None,
        transaction_cost=sum(item.transaction_cost for item in metrics),
        number_of_trades=sum(item.number_of_trades for item in metrics),
        position_changes=sum(item.position_changes for item in metrics),
        trades_per_year=(
            sum(value for value in (item.trades_per_year for item in metrics) if value is not None) / len(metrics)
            if all(item.trades_per_year is not None for item in metrics)
            else None
        ),
        average_holding_period_bars=(
            sum(
                (item.average_holding_period_bars or 0.0) * item.number_of_trades
                for item in metrics
                if item.average_holding_period_bars is not None
            )
            / sum(item.number_of_trades for item in metrics if item.average_holding_period_bars is not None)
            if any(item.average_holding_period_bars is not None and item.number_of_trades for item in metrics)
            else None
        ),
    )
