"""Transparent V0.6 robustness, bootstrap, sensitivity, ablation, and benchmark analyses."""

from __future__ import annotations

import copy
import hashlib
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from finagent import __version__
from finagent.learning.candidate_generator import CandidateGenerator
from finagent.validation.engine import SimulationResult, simulate_configuration
from finagent.validation.models import (
    AblationResult,
    AssetValidationResult,
    BenchmarkResult,
    ConfidenceInterval,
    MetricSnapshot,
    ReproducibilityManifest,
    RobustnessScore,
    SensitivityPoint,
)


@dataclass(frozen=True)
class BootstrapConfig:
    samples: int = 500
    confidence_level: float = 0.95
    random_seed: int = 42

    def __post_init__(self) -> None:
        if self.samples < 10:
            raise ValueError("Bootstrap samples must be at least 10")
        if not 0 < self.confidence_level < 1:
            raise ValueError("Bootstrap confidence_level must be between zero and one")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "BootstrapConfig":
        return cls(
            samples=int(raw.get("samples", 500)),
            confidence_level=float(raw.get("confidence_level", 0.95)),
            random_seed=int(raw.get("random_seed", 42)),
        )


@dataclass(frozen=True)
class RobustnessScoreConfig:
    maximum_drawdown: float = 0.20
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "asset_consistency": 1.0,
            "window_consistency": 1.0,
            "sensitivity_stability": 1.0,
            "drawdown_control": 1.0,
            "turnover_stability": 1.0,
            "benchmark_consistency": 1.0,
        }
    )

    def __post_init__(self) -> None:
        if self.maximum_drawdown <= 0 or not self.weights or any(value < 0 for value in self.weights.values()):
            raise ValueError("Robustness settings require a positive drawdown limit and non-negative weights")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RobustnessScoreConfig":
        return cls(float(raw.get("maximum_drawdown", 0.20)), dict(raw.get("weights", {})) or cls().weights)


def bootstrap_confidence_intervals(
    equity_curve: pd.DataFrame, annualization_factor: int, configuration: BootstrapConfig
) -> tuple[ConfidenceInterval, ConfidenceInterval]:
    """Estimate percentile bootstrap intervals from realized historical returns, not forecasts."""
    returns = equity_curve["equity"].astype(float).pct_change(fill_method=None).dropna().to_numpy()
    alpha = (1 - configuration.confidence_level) / 2
    if len(returns) == 0:
        unavailable = ConfidenceInterval("mean_return", None, None, None, configuration.confidence_level, configuration.samples)
        return unavailable, ConfidenceInterval("sharpe_ratio", None, None, None, configuration.confidence_level, configuration.samples)
    generator = np.random.default_rng(configuration.random_seed)
    sampled_returns = generator.choice(returns, size=(configuration.samples, len(returns)), replace=True)
    mean_samples = sampled_returns.mean(axis=1)
    mean_interval = ConfidenceInterval(
        "mean_return",
        float(returns.mean()),
        float(np.quantile(mean_samples, alpha)),
        float(np.quantile(mean_samples, 1 - alpha)),
        configuration.confidence_level,
        configuration.samples,
    )
    sample_standard_deviation = sampled_returns.std(axis=1, ddof=1)
    valid = sample_standard_deviation > 0
    if len(returns) < 2 or not valid.any() or returns.std(ddof=1) == 0:
        return mean_interval, ConfidenceInterval(
            "sharpe_ratio", None, None, None, configuration.confidence_level, configuration.samples
        )
    sharpe_samples = (sampled_returns[valid].mean(axis=1) / sample_standard_deviation[valid]) * np.sqrt(annualization_factor)
    sharpe_estimate = float((returns.mean() / returns.std(ddof=1)) * np.sqrt(annualization_factor))
    return mean_interval, ConfidenceInterval(
        "sharpe_ratio",
        sharpe_estimate,
        float(np.quantile(sharpe_samples, alpha)),
        float(np.quantile(sharpe_samples, 1 - alpha)),
        configuration.confidence_level,
        configuration.samples,
    )


