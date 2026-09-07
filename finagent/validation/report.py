"""Markdown research-report export for persisted FinAgent experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finagent.database.experiment_repository import ExperimentRepository
from finagent.validation.models import MetricSnapshot, ResearchValidationResult


class ResearchReportExporter:
    """Creates a portable Markdown report from stored research evidence; it performs no new evaluation."""

    def __init__(self, repository: ExperimentRepository) -> None:
        self.repository = repository

    def export(self, experiment_id: str, output_path: str | Path) -> Path:
        experiment = self.repository.get_experiment(experiment_id)
        if experiment is None:
            raise ValueError(f"Unknown experiment: {experiment_id}")
        validation = self.repository.latest_research_validation(experiment_id)
        manifest = self.repository.get_manifest(experiment_id)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self._render(experiment, validation, manifest.to_dict() if manifest else None), encoding="utf-8")
        return output

    def _render(self, experiment: Any, validation: ResearchValidationResult | None, manifest: dict[str, Any] | None) -> str:
        lines = [f"# FinAgent Research Report — {experiment.experiment_id}", "", "## Experiment Summary", ""]
        lines.extend(
            [
                f"- Strategy: `{experiment.strategy}`",
                f"- Asset: `{experiment.asset}`",
                f"- Dataset: `{experiment.dataset}`",
                f"- Dates: {experiment.start_date} to {experiment.end_date}",
                f"- Starting capital: {experiment.starting_capital:.2f}",
                "",
                "## Configuration",
                "",
                "```json",
                json.dumps(experiment.configuration, indent=2, sort_keys=True, default=str),
                "```",
                "",
                "## Primary Metrics",
                "",
                _metrics_table(
                    MetricSnapshot.from_metrics(
                        experiment.results["metrics"],
                        float(self.repository.get_trades(experiment.experiment_id)["transaction_cost"].sum()),
                    )
                ),
                "",
                "## Regime and Agent Summary",
                "",
                f"- Regime distribution: `{experiment.results.get('regime', {}).get('distribution', {})}`",
                f"- Agent observations: {experiment.results.get('agents', {}).get('observations', 0)}",
            ]
        )
        critique = experiment.results.get("critique", {})
        if critique.get("enabled") and critique.get("output"):
            output = critique["output"]
            lines.extend(
                ["", "## Critique Summary", "", f"- Confidence: {output['confidence']:.2f}",
                 f"- Strengths: {', '.join(item['code'] for item in output['strengths']) or 'None'}",
                 f"- Weaknesses: {', '.join(item['code'] for item in output['weaknesses']) or 'None'}" ]
            )
        if validation is not None:
            lines.extend(self._validation_sections(validation))
        else:
            lines.extend(["", "## Research Validation", "", "No research-validation suite is attached to this experiment."])
        lines.extend(["", "## Reproducibility Manifest", "", "```json", json.dumps(manifest or {}, indent=2, sort_keys=True), "```"])
        history = self.repository.configuration_version_history()
        lines.extend(["", "## Self-Improvement History", "", "| Version | Parent | Candidate | Status |", "|---|---|---|---|"])
        lines.extend([f"| {item.version_id} | {item.parent_version_id or ''} | {item.candidate_id or ''} | {item.status.value} |" for item in history] or ["| None | | | |"])
        lines.extend(
            [
                "",
                "## Limitations",
                "",
                "- All results are historical simulations and do not establish future performance or investment suitability.",
                "- Bootstrap intervals are estimated from observed returns; they do not account for regime changes, dependence, or model uncertainty.",
                "- Robustness is a transparent heuristic score, not a statistical proof of generalization.",
                "- FinAgent remains local, deterministic, and research-only: no LLMs, live data, paper trading, or brokerage execution.",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _validation_sections(validation: ResearchValidationResult) -> list[str]:
        lines = ["", "## Research Validation", "", f"- Validation ID: `{validation.validation_id}`", f"- Leakage checks: {'passed' if validation.leakage.passed else 'failed'}", "", "### Multi-Asset Summary", "", "| Asset | Return | Sharpe | Max drawdown | Passed |", "|---|---:|---:|---:|---|"]
        lines.extend(
            [
                f"| {item.asset} | {_pct(item.metrics.total_return)} | {_number(item.metrics.sharpe_ratio)} | "
                f"{_pct(item.metrics.maximum_drawdown)} | {item.passed} |"
                for item in validation.asset_results
            ]
        )
        lines.extend(["", "### Aggregate Metrics", "", _metrics_table(validation.aggregate_metrics), "", "### Robustness Score", "", f"- Overall score: {validation.robustness.score:.3f}"])
        lines.extend([f"- {name}: {value:.3f}" for name, value in validation.robustness.components.items()])
        lines.extend(["", "### Confidence Intervals (estimated)", "", "| Metric | Estimate | Lower | Upper | Level | Samples |", "|---|---:|---:|---:|---:|---:|"])
        lines.extend(
            [
                f"| {item.metric} | {_number(item.estimate)} | {_number(item.lower)} | {_number(item.upper)} | "
                f"{item.confidence_level:.0%} | {item.samples} |"
                for item in validation.confidence_intervals
            ] or ["| Not configured | | | | | |"]
        )
        lines.extend(["", "### Walk-Forward Results", "", "| Asset | Window | Mode | Test dates | Return | Sharpe | Max drawdown |", "|---|---:|---|---|---:|---:|---:|"])
        lines.extend(
            [
                f"| {item.asset} | {item.window_index} | {item.window_mode} | {item.test_start[:10]} to {item.test_end[:10]} | "
                f"{_pct(item.metrics.total_return)} | {_number(item.metrics.sharpe_ratio)} | {_pct(item.metrics.maximum_drawdown)} |"
                for item in validation.windows
            ] or ["| No eligible windows | | | | | |"]
        )
        lines.extend(["", "### Sensitivity Analysis", "", "| Parameter | Value | Sharpe | Return | Max drawdown | Turnover | Costs | Stability |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
        lines.extend(
            [
                f"| {item.parameter} | {item.value} | {_number(item.metrics.sharpe_ratio)} | {_pct(item.metrics.total_return)} | "
                f"{_pct(item.metrics.maximum_drawdown)} | {_number(item.metrics.turnover)} | {item.metrics.transaction_cost:.2f} | {item.stability_score:.3f} |"
                for item in validation.sensitivity
            ] or ["| Not configured | | | | | | | |"]
        )
        lines.extend(["", "### Ablation Study", "", "| Variant | Return | Sharpe | Sortino | Max drawdown | Turnover | Costs | Robustness |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
        lines.extend(
            [
                f"| {item.variant} | {_pct(item.metrics.total_return)} | {_number(item.metrics.sharpe_ratio)} | "
                f"{_number(item.metrics.sortino_ratio)} | {_pct(item.metrics.maximum_drawdown)} | {_number(item.metrics.turnover)} | "
                f"{item.metrics.transaction_cost:.2f} | {item.robustness.score:.3f} |"
                for item in validation.ablations
            ] or ["| Not configured | | | | | | | |"]
        )
        lines.extend(["", "### Benchmark Suite", "", "| Asset | Benchmark | Status | Return | Sharpe | Max drawdown |", "|---|---|---|---:|---:|---:|"])
        lines.extend(
            [
                f"| {item.asset} | {item.benchmark} | {'available' if item.available else item.unavailable_reason or 'unavailable'} | {_pct(item.metrics.total_return)} | "
                f"{_number(item.metrics.sharpe_ratio)} | {_pct(item.metrics.maximum_drawdown)} |"
                for item in validation.benchmarks
            ] or ["| Not configured | | | | |"]
        )
        return lines


def _metrics_table(metrics: MetricSnapshot) -> str:
    return "\n".join(
        [
            "| Return | Sharpe | Sortino | Max drawdown | Turnover | Transaction costs | Trades |",
            "|---:|---:|---:|---:|---:|---:|---:|",
            f"| {_pct(metrics.total_return)} | {_number(metrics.sharpe_ratio)} | {_number(metrics.sortino_ratio)} | "
            f"{_pct(metrics.maximum_drawdown)} | {_number(metrics.turnover)} | {metrics.transaction_cost:.2f} | {metrics.number_of_trades} |",
        ]
    )


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def _number(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"
