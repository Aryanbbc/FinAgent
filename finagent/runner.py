"""Configuration-driven orchestration for a complete V0.1–V0.6 experiment."""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from finagent.agents.decision_system import AgentDecisionSystem
from finagent.agents.factory import build_agent_decision_system
from finagent.backtesting.costs import TransactionCostModel
from finagent.backtesting.engine import BacktestEngine
from finagent.critique.critic_agent import CriticAgent, CriticAgentConfig
from finagent.critique.models import CriticAgentInput, TradeStatistics, TransactionCostAssumptions
from finagent.configuration import validate_research_configuration
from finagent.data.loader import CSVDataLoader
from finagent.data.registry import DatasetRegistry
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.evaluation.benchmark import buy_and_hold_benchmark
from finagent.evaluation.metrics import calculate_metrics
from finagent.features.pipeline import FeaturePipeline
from finagent.memory.experiment_memory import ExperimentMemory
from finagent.regime.detector import RuleBasedRegimeDetector, RuleBasedRegimeDetectorConfig
from finagent.strategies.factory import create_strategy
from finagent.validation.analysis import build_manifest
from finagent.validation.models import AssetValidationResult, MetricSnapshot


def _deep_merge(base: dict[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def load_configuration(config_path: str | Path, project_root: str | Path) -> dict[str, Any]:
    """Load an experiment YAML file over the repository's V0.6 defaults."""
    root = Path(project_root)
    requested_path = Path(config_path)
    if not requested_path.is_absolute():
        requested_path = root / requested_path
    default_path = root / "config" / "default.yaml"
    with default_path.open(encoding="utf-8") as handle:
        default_config = yaml.safe_load(handle) or {}
    with requested_path.open(encoding="utf-8") as handle:
        experiment_config = yaml.safe_load(handle) or {}
    merged = _deep_merge(default_config, experiment_config)
    validate_research_configuration(merged)
    return merged


def _curve_records(curve: pd.DataFrame, value_column: str) -> list[dict[str, object]]:
    return [
        {"timestamp": pd.Timestamp(row["timestamp"]).isoformat(), value_column: float(row[value_column])}
        for _, row in curve.iterrows()
    ]


def _regime_summary(regime_history: pd.DataFrame) -> dict[str, Any]:
    """Build JSON-safe experiment-result metadata from persisted regime history."""
    latest_row = regime_history.iloc[-1]
    latest: dict[str, Any] = {
        "timestamp": str(latest_row["timestamp"]),
        "regime": str(latest_row["regime"]),
        "confidence": float(latest_row["confidence"]),
        "features": {},
    }
    for key in ("rolling_return", "rolling_volatility", "moving_average_slope", "momentum", "drawdown"):
        value = latest_row[key]
        latest["features"][key] = None if pd.isna(value) else float(value)
    distribution = {str(regime): int(count) for regime, count in regime_history["regime"].value_counts().items()}
    return {"enabled": True, "latest": latest, "distribution": distribution, "observations": int(len(regime_history))}


def _agent_summary(agent_decisions: pd.DataFrame, enabled: bool) -> dict[str, Any]:
    """Build the nested result representation of the latest persisted agent flow."""
    if not enabled or agent_decisions.empty:
        return {"enabled": enabled, "observations": 0, "latest": None}
    latest = agent_decisions.iloc[-1]
    return {
        "enabled": True,
        "observations": int(len(agent_decisions)),
        "latest": {
            "timestamp": str(latest["timestamp"]),
            "technical": {
                "trend": latest["technical_trend"],
                "momentum": latest["technical_momentum"],
                "volatility": latest["technical_volatility"],
                "rsi": latest["technical_rsi"],
                "signal_strength": float(latest["technical_signal_strength"]),
                "confidence": float(latest["technical_confidence"]),
            },
            "regime": {"regime": latest["regime"], "confidence": float(latest["regime_confidence"])},
            "proposal": {
                "selected_strategy": latest["selected_strategy"],
                "action": latest["action"],
                "confidence": float(latest["proposal_confidence"]),
                "requested_position_size": float(latest["requested_position_size"]),
                "reason_codes": list(latest["strategy_reason_codes"]),
            },
            "risk": {
                "approved": bool(latest["risk_approved"]),
                "adjusted_position_size": float(latest["adjusted_position_size"]),
                "reason_code": latest["risk_reason_code"],
            },
            "execution_action": latest["execution_action"],
        },
    }


def _trade_statistics(trades: pd.DataFrame) -> TradeStatistics:
    """Calculate typed cost-aware trade statistics for the V0.4 critic input."""
    if trades.empty:
        return TradeStatistics(0, 0, 0.0, 0.0, None)
    total_notional = float((trades["price"].astype(float) * trades["quantity"].astype(float)).sum())
    total_cost = float(trades["transaction_cost"].astype(float).sum())
    return TradeStatistics(
        number_of_executions=int(len(trades)),
        closed_trades=int((trades["side"] == "SELL").sum()),
        total_notional=total_notional,
        total_transaction_cost=total_cost,
        transaction_cost_ratio=(total_cost / total_notional) if total_notional else None,
    )


def run_experiment(
    config_path: str | Path,
    project_root: str | Path,
    logger: logging.Logger | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run, evaluate, persist, critique, manifest, and return a V0.1–V0.6 historical experiment."""
    root = Path(project_root)
    configuration = load_configuration(config_path, root)
    experiment_config = configuration["experiment"]
    backtest_config = configuration.get("backtest", {})
    asset = str(experiment_config.get("asset") or "")
    database_value = configuration.get("database_path", "data/finagent.db")
    database_path = Path(database_value)
    if not database_path.is_absolute():
        database_path = root / database_path
    dataset_provenance: dict[str, Any] | None = None
    dataset_id = experiment_config.get("dataset_id")
    if dataset_id:
        dataset_record = DatasetRegistry(Database(database_path)).latest(str(dataset_id))
        dataset_value = str(dataset_id)
        dataset_path = Path(dataset_record.cache_path)
        asset = str(experiment_config.get("asset") or dataset_record.symbol)
        dataset_provenance = {
            "dataset_id": dataset_record.dataset_id,
            "dataset_version": dataset_record.version_id,
            "provider": dataset_record.provider,
            "symbol": dataset_record.symbol,
            "fetch_date": dataset_record.last_refreshed_at,
            "checksum": dataset_record.checksum,
            "date_range": {"start": dataset_record.start_date, "end": dataset_record.end_date},
            "adjustment_mode": dataset_record.metadata.adjustment_mode,
        }
    else:
        if not asset:
            raise ValueError("experiment.asset is required when experiment.dataset_id is not set")
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

    annualization_factor = int(backtest_config.get("annualization_factor", 252))
    regime_config = configuration.get("regime", {})
    regime_detector = RuleBasedRegimeDetector(RuleBasedRegimeDetectorConfig.from_mapping(regime_config, annualization_factor))
    regime_history: pd.DataFrame | None = None
    regime_results: dict[str, Any] = {"enabled": False, "latest": None, "distribution": {}, "observations": 0}
    if regime_config.get("enabled", True):
        regime_history = regime_detector.detect_history(featured_data)
        regime_results = _regime_summary(regime_history)
        if logger:
            logger.info(
                "event=REGIMES_DETECTED observations=%s latest_regime=%s",
                len(regime_history),
                regime_results["latest"]["regime"],
            )

    strategy_config = configuration["strategy"]
    strategy = create_strategy(strategy_config["name"], strategy_config.get("parameters"))
    costs = TransactionCostModel(**backtest_config.get("transaction_costs", {}))
    starting_capital = float(experiment_config["starting_capital"])
    agents_enabled = bool(configuration.get("agents", {}).get("enabled", False))
    if agents_enabled and not regime_config.get("enabled", True):
        raise ValueError("V0.3 agent mode requires regime.enabled to remain true")
    agent_decision_system = build_agent_decision_system(configuration, regime_detector, logger) if agents_enabled else None
    result = BacktestEngine(
        strategy=strategy,
        starting_capital=starting_capital,
        transaction_costs=costs,
        position_fraction=float(backtest_config.get("position_fraction", 1.0)),
        agent_decision_system=agent_decision_system,
    ).run(featured_data)
    if logger and agents_enabled:
        logger.info("event=AGENT_DECISIONS_GENERATED observations=%s", len(result.agent_decisions))
    if logger:
        logger.info("event=EXPERIMENT_COMPLETED trades=%s", len(result.trades))

    metrics = calculate_metrics(result.equity_curve, result.trades, annualization_factor, initial_equity=starting_capital)
    benchmark_curve = buy_and_hold_benchmark(market_data, starting_capital, costs)
    benchmark_metrics = calculate_metrics(
        benchmark_curve.rename(columns={"benchmark_equity": "equity"}), None, annualization_factor, initial_equity=starting_capital
    )
    agent_results = _agent_summary(result.agent_decisions, agents_enabled)
    critic_enabled = bool(configuration.get("critic", {}).get("enabled", False))

    results: dict[str, Any] = {
        "metrics": metrics,
        "benchmark_metrics": benchmark_metrics,
        "regime": regime_results,
        "agents": agent_results,
        "critique": {"enabled": False, "output": None},
        "memory": {"enabled": False, "record": None},
        "equity_curve": _curve_records(result.equity_curve, "equity"),
        "benchmark_curve": _curve_records(benchmark_curve, "benchmark_equity"),
        "final_portfolio": {
            "cash": float(result.final_portfolio.cash or 0.0),
            "holdings": result.final_portfolio.holdings,
            "entry_price": result.final_portfolio.entry_price,
            "realized_pnl": result.final_portfolio.realized_pnl,
            "unrealized_pnl": result.final_portfolio.unrealized_pnl,
        },
        "dataset_provenance": dataset_provenance,
    }
    repository = ExperimentRepository(Database(database_path))
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
        regime_observations=regime_history,
        agent_decisions=result.agent_decisions,
    )
    manifest = build_manifest(
        experiment_id,
        configuration,
        [
            AssetValidationResult(
                asset=asset,
                dataset=str(dataset_path),
                start_date=market_data["timestamp"].iloc[0].date().isoformat(),
                end_date=market_data["timestamp"].iloc[-1].date().isoformat(),
                metrics=MetricSnapshot.from_metrics(metrics, _trade_statistics(result.trades).total_transaction_cost),
                benchmark_metrics=MetricSnapshot.from_metrics(benchmark_metrics),
                passed=True,
                regime_distribution=regime_results.get("distribution", {}),
                agent_observations=len(result.agent_decisions),
            )
        ],
        "single_asset",
        configuration.get("validation", {}).get("walk_forward", {}),
        root,
        {asset: dataset_provenance} if dataset_provenance else None,
    )
    repository.save_manifest(manifest)
    results["manifest"] = {
        "enabled": True,
        "evaluation_mode": manifest.evaluation_mode,
        "code_version": manifest.code_version,
        "dataset_count": len(manifest.datasets),
    }
    repository.update_experiment_results(experiment_id, results)
    if critic_enabled:
        critic = CriticAgent(CriticAgentConfig(**dict(configuration.get("critic", {}).get("thresholds", {}))), logger=logger)
        critique = critic.run(
            CriticAgentInput(
                experiment_id=experiment_id,
                strategy=strategy.name,
                strategy_parameters=dict(strategy_config.get("parameters", {})),
                metrics=metrics,
                benchmark_metrics=benchmark_metrics,
                regime_history=regime_history if regime_history is not None else pd.DataFrame(columns=["timestamp", "regime"]),
                agent_decision_history=result.agent_decisions,
                trade_statistics=_trade_statistics(result.trades),
                transaction_costs=TransactionCostAssumptions(costs.percentage_fee, costs.fixed_fee),
            )
        )
        memory = ExperimentMemory(repository)
        memory_record = memory.build_record(
            experiment_id=experiment_id,
            agent_version="0.3" if agents_enabled else "baseline",
            strategy=strategy.name,
            strategy_parameters=dict(strategy_config.get("parameters", {})),
            metrics=metrics,
            transaction_costs={"percentage_fee": costs.percentage_fee, "fixed_fee": costs.fixed_fee},
            critique=critique,
            regime_history=regime_history if regime_history is not None else pd.DataFrame(columns=["timestamp", "regime"]),
            equity_curve=result.equity_curve,
            agent_decisions=result.agent_decisions,
        )
        repository.save_critique(critique)
        memory.store(memory_record)
        results["critique"] = {"enabled": True, "output": critique.to_dict()}
        results["memory"] = {
            "enabled": True,
            "record": {
                "agent_version": memory_record.agent_version,
                "decision_summary": memory_record.decision_summary.to_dict(),
                "regime_performance": [item.to_dict() for item in memory_record.regime_performance],
            },
        }
        repository.update_experiment_results(experiment_id, results)
        if logger:
            logger.info("event=CRITIQUE_GENERATED experiment_id=%s confidence=%.2f", experiment_id, critique.confidence)
    if logger:
        logger.info("event=EXPERIMENT_SAVED experiment_id=%s", experiment_id)
    return experiment_id, results