def aggregate_metrics(metrics: Sequence[MetricSnapshot]) -> MetricSnapshot:
    """Create an equal-weight cross-asset summary; costs and trades are summed, drawdown is worst-case."""
    if not metrics:
        return MetricSnapshot(None, None, None, None, None, 0.0, 0)
    return MetricSnapshot(
        _mean(metric.total_return for metric in metrics),
        _mean(metric.sharpe_ratio for metric in metrics),
        _mean(metric.sortino_ratio for metric in metrics),
        min((metric.maximum_drawdown for metric in metrics if metric.maximum_drawdown is not None), default=None),
        _mean(metric.turnover for metric in metrics),
        sum(metric.transaction_cost for metric in metrics),
        sum(metric.number_of_trades for metric in metrics),
    )


class RobustnessScorer:
    """Calculates an inspectable weighted robustness score from 0 to 1."""

    def __init__(self, configuration: RobustnessScoreConfig | None = None) -> None:
        self.configuration = configuration or RobustnessScoreConfig()

    def calculate(
        self,
        asset_results: Sequence[AssetValidationResult],
        window_metrics: Sequence[MetricSnapshot],
        sensitivity: Sequence[SensitivityPoint],
    ) -> RobustnessScore:
        asset_sharpes = [item.metrics.sharpe_ratio for item in asset_results]
        window_sharpes = [item.sharpe_ratio for item in window_metrics]
        turnovers = [item.metrics.turnover for item in asset_results]
        drawdowns = [item.metrics.maximum_drawdown for item in asset_results if item.metrics.maximum_drawdown is not None]
        components = {
            "asset_consistency": _consistency(asset_sharpes),
            "window_consistency": _consistency(window_sharpes),
            "sensitivity_stability": _mean(point.stability_score for point in sensitivity) if sensitivity else 1.0,
            "drawdown_control": _clamp(1 - abs(min(drawdowns, default=-self.configuration.maximum_drawdown)) / self.configuration.maximum_drawdown),
            "turnover_stability": _consistency(turnovers),
            "benchmark_consistency": (
                sum(item.metrics.total_return >= item.benchmark_metrics.total_return for item in asset_results
                    if item.metrics.total_return is not None and item.benchmark_metrics.total_return is not None)
                / len(asset_results)
                if asset_results
                else 0.0
            ),
        }
        weighted_total = sum(components[name] * self.configuration.weights.get(name, 0.0) for name in components)
        weight_total = sum(self.configuration.weights.get(name, 0.0) for name in components)
        return RobustnessScore(_clamp(weighted_total / weight_total) if weight_total else 0.0, components, self.configuration.weights)


class SensitivityAnalyzer:
    """Evaluates only V0.5-approved configuration parameters and reports local stability."""

    def analyze(
        self,
        simulations_by_asset: Sequence[tuple[str, pd.DataFrame]],
        configuration: dict[str, Any],
        boundaries: Mapping[str, Sequence[Any]],
    ) -> tuple[SensitivityPoint, ...]:
        raw_points: list[tuple[str, Any, MetricSnapshot]] = []
        helper = CandidateGenerator()
        for parameter in sorted(boundaries):
            for value in boundaries[parameter]:
                candidate_configuration = helper.apply_parameter_change(configuration, parameter, value)
                snapshots = [simulate_configuration(data, candidate_configuration, asset).metric_snapshot for asset, data in simulations_by_asset]
                raw_points.append((parameter, value, aggregate_metrics(snapshots)))
        points: list[SensitivityPoint] = []
        for parameter in sorted({item[0] for item in raw_points}):
            group = [item for item in raw_points if item[0] == parameter]
            median_sharpe = float(np.median([item[2].sharpe_ratio for item in group if item[2].sharpe_ratio is not None])) if any(
                item[2].sharpe_ratio is not None for item in group
            ) else 0.0
            for _, value, metrics in group:
                stability = 0.0 if metrics.sharpe_ratio is None else _clamp(1 - abs(metrics.sharpe_ratio - median_sharpe) / (abs(median_sharpe) + 1))
                points.append(SensitivityPoint(parameter, value, metrics, stability))
        return tuple(points)


