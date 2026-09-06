"""Typed, auditable records for the V0.5 controlled improvement workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CandidateReasonCode(str, Enum):
    """Why a bounded configuration candidate was generated or rejected."""

    MEMORY_RETRIEVED = "MEMORY_RETRIEVED"
    CRITIC_RECOMMENDATION = "CRITIC_RECOMMENDATION"
    REGIME_UNDERPERFORMANCE = "REGIME_UNDERPERFORMANCE"
    EXCESSIVE_TURNOVER = "EXCESSIVE_TURNOVER"
    HIGH_DRAWDOWN = "HIGH_DRAWDOWN"
    NEIGHBORHOOD_SEARCH = "NEIGHBORHOOD_SEARCH"
    GRID_SEARCH = "GRID_SEARCH"
    CONFIGURATION_VIOLATION = "CONFIGURATION_VIOLATION"
    INVALID_METRICS = "INVALID_METRICS"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    OUT_OF_SAMPLE_SHARPE_NOT_IMPROVED = "OUT_OF_SAMPLE_SHARPE_NOT_IMPROVED"
    MAXIMUM_DRAWDOWN_EXCEEDED = "MAXIMUM_DRAWDOWN_EXCEEDED"
    EXCESSIVE_TURNOVER_REJECTED = "EXCESSIVE_TURNOVER_REJECTED"
    TRANSACTION_COSTS_ERASE_ADVANTAGE = "TRANSACTION_COSTS_ERASE_ADVANTAGE"
    INCONSISTENT_OUT_OF_SAMPLE_RESULTS = "INCONSISTENT_OUT_OF_SAMPLE_RESULTS"
    INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
    NOT_SELECTED = "NOT_SELECTED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class PromotionStatus(str, Enum):
    BASELINE = "BASELINE"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ParameterChange:
    """One approved configuration value modified by a candidate."""

    parameter: str
    previous_value: Any
    proposed_value: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "previous_value": self.previous_value,
            "proposed_value": self.proposed_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParameterChange":
        return cls(str(data["parameter"]), data.get("previous_value"), data.get("proposed_value"))


@dataclass(frozen=True)
class CandidateProposal:
    """A complete, executable candidate configuration derived from one parent version."""

    candidate_id: str
    parent_version_id: str
    configuration: dict[str, Any]
    parameter_changes: tuple[ParameterChange, ...]
    reason_codes: tuple[CandidateReasonCode, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parent_version_id": self.parent_version_id,
            "configuration": self.configuration,
            "parameter_changes": [change.to_dict() for change in self.parameter_changes],
            "reason_codes": [code.value for code in self.reason_codes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateProposal":
        return cls(
            candidate_id=str(data["candidate_id"]),
            parent_version_id=str(data["parent_version_id"]),
            configuration=dict(data["configuration"]),
            parameter_changes=tuple(ParameterChange.from_dict(item) for item in data.get("parameter_changes", [])),
            reason_codes=tuple(CandidateReasonCode(item) for item in data.get("reason_codes", [])),
        )


@dataclass(frozen=True)
class LearningAgentInput:
    """The deterministic post-experiment evidence available to the LearningAgent."""

    current_version_id: str
    current_configuration: dict[str, Any]
    memory: dict[str, Any]
    critique: dict[str, Any]
    boundaries: dict[str, Any]
    search_mode: str = "neighborhood"
    max_candidates: int = 5


@dataclass(frozen=True)
class ValidationMetrics:
    """Risk-adjusted metrics calculated only from an out-of-sample test window."""

    total_return: float | None
    sharpe_ratio: float | None
    maximum_drawdown: float | None
    turnover: float | None
    transaction_cost: float
    number_of_trades: int

    @classmethod
    def from_mapping(cls, data: dict[str, Any], transaction_cost: float) -> "ValidationMetrics":
        return cls(
            total_return=_float_or_none(data.get("total_return")),
            sharpe_ratio=_float_or_none(data.get("sharpe_ratio")),
            maximum_drawdown=_float_or_none(data.get("maximum_drawdown")),
            turnover=_float_or_none(data.get("turnover")),
            transaction_cost=float(transaction_cost),
            number_of_trades=int(data.get("number_of_trades") or 0),
        )

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "maximum_drawdown": self.maximum_drawdown,
            "turnover": self.turnover,
            "transaction_cost": self.transaction_cost,
            "number_of_trades": self.number_of_trades,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationMetrics":
        return cls(
            total_return=_float_or_none(data.get("total_return")),
            sharpe_ratio=_float_or_none(data.get("sharpe_ratio")),
            maximum_drawdown=_float_or_none(data.get("maximum_drawdown")),
            turnover=_float_or_none(data.get("turnover")),
            transaction_cost=float(data.get("transaction_cost") or 0.0),
            number_of_trades=int(data.get("number_of_trades") or 0),
        )


@dataclass(frozen=True)
class WalkForwardWindow:
    """One chronological train/test split and its independent parent/candidate results."""

    window_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_observations: int
    test_observations: int
    parent_metrics: ValidationMetrics
    candidate_metrics: ValidationMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "train_observations": self.train_observations,
            "test_observations": self.test_observations,
            "parent_metrics": self.parent_metrics.to_dict(),
            "candidate_metrics": self.candidate_metrics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WalkForwardWindow":
        return cls(
            window_index=int(data["window_index"]),
            train_start=str(data["train_start"]),
            train_end=str(data["train_end"]),
            test_start=str(data["test_start"]),
            test_end=str(data["test_end"]),
            train_observations=int(data["train_observations"]),
            test_observations=int(data["test_observations"]),
            parent_metrics=ValidationMetrics.from_dict(dict(data["parent_metrics"])),
            candidate_metrics=ValidationMetrics.from_dict(dict(data["candidate_metrics"])),
        )


@dataclass(frozen=True)
class WalkForwardEvaluation:
    candidate_id: str
    parent_version_id: str
    windows: tuple[WalkForwardWindow, ...]
    parent_aggregate: ValidationMetrics
    candidate_aggregate: ValidationMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parent_version_id": self.parent_version_id,
            "windows": [window.to_dict() for window in self.windows],
            "parent_aggregate": self.parent_aggregate.to_dict(),
            "candidate_aggregate": self.candidate_aggregate.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WalkForwardEvaluation":
        return cls(
            candidate_id=str(data["candidate_id"]),
            parent_version_id=str(data["parent_version_id"]),
            windows=tuple(WalkForwardWindow.from_dict(item) for item in data.get("windows", [])),
            parent_aggregate=ValidationMetrics.from_dict(dict(data["parent_aggregate"])),
            candidate_aggregate=ValidationMetrics.from_dict(dict(data["candidate_aggregate"])),
        )


@dataclass(frozen=True)
class PromotionDecision:
    candidate_id: str
    parent_version_id: str
    status: PromotionStatus
    reason_codes: tuple[CandidateReasonCode, ...]
    parent_metrics: ValidationMetrics
    candidate_metrics: ValidationMetrics
    window_pass_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parent_version_id": self.parent_version_id,
            "status": self.status.value,
            "reason_codes": [code.value for code in self.reason_codes],
            "parent_metrics": self.parent_metrics.to_dict(),
            "candidate_metrics": self.candidate_metrics.to_dict(),
            "window_pass_rate": self.window_pass_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromotionDecision":
        return cls(
            candidate_id=str(data["candidate_id"]),
            parent_version_id=str(data["parent_version_id"]),
            status=PromotionStatus(data["status"]),
            reason_codes=tuple(CandidateReasonCode(item) for item in data.get("reason_codes", [])),
            parent_metrics=ValidationMetrics.from_dict(dict(data["parent_metrics"])),
            candidate_metrics=ValidationMetrics.from_dict(dict(data["candidate_metrics"])),
            window_pass_rate=float(data.get("window_pass_rate") or 0.0),
        )


@dataclass(frozen=True)
class ConfigurationVersion:
    """Immutable promoted (or initial baseline) configuration registry record."""

    version_id: str
    parent_version_id: str | None
    candidate_id: str | None
    configuration: dict[str, Any]
    validation_metrics: ValidationMetrics | None
    status: PromotionStatus
    reason_codes: tuple[CandidateReasonCode, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "parent_version_id": self.parent_version_id,
            "candidate_id": self.candidate_id,
            "configuration": self.configuration,
            "validation_metrics": self.validation_metrics.to_dict() if self.validation_metrics else None,
            "status": self.status.value,
            "reason_codes": [code.value for code in self.reason_codes],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigurationVersion":
        validation = data.get("validation_metrics")
        return cls(
            version_id=str(data["version_id"]),
            parent_version_id=data.get("parent_version_id"),
            candidate_id=data.get("candidate_id"),
            configuration=dict(data["configuration"]),
            validation_metrics=ValidationMetrics.from_dict(dict(validation)) if validation else None,
            status=PromotionStatus(data["status"]),
            reason_codes=tuple(CandidateReasonCode(item) for item in data.get("reason_codes", [])),
            created_at=str(data["created_at"]),
        )


@dataclass(frozen=True)
class ImprovementRunResult:
    """Structured result of one user-invoked, bounded improvement run."""

    current_version: ConfigurationVersion
    candidates: tuple[CandidateProposal, ...]
    evaluations: tuple[WalkForwardEvaluation, ...]
    decisions: tuple[PromotionDecision, ...]
    promoted_version: ConfigurationVersion | None


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)
