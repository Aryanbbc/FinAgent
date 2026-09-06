"""Deterministic promotion gate for out-of-sample configuration evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from finagent.learning.models import (
    CandidateReasonCode,
    PromotionDecision,
    PromotionStatus,
    ValidationMetrics,
    WalkForwardEvaluation,
)


@dataclass(frozen=True)
class PromotionGateConfig:
    """Explicit, conservative requirements for a candidate to become a new version."""

    minimum_sharpe_improvement: float = 0.0
    maximum_drawdown: float = 0.20
    minimum_window_pass_rate: float = 0.60
    minimum_windows: int = 1
    minimum_trades: int = 1
    maximum_turnover: float = 10.0

    def __post_init__(self) -> None:
        if self.maximum_drawdown <= 0 or self.minimum_trades < 0 or self.maximum_turnover < 0 or self.minimum_windows < 1:
            raise ValueError("Promotion risk limits must be non-negative and maximum_drawdown positive")
        if not 0 <= self.minimum_window_pass_rate <= 1:
            raise ValueError("minimum_window_pass_rate must be between zero and one")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PromotionGateConfig":
        return cls(
            minimum_sharpe_improvement=float(raw.get("minimum_sharpe_improvement", 0.0)),
            maximum_drawdown=float(raw.get("maximum_drawdown", 0.20)),
            minimum_window_pass_rate=float(raw.get("minimum_window_pass_rate", 0.60)),
            minimum_windows=int(raw.get("minimum_windows", 1)),
            minimum_trades=int(raw.get("minimum_trades", 1)),
            maximum_turnover=float(raw.get("maximum_turnover", 10.0)),
        )


class PromotionGate:
    """Promotes only candidates with consistent risk-adjusted held-out improvement."""

    def __init__(self, configuration: PromotionGateConfig | None = None) -> None:
        self.configuration = configuration or PromotionGateConfig()

    def decide(self, evaluation: WalkForwardEvaluation) -> PromotionDecision:
        candidate = evaluation.candidate_aggregate
        parent = evaluation.parent_aggregate
        reasons: list[CandidateReasonCode] = []
        if len(evaluation.windows) < self.configuration.minimum_windows:
            reasons.append(CandidateReasonCode.INSUFFICIENT_SAMPLE)
        if not self._complete(candidate) or not self._complete(parent):
            reasons.append(CandidateReasonCode.INVALID_METRICS)
        if candidate.number_of_trades < self.configuration.minimum_trades:
            reasons.append(CandidateReasonCode.INSUFFICIENT_TRADES)
        if candidate.maximum_drawdown is not None and candidate.maximum_drawdown < -self.configuration.maximum_drawdown:
            reasons.append(CandidateReasonCode.MAXIMUM_DRAWDOWN_EXCEEDED)
        if candidate.turnover is not None and candidate.turnover > self.configuration.maximum_turnover:
            reasons.append(CandidateReasonCode.EXCESSIVE_TURNOVER_REJECTED)

        window_passes = [
            window.candidate_metrics.sharpe_ratio is not None
            and window.parent_metrics.sharpe_ratio is not None
            and window.candidate_metrics.sharpe_ratio > window.parent_metrics.sharpe_ratio
            for window in evaluation.windows
        ]
        pass_rate = sum(window_passes) / len(window_passes) if window_passes else 0.0
        if pass_rate < self.configuration.minimum_window_pass_rate:
            reasons.append(CandidateReasonCode.INCONSISTENT_OUT_OF_SAMPLE_RESULTS)
        if (
            candidate.sharpe_ratio is None
            or parent.sharpe_ratio is None
            or candidate.sharpe_ratio < parent.sharpe_ratio + self.configuration.minimum_sharpe_improvement
        ):
            reasons.append(CandidateReasonCode.OUT_OF_SAMPLE_SHARPE_NOT_IMPROVED)
        if (
            candidate.total_return is not None
            and parent.total_return is not None
            and candidate.total_return <= parent.total_return
            and candidate.transaction_cost > 0
        ):
            reasons.append(CandidateReasonCode.TRANSACTION_COSTS_ERASE_ADVANTAGE)

        if reasons:
            reasons.append(CandidateReasonCode.REJECTED)
            status = PromotionStatus.REJECTED
        else:
            reasons.append(CandidateReasonCode.PROMOTED)
            status = PromotionStatus.PROMOTED
        return PromotionDecision(
            candidate_id=evaluation.candidate_id,
            parent_version_id=evaluation.parent_version_id,
            status=status,
            reason_codes=tuple(dict.fromkeys(reasons)),
            parent_metrics=parent,
            candidate_metrics=candidate,
            window_pass_rate=pass_rate,
        )

    @staticmethod
    def _complete(metrics: ValidationMetrics) -> bool:
        return all(
            value is not None
            for value in (metrics.total_return, metrics.sharpe_ratio, metrics.maximum_drawdown, metrics.turnover)
        )