def benchmark_suite(simulations: Sequence[SimulationResult], configuration: dict[str, Any]) -> tuple[BenchmarkResult, ...]:
    """Run buy-and-hold and all three baseline strategies with identical data, capital, and costs."""
    results: list[BenchmarkResult] = []
    available = configuration.get("agents", {}).get("strategy", {}).get("available_strategies", {})
    for simulation in simulations:
        results.append(BenchmarkResult(simulation.asset, "finagent", simulation.metric_snapshot))
        results.append(BenchmarkResult(simulation.asset, "buy_and_hold", simulation.benchmark_snapshot))
        for strategy_name in ("moving_average", "momentum", "mean_reversion"):
            baseline_configuration = copy.deepcopy(configuration)
            baseline_configuration["strategy"] = {
                "name": strategy_name,
                "parameters": dict(available.get(strategy_name, {})),
            }
            baseline_configuration.setdefault("agents", {})["enabled"] = False
            baseline_configuration.setdefault("regime", {})["enabled"] = False
            baseline_configuration.setdefault("critic", {})["enabled"] = False
            baseline_configuration.setdefault("learning", {})["enabled"] = False
            metrics = simulate_configuration(simulation.market_data, baseline_configuration, simulation.asset).metric_snapshot
            results.append(BenchmarkResult(simulation.asset, strategy_name, metrics))
    return tuple(results)


def final_release_benchmark_suite(
    simulations: Sequence[SimulationResult], configuration: dict[str, Any]
) -> tuple[BenchmarkResult, ...]:
    """Run the fixed V1.0 release comparators without changing research behaviour.

    Critic/memory is deliberately identified as post-experiment evidence, so its
    in-run metrics equal the multi-agent comparator. A self-improved comparator
    is available only when a separately promoted configuration is supplied; this
    release suite never invents one from in-sample observations.
    """
    results: list[BenchmarkResult] = []
    available = configuration.get("agents", {}).get("strategy", {}).get("available_strategies", {})
    for simulation in simulations:
        results.append(BenchmarkResult(simulation.asset, "buy_and_hold", simulation.benchmark_snapshot))
        for strategy_name in ("moving_average", "momentum", "mean_reversion"):
            baseline = _benchmark_configuration(configuration, strategy_name, available, regime=False, agents=False, critic=False)
            results.append(
                BenchmarkResult(
                    simulation.asset,
                    strategy_name,
                    simulate_configuration(simulation.market_data, baseline, simulation.asset).metric_snapshot,
                )
            )
        regime_aware = _benchmark_configuration(
            configuration, str(configuration["strategy"]["name"]), available, regime=True, agents=False, critic=False
        )
        results.append(
            BenchmarkResult(
                simulation.asset,
                "regime_aware_finagent",
                simulate_configuration(simulation.market_data, regime_aware, simulation.asset).metric_snapshot,
            )
        )
        multi_agent = _benchmark_configuration(
            configuration, str(configuration["strategy"]["name"]), available, regime=True, agents=True, critic=False
        )
        multi_agent_metrics = simulate_configuration(simulation.market_data, multi_agent, simulation.asset).metric_snapshot
        results.append(BenchmarkResult(simulation.asset, "multi_agent_finagent", multi_agent_metrics))
        # The critic and memory examine completed experiments; they cannot affect
        # a historical decision path in this deterministic release.
        results.append(BenchmarkResult(simulation.asset, "critic_memory_finagent", multi_agent_metrics))
        results.append(
            BenchmarkResult(
                simulation.asset,
                "self_improved_finagent",
                MetricSnapshot(None, None, None, None, None, 0.0, 0),
                available=False,
                unavailable_reason="no_promoted_configuration",
            )
        )
    return tuple(results)


def _benchmark_configuration(
    configuration: dict[str, Any], strategy_name: str, available: Mapping[str, Any], *, regime: bool, agents: bool, critic: bool
) -> dict[str, Any]:
    """Create an isolated, explicitly labelled comparator configuration."""
    result = copy.deepcopy(configuration)
    result["strategy"] = {"name": strategy_name, "parameters": dict(available.get(strategy_name, result["strategy"].get("parameters", {})))}
    result.setdefault("regime", {})["enabled"] = regime
    result.setdefault("agents", {})["enabled"] = agents
    result.setdefault("critic", {})["enabled"] = critic
    result.setdefault("learning", {})["enabled"] = False
    return result


