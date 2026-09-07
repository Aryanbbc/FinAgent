"""Typed, transparent records for V0.6 research validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricSnapshot:
    """Comparable cost-aware performance metrics for one configuration and evaluation slice."""

    total_return: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    maximum_drawdown: float | None
    turnover: float | None
    transaction_cost: float
    number_of_trades: int

    @classmethod
    def from_metrics(cls, metrics: dict[str, Any], transaction_cost: float = 0.0) -> "MetricSnapshot":
        return cls(
            _optional_float(metrics.get("total_return")),
            _optional_float(metrics.get("sharpe_ratio")),
            _optional_float(metrics.get("sortino_ratio")),
            _optional_float(metrics.get("maximum_drawdown")),
            _optional_float(metrics.get("turnover")),
            float(transaction_cost),
            int(metrics.get("number_of_trades") or 0),
        )

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "maximum_drawdown": self.maximum_drawdown,
            "turnover": self.turnover,
            "transaction_cost": self.transaction_cost,
            "number_of_trades": self.number_of_trades,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricSnapshot":
        return cls(
            _optional_float(data.get("total_return")),
            _optional_float(data.get("sharpe_ratio")),
            _optional_float(data.get("sortino_ratio")),
            _optional_float(data.get("maximum_drawdown")),
            _optional_float(data.get("turnover")),
            float(data.get("transaction_cost") or 0.0),
            int(data.get("number_of_trades") or 0),
        )


@dataclass(frozen=True)
class AssetSpec:
    asset: str
    dataset: str

    def to_dict(self) -> dict[str, str]:
        return {"asset": self.asset, "dataset": self.dataset}


@dataclass(frozen=True)
class AssetValidationResult:
    asset: str
    dataset: str
    start_date: str
    end_date: str
    metrics: MetricSnapshot
    benchmark_metrics: MetricSnapshot
    passed: bool
    regime_distribution: dict[str, int]
    agent_observations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "dataset": self.dataset,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "metrics": self.metrics.to_dict(),
            "benchmark_metrics": self.benchmark_metrics.to_dict(),
            "passed": self.passed,
            "regime_distribution": self.regime_distribution,
            "agent_observations": self.agent_observations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetValidationResult":
        return cls(
            str(data["asset"]),
            str(data["dataset"]),
            str(data["start_date"]),
            str(data["end_date"]),
            MetricSnapshot.from_dict(dict(data["metrics"])),
            MetricSnapshot.from_dict(dict(data["benchmark_metrics"])),
            bool(data["passed"]),
            {str(key): int(value) for key, value in data.get("regime_distribution", {}).items()},
            int(data.get("agent_observations") or 0),
        )


@dataclass(frozen=True)
class ResearchWindowResult:
    asset: str
    window_index: int
    window_mode: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_observations: int
    test_observations: int
    metrics: MetricSnapshot

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "window_index": self.window_index,
            "window_mode": self.window_mode,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "train_observations": self.train_observations,
            "test_observations": self.test_observations,
            "metrics": self.metrics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchWindowResult":
        return cls(
            str(data["asset"]),
            int(data["window_index"]),
            str(data["window_mode"]),
            str(data["train_start"]),
            str(data["train_end"]),
            str(data["test_start"]),
            str(data["test_end"]),
            int(data["train_observations"]),
            int(data["test_observations"]),
            MetricSnapshot.from_dict(dict(data["metrics"])),
        )


@dataclass(frozen=True)
class LeakageCheckResult:
    passed: bool
    checks: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": list(self.checks), "errors": list(self.errors)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeakageCheckResult":
        return cls(bool(data["passed"]), tuple(data.get("checks", [])), tuple(data.get("errors", [])))


@dataclass(frozen=True)
class ConfidenceInterval:
    metric: str
    estimate: float | None
    lower: float | None
    upper: float | None
    confidence_level: float
    samples: int
    estimated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "estimate": self.estimate,
            "lower": self.lower,
            "upper": self.upper,
            "confidence_level": self.confidence_level,
            "samples": self.samples,
            "estimated": self.estimated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfidenceInterval":
        return cls(
            str(data["metric"]),
            _optional_float(data.get("estimate")),
            _optional_float(data.get("lower")),
            _optional_float(data.get("upper")),
            float(data["confidence_level"]),
            int(data["samples"]),
            bool(data.get("estimated", True)),
        )


@dataclass(frozen=True)
class SensitivityPoint:
    parameter: str
    value: Any
    metrics: MetricSnapshot
    stability_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "value": self.value,
            "metrics": self.metrics.to_dict(),
            "stability_score": self.stability_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SensitivityPoint":
        return cls(
            str(data["parameter"]), data.get("value"), MetricSnapshot.from_dict(dict(data["metrics"])), float(data["stability_score"])
        )


@dataclass(frozen=True)
class RobustnessScore:
    score: float
    components: dict[str, float]
    weights: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "components": self.components, "weights": self.weights}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RobustnessScore":
        return cls(
            float(data["score"]),
            {str(key): float(value) for key, value in data.get("components", {}).items()},
            {str(key): float(value) for key, value in data.get("weights", {}).items()},
        )


@dataclass(frozen=True)
class AblationResult:
    variant: str
    enabled_components: tuple[str, ...]
    metrics: MetricSnapshot
    robustness: RobustnessScore

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "enabled_components": list(self.enabled_components),
            "metrics": self.metrics.to_dict(),
            "robustness": self.robustness.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AblationResult":
        return cls(
            str(data["variant"]),
            tuple(data.get("enabled_components", [])),
            MetricSnapshot.from_dict(dict(data["metrics"])),
            RobustnessScore.from_dict(dict(data["robustness"])),
        )


@dataclass(frozen=True)
class BenchmarkResult:
    asset: str
    benchmark: str
    metrics: MetricSnapshot
    available: bool = True
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "benchmark": self.benchmark,
            "metrics": self.metrics.to_dict(),
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkResult":
        return cls(
            str(data["asset"]),
            str(data["benchmark"]),
            MetricSnapshot.from_dict(dict(data["metrics"])),
            bool(data.get("available", True)),
            str(data["unavailable_reason"]) if data.get("unavailable_reason") is not None else None,
        )


@dataclass(frozen=True)
class ReproducibilityManifest:
    experiment_id: str
    created_at: str
    random_seeds: dict[str, int | None]
    configuration: dict[str, Any]
    datasets: tuple[dict[str, Any], ...]
    assets: tuple[str, ...]
    date_ranges: dict[str, dict[str, str]]
    enabled_modules: dict[str, bool]
    code_version: str
    transaction_costs: dict[str, float]
    evaluation_mode: str
    walk_forward: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "created_at": self.created_at,
            "random_seeds": self.random_seeds,
            "configuration": self.configuration,
            "datasets": list(self.datasets),
            "assets": list(self.assets),
            "date_ranges": self.date_ranges,
            "enabled_modules": self.enabled_modules,
            "code_version": self.code_version,
            "transaction_costs": self.transaction_costs,
            "evaluation_mode": self.evaluation_mode,
            "walk_forward": self.walk_forward,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReproducibilityManifest":
        return cls(
            str(data["experiment_id"]),
            str(data["created_at"]),
            dict(data.get("random_seeds", {})),
            dict(data.get("configuration", {})),
            tuple(dict(item) for item in data.get("datasets", [])),
            tuple(str(item) for item in data.get("assets", [])),
            {str(key): dict(value) for key, value in data.get("date_ranges", {}).items()},
            {str(key): bool(value) for key, value in data.get("enabled_modules", {}).items()},
            str(data.get("code_version", "unavailable")),
            {str(key): float(value) for key, value in data.get("transaction_costs", {}).items()},
            str(data.get("evaluation_mode", "single_asset")),
            dict(data.get("walk_forward", {})),
        )


@dataclass(frozen=True)
class ResearchValidationResult:
    validation_id: str
    experiment_id: str
    asset_results: tuple[AssetValidationResult, ...]
    aggregate_metrics: MetricSnapshot
    windows: tuple[ResearchWindowResult, ...]
    leakage: LeakageCheckResult
    sensitivity: tuple[SensitivityPoint, ...]
    confidence_intervals: tuple[ConfidenceInterval, ...]
    robustness: RobustnessScore
    ablations: tuple[AblationResult, ...]
    benchmarks: tuple[BenchmarkResult, ...]
    manifest: ReproducibilityManifest

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "experiment_id": self.experiment_id,
            "asset_results": [item.to_dict() for item in self.asset_results],
            "aggregate_metrics": self.aggregate_metrics.to_dict(),
            "windows": [item.to_dict() for item in self.windows],
            "leakage": self.leakage.to_dict(),
            "sensitivity": [item.to_dict() for item in self.sensitivity],
            "confidence_intervals": [item.to_dict() for item in self.confidence_intervals],
            "robustness": self.robustness.to_dict(),
            "ablations": [item.to_dict() for item in self.ablations],
            "benchmarks": [item.to_dict() for item in self.benchmarks],
            "manifest": self.manifest.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchValidationResult":
        return cls(
            str(data["validation_id"]),
            str(data["experiment_id"]),
            tuple(AssetValidationResult.from_dict(item) for item in data.get("asset_results", [])),
            MetricSnapshot.from_dict(dict(data["aggregate_metrics"])),
            tuple(ResearchWindowResult.from_dict(item) for item in data.get("windows", [])),
            LeakageCheckResult.from_dict(dict(data["leakage"])),
            tuple(SensitivityPoint.from_dict(item) for item in data.get("sensitivity", [])),
            tuple(ConfidenceInterval.from_dict(item) for item in data.get("confidence_intervals", [])),
            RobustnessScore.from_dict(dict(data["robustness"])),
            tuple(AblationResult.from_dict(item) for item in data.get("ablations", [])),
            tuple(BenchmarkResult.from_dict(item) for item in data.get("benchmarks", [])),
            ReproducibilityManifest.from_dict(dict(data["manifest"])),
        )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
