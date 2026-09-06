"""Builds reproducible V0.4 experiment-memory records and exposes retrieval helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from finagent.critique.models import ExperimentCritique
from finagent.memory.models import DecisionHistorySummary, ExperimentMemoryRecord, RegimePerformance


class ExperimentMemory:
    """Constructs compact experiment memory; persistence is delegated to its repository."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def build_record(
        self,
        *,
        experiment_id: str,
        agent_version: str,
        strategy: str,
        strategy_parameters: Mapping[str, Any],
        metrics: Mapping[str, float | int | None],
        transaction_costs: Mapping[str, float],
        critique: ExperimentCritique,
        regime_history: pd.DataFrame,
        equity_curve: pd.DataFrame,
        agent_decisions: pd.DataFrame,
    ) -> ExperimentMemoryRecord:
        """Create a typed record from the completed experiment's immutable audit trails."""
        distribution = self._regime_distribution(regime_history)
        return ExperimentMemoryRecord(
            experiment_id=experiment_id,
            agent_version=agent_version,
            strategy=strategy,
            strategy_parameters=dict(strategy_parameters),
            regime_distribution=distribution,
            regime_performance=tuple(self._regime_performance(regime_history, equity_curve)),
            metrics=dict(metrics),
            maximum_drawdown=float(metrics.get("maximum_drawdown") or 0.0),
            turnover=self._optional_float(metrics.get("turnover")),
            transaction_costs={str(key): float(value) for key, value in transaction_costs.items()},
            critique=critique,
            decision_summary=self._decision_summary(agent_decisions),
        )

    def store(self, record: ExperimentMemoryRecord) -> None:
        self.repository.save_experiment_memory(record)

    def best_performing_strategy_by_regime(self, regime: str, limit: int = 1):
        return self.repository.best_performing_strategy_by_regime(regime, limit)

    def worst_performing_strategy_by_regime(self, regime: str, limit: int = 1):
        return self.repository.worst_performing_strategy_by_regime(regime, limit)

    def experiments_with_high_drawdown(self, threshold: float):
        return self.repository.experiments_with_high_drawdown(threshold)

    def experiments_with_excessive_turnover(self, threshold: float):
        return self.repository.experiments_with_excessive_turnover(threshold)

    def recent_critiques(self, limit: int = 10):
        return self.repository.recent_critiques(limit)

    @staticmethod
    def _regime_distribution(regime_history: pd.DataFrame) -> dict[str, int]:
        if regime_history.empty:
            return {}
        return {str(regime): int(count) for regime, count in regime_history["regime"].value_counts().items()}

    @staticmethod
    def _regime_performance(regime_history: pd.DataFrame, equity_curve: pd.DataFrame) -> list[RegimePerformance]:
        if regime_history.empty or equity_curve.empty:
            return []
        regimes = regime_history.loc[:, ["timestamp", "regime"]].copy()
        equity = equity_curve.loc[:, ["timestamp", "equity"]].copy()
        regimes["timestamp"] = pd.to_datetime(regimes["timestamp"])
        equity["timestamp"] = pd.to_datetime(equity["timestamp"])
        equity["period_return"] = equity["equity"].pct_change(fill_method=None).fillna(0.0)
        merged = regimes.merge(equity.loc[:, ["timestamp", "period_return"]], on="timestamp", how="left")
        records = []
        for regime, group in merged.groupby("regime", sort=True):
            compounded_return = float((1 + group["period_return"].fillna(0.0)).prod() - 1)
            records.append(RegimePerformance(str(regime), int(len(group)), compounded_return))
        return records

    @staticmethod
    def _decision_summary(agent_decisions: pd.DataFrame) -> DecisionHistorySummary:
        if agent_decisions.empty:
            return DecisionHistorySummary(0, 0, 0, {}, {})
        approved = int(agent_decisions["risk_approved"].astype(bool).sum())
        return DecisionHistorySummary(
            observations=int(len(agent_decisions)),
            approved_decisions=approved,
            rejected_decisions=int(len(agent_decisions) - approved),
            action_counts={str(key): int(value) for key, value in agent_decisions["execution_action"].value_counts().items()},
            strategy_counts={str(key): int(value) for key, value in agent_decisions["selected_strategy"].value_counts().items()},
        )

    @staticmethod
    def _optional_float(value: object) -> float | None:
        return None if value is None or pd.isna(value) else float(value)
