"""Typed stored-memory records and query results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finagent.critique.models import ExperimentCritique


@dataclass(frozen=True)
class RegimePerformance:
    regime: str
    observations: int
    compounded_return: float

    def to_dict(self) -> dict[str, object]:
        return {"regime": self.regime, "observations": self.observations, "compounded_return": self.compounded_return}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimePerformance":
        return cls(str(data["regime"]), int(data["observations"]), float(data["compounded_return"]))


@dataclass(frozen=True)
class DecisionHistorySummary:
    observations: int
    approved_decisions: int
    rejected_decisions: int
    action_counts: dict[str, int]
    strategy_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "observations": self.observations,
            "approved_decisions": self.approved_decisions,
            "rejected_decisions": self.rejected_decisions,
            "action_counts": self.action_counts,
            "strategy_counts": self.strategy_counts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionHistorySummary":
        return cls(
            observations=int(data["observations"]),
            approved_decisions=int(data["approved_decisions"]),
            rejected_decisions=int(data["rejected_decisions"]),
            action_counts={str(key): int(value) for key, value in data.get("action_counts", {}).items()},
            strategy_counts={str(key): int(value) for key, value in data.get("strategy_counts", {}).items()},
        )


@dataclass(frozen=True)
class ExperimentMemoryRecord:
    experiment_id: str
    agent_version: str
    strategy: str
    strategy_parameters: dict[str, Any]
    regime_distribution: dict[str, int]
    regime_performance: tuple[RegimePerformance, ...]
    metrics: dict[str, float | int | None]
    maximum_drawdown: float
    turnover: float | None
    transaction_costs: dict[str, float]
    critique: ExperimentCritique
    decision_summary: DecisionHistorySummary

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "agent_version": self.agent_version,
            "strategy": self.strategy,
            "strategy_parameters": self.strategy_parameters,
            "regime_distribution": self.regime_distribution,
            "regime_performance": [item.to_dict() for item in self.regime_performance],
            "metrics": self.metrics,
            "maximum_drawdown": self.maximum_drawdown,
            "turnover": self.turnover,
            "transaction_costs": self.transaction_costs,
            "critique": self.critique.to_dict(),
            "decision_summary": self.decision_summary.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentMemoryRecord":
        return cls(
            experiment_id=data["experiment_id"],
            agent_version=data["agent_version"],
            strategy=data["strategy"],
            strategy_parameters=dict(data.get("strategy_parameters", {})),
            regime_distribution={str(key): int(value) for key, value in data.get("regime_distribution", {}).items()},
            regime_performance=tuple(RegimePerformance.from_dict(item) for item in data.get("regime_performance", [])),
            metrics=dict(data.get("metrics", {})),
            maximum_drawdown=float(data["maximum_drawdown"]),
            turnover=data.get("turnover"),
            transaction_costs={str(key): float(value) for key, value in data.get("transaction_costs", {}).items()},
            critique=ExperimentCritique.from_dict(data["critique"]),
            decision_summary=DecisionHistorySummary.from_dict(data["decision_summary"]),
        )


@dataclass(frozen=True)
class MemoryQueryResult:
    experiment_id: str
    strategy: str
    regime: str | None
    regime_return: float | None
    maximum_drawdown: float
    turnover: float | None
    created_at: str
