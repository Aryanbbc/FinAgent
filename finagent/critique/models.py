"""Typed schemas for deterministic experiment critiques."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd


class CritiqueReasonCode(str, Enum):
    CRITIQUE_COMPLETED = "CRITIQUE_COMPLETED"
    OUTPERFORMS_BENCHMARK = "OUTPERFORMS_BENCHMARK"
    UNDERPERFORMS_BENCHMARK = "UNDERPERFORMS_BENCHMARK"
    POSITIVE_RETURN = "POSITIVE_RETURN"
    NEGATIVE_RETURN = "NEGATIVE_RETURN"
    STRONG_SHARPE = "STRONG_SHARPE"
    WEAK_SHARPE = "WEAK_SHARPE"
    CONTROLLED_DRAWDOWN = "CONTROLLED_DRAWDOWN"
    HIGH_DRAWDOWN = "HIGH_DRAWDOWN"
    LOW_TURNOVER = "LOW_TURNOVER"
    EXCESSIVE_TURNOVER = "EXCESSIVE_TURNOVER"
    HIGH_TRANSACTION_COSTS = "HIGH_TRANSACTION_COSTS"
    LOW_TRADE_SAMPLE = "LOW_TRADE_SAMPLE"
    RISK_REJECTIONS = "RISK_REJECTIONS"


@dataclass(frozen=True)
class TradeStatistics:
    number_of_executions: int
    closed_trades: int
    total_notional: float
    total_transaction_cost: float
    transaction_cost_ratio: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "number_of_executions": self.number_of_executions,
            "closed_trades": self.closed_trades,
            "total_notional": self.total_notional,
            "total_transaction_cost": self.total_transaction_cost,
            "transaction_cost_ratio": self.transaction_cost_ratio,
        }


@dataclass(frozen=True)
class TransactionCostAssumptions:
    percentage_fee: float
    fixed_fee: float

    def to_dict(self) -> dict[str, float]:
        return {"percentage_fee": self.percentage_fee, "fixed_fee": self.fixed_fee}


@dataclass(frozen=True)
class CriticAgentInput:
    experiment_id: str
    strategy: str
    strategy_parameters: dict[str, Any]
    metrics: dict[str, float | int | None]
    benchmark_metrics: dict[str, float | int | None]
    regime_history: pd.DataFrame
    agent_decision_history: pd.DataFrame
    trade_statistics: TradeStatistics
    transaction_costs: TransactionCostAssumptions


@dataclass(frozen=True)
class CritiqueFinding:
    code: CritiqueReasonCode
    summary: str
    evidence: dict[str, float | int | str | None]

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "summary": self.summary, "evidence": self.evidence}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CritiqueFinding":
        return cls(CritiqueReasonCode(data["code"]), data["summary"], dict(data.get("evidence", {})))


@dataclass(frozen=True)
class RegimeObservationSummary:
    regime: str
    observations: int
    trade_executions: int
    risk_rejections: int
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "regime": self.regime,
            "observations": self.observations,
            "trade_executions": self.trade_executions,
            "risk_rejections": self.risk_rejections,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimeObservationSummary":
        return cls(
            regime=data["regime"],
            observations=int(data["observations"]),
            trade_executions=int(data["trade_executions"]),
            risk_rejections=int(data["risk_rejections"]),
            summary=data["summary"],
        )


@dataclass(frozen=True)
class CritiqueRecommendation:
    parameter: str
    direction: str
    rationale: str
    reason_code: CritiqueReasonCode

    def to_dict(self) -> dict[str, str]:
        return {
            "parameter": self.parameter,
            "direction": self.direction,
            "rationale": self.rationale,
            "reason_code": self.reason_code.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "CritiqueRecommendation":
        return cls(data["parameter"], data["direction"], data["rationale"], CritiqueReasonCode(data["reason_code"]))


@dataclass(frozen=True)
class ExperimentCritique:
    experiment_id: str
    strengths: tuple[CritiqueFinding, ...]
    weaknesses: tuple[CritiqueFinding, ...]
    failure_modes: tuple[CritiqueFinding, ...]
    regime_observations: tuple[RegimeObservationSummary, ...]
    recommendations: tuple[CritiqueRecommendation, ...]
    reason_codes: tuple[CritiqueReasonCode, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("Critique confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "strengths": [finding.to_dict() for finding in self.strengths],
            "weaknesses": [finding.to_dict() for finding in self.weaknesses],
            "failure_modes": [finding.to_dict() for finding in self.failure_modes],
            "regime_observations": [observation.to_dict() for observation in self.regime_observations],
            "recommendations": [recommendation.to_dict() for recommendation in self.recommendations],
            "reason_codes": [code.value for code in self.reason_codes],
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentCritique":
        return cls(
            experiment_id=data["experiment_id"],
            strengths=tuple(CritiqueFinding.from_dict(item) for item in data.get("strengths", [])),
            weaknesses=tuple(CritiqueFinding.from_dict(item) for item in data.get("weaknesses", [])),
            failure_modes=tuple(CritiqueFinding.from_dict(item) for item in data.get("failure_modes", [])),
            regime_observations=tuple(
                RegimeObservationSummary.from_dict(item) for item in data.get("regime_observations", [])
            ),
            recommendations=tuple(CritiqueRecommendation.from_dict(item) for item in data.get("recommendations", [])),
            reason_codes=tuple(CritiqueReasonCode(code) for code in data.get("reason_codes", [])),
            confidence=float(data["confidence"]),
        )