def ablation_study(simulations_by_asset: Sequence[tuple[str, pd.DataFrame]], configuration: dict[str, Any], scorer: RobustnessScorer) -> tuple[AblationResult, ...]:
    """Compare fixed component configurations; post-experiment modules never influence in-run execution."""
    variants = (
        ("A: baseline strategy only", ("baseline_strategy",), {"regime": False, "agents": False, "critic": False, "learning": False}),
        ("B: + regime detection", ("baseline_strategy", "regime"), {"regime": True, "agents": False, "critic": False, "learning": False}),
        ("C: + multi-agent decision system", ("baseline_strategy", "regime", "agents"), {"regime": True, "agents": True, "critic": False, "learning": False}),
        ("D: + critic/memory", ("baseline_strategy", "regime", "agents", "critic_memory"), {"regime": True, "agents": True, "critic": True, "learning": False}),
        ("E: + self-improvement", ("baseline_strategy", "regime", "agents", "critic_memory", "learning"), {"regime": True, "agents": True, "critic": True, "learning": True}),
    )
    results: list[AblationResult] = []
    for name, components, enabled in variants:
        variant_configuration = copy.deepcopy(configuration)
        variant_configuration.setdefault("regime", {})["enabled"] = enabled["regime"]
        variant_configuration.setdefault("agents", {})["enabled"] = enabled["agents"]
        variant_configuration.setdefault("critic", {})["enabled"] = enabled["critic"]
        variant_configuration.setdefault("learning", {})["enabled"] = enabled["learning"]
        asset_results = []
        for asset, data in simulations_by_asset:
            simulation = simulate_configuration(data, variant_configuration, asset)
            asset_results.append(
                AssetValidationResult(
                    asset, "ablation", "", "", simulation.metric_snapshot, simulation.benchmark_snapshot,
                    True, {}, len(simulation.backtest.agent_decisions),
                )
            )
        results.append(AblationResult(name, components, aggregate_metrics([item.metrics for item in asset_results]), scorer.calculate(asset_results, (), ())))
    return tuple(results)


def build_manifest(
    experiment_id: str,
    configuration: dict[str, Any],
    assets: Sequence[AssetValidationResult],
    evaluation_mode: str,
    walk_forward: Mapping[str, Any],
    project_root: Path,
    dataset_provenance: Mapping[str, Mapping[str, Any]] | None = None,
) -> ReproducibilityManifest:
    """Capture sufficient configuration, data, and version facts to reproduce a historical validation run."""
    datasets = []
    for item in assets:
        identifier = _dataset_identifier(Path(item.dataset), project_root)
        if dataset_provenance and item.asset in dataset_provenance:
            identifier["registry"] = dict(dataset_provenance[item.asset])
        datasets.append(identifier)
    backtest = configuration.get("backtest", {})
    return ReproducibilityManifest(
        experiment_id=experiment_id,
        created_at=datetime.now(UTC).isoformat(),
        random_seeds={"experiment": configuration.get("experiment", {}).get("random_seed"), "bootstrap": None},
        configuration=copy.deepcopy(configuration),
        datasets=tuple(datasets),
        assets=tuple(item.asset for item in assets),
        date_ranges={item.asset: {"start": item.start_date, "end": item.end_date} for item in assets},
        enabled_modules={
            "regime": bool(configuration.get("regime", {}).get("enabled", True)),
            "agents": bool(configuration.get("agents", {}).get("enabled", False)),
            "critic": bool(configuration.get("critic", {}).get("enabled", False)),
            "learning": bool(configuration.get("learning", {}).get("enabled", False)),
        },
        code_version=_code_version(project_root),
        transaction_costs={str(key): float(value) for key, value in backtest.get("transaction_costs", {}).items()},
        evaluation_mode=evaluation_mode,
        walk_forward=dict(walk_forward),
    )


def _dataset_identifier(dataset: Path, root: Path) -> dict[str, Any]:
    path = dataset if dataset.is_absolute() else root / dataset
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "unavailable"
    return {"dataset": str(dataset), "sha256": digest, "bytes": path.stat().st_size if path.exists() else None}


def _code_version(project_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=project_root, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=project_root, check=True, capture_output=True, text=True
            ).stdout.strip()
        )
        return f"{__version__}+{revision}{'.dirty' if dirty else ''}"
    except (OSError, subprocess.CalledProcessError):
        return f"{__version__}+unavailable"


def _mean(values: Any) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return float(np.mean(usable)) if usable else None


def _consistency(values: Sequence[float | None]) -> float:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return 0.0
    if len(usable) == 1:
        return 1.0
    return _clamp(1 - float(np.std(usable, ddof=0)) / (abs(float(np.mean(usable))) + 1))


def _clamp(value: float) -> float:
    return float(max(0.0, min(1.0, value)))
