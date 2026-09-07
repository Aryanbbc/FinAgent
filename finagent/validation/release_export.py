"""Portable table and chart exports for a persisted FinAgent release validation."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from statistics import fmean
from typing import Any

from finagent.database.experiment_repository import ExperimentRepository
from finagent.validation.report import ResearchReportExporter


class ReleaseArtifactExporter:
    """Export existing validation evidence; this class performs no simulation."""

    def __init__(self, repository: ExperimentRepository) -> None:
        self.repository = repository

    def export(self, experiment_id: str, output_directory: str | Path) -> dict[str, Path]:
        validation = self.repository.latest_research_validation(experiment_id)
        if validation is None:
            raise ValueError(f"No research validation is attached to experiment: {experiment_id}")
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, Path] = {}
        artifacts["research_report"] = ResearchReportExporter(self.repository).export(
            experiment_id, output / "research_report.md"
        )
        artifacts["experiment_metrics"] = _write_rows(
            output / "experiment_metrics.csv",
            [{"metric": key, "value": value} for key, value in validation.aggregate_metrics.to_dict().items()],
        )
        artifacts["multi_asset"] = _write_rows(
            output / "multi_asset.csv",
            [
                {
                    "asset": item.asset,
                    "dataset": item.dataset,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "passed": item.passed,
                    **_prefixed("strategy_", item.metrics.to_dict()),
                    **_prefixed("buy_and_hold_", item.benchmark_metrics.to_dict()),
                    "regime_distribution": json.dumps(item.regime_distribution, sort_keys=True),
                    "agent_observations": item.agent_observations,
                }
                for item in validation.asset_results
            ],
        )
        artifacts["walk_forward"] = _write_rows(
            output / "walk_forward.csv",
            [
                {
                    "asset": item.asset,
                    "window_index": item.window_index,
                    "window_mode": item.window_mode,
                    "train_start": item.train_start,
                    "train_end": item.train_end,
                    "test_start": item.test_start,
                    "test_end": item.test_end,
                    "train_observations": item.train_observations,
                    "test_observations": item.test_observations,
                    **item.metrics.to_dict(),
                }
                for item in validation.windows
            ],
        )
        artifacts["sensitivity"] = _write_rows(
            output / "sensitivity.csv",
            [
                {"parameter": item.parameter, "value": item.value, "stability_score": item.stability_score, **item.metrics.to_dict()}
                for item in validation.sensitivity
            ],
        )
        artifacts["confidence_intervals"] = _write_rows(
            output / "confidence_intervals.csv", [item.to_dict() for item in validation.confidence_intervals]
        )
        artifacts["ablations"] = _write_rows(
            output / "ablations.csv",
            [
                {
                    "variant": item.variant,
                    "enabled_components": ",".join(item.enabled_components),
                    "robustness_score": item.robustness.score,
                    **item.metrics.to_dict(),
                }
                for item in validation.ablations
            ],
        )
        benchmark_rows = [
            {
                "asset": item.asset,
                "benchmark": item.benchmark,
                "available": item.available,
                "unavailable_reason": item.unavailable_reason or "",
                **item.metrics.to_dict(),
            }
            for item in validation.benchmarks
        ]
        artifacts["benchmarks"] = _write_rows(output / "benchmarks.csv", benchmark_rows)
        artifacts["benchmark_chart"] = _write_benchmark_chart(output / "benchmark_total_returns.svg", benchmark_rows)
        artifacts["validation_record"] = output / "validation_record.json"
        artifacts["validation_record"].write_text(
            json.dumps(validation.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
        return artifacts


def _prefixed(prefix: str, values: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}{key}": value for key, value in values.items()}


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> Path:
    fields = list(dict.fromkeys(field for row in rows for field in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_benchmark_chart(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write a dependency-free SVG bar chart of cross-asset total returns."""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        value = row.get("total_return")
        if row.get("available") and isinstance(value, (int, float)):
            grouped.setdefault(str(row["benchmark"]), []).append(float(value))
    labels = list(grouped)
    values = [fmean(grouped[label]) for label in labels]
    width, height, baseline = max(720, 110 * max(1, len(labels))), 360, 185
    scale = 130 / max(max((abs(value) for value in values), default=0.01), 0.01)
    bar_width = max(34, min(82, (width - 100) // max(1, len(labels)) - 16))
    bars = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s" role="img" aria-label="Cross-asset benchmark total returns">'
        % (width, height, width, height),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="30" y="34" font-family="Arial, sans-serif" font-size="18" font-weight="700">FinAgent V1.0 benchmark total returns</text>',
        f'<line x1="40" x2="{width - 24}" y1="{baseline}" y2="{baseline}" stroke="#475569" stroke-width="1"/>',
    ]
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        x = 52 + index * ((width - 90) / max(1, len(labels)))
        bar_height = abs(value) * scale
        y = baseline - bar_height if value >= 0 else baseline
        colour = "#0f766e" if value >= 0 else "#b91c1c"
        escaped = html.escape(label.replace("_", " "))
        bars.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width}" height="{bar_height:.1f}" fill="{colour}" rx="2"/>',
                f'<text x="{x + bar_width / 2:.1f}" y="{y - 7 if value >= 0 else y + bar_height + 16:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11">{value:.2%}</text>',
                f'<text x="{x + bar_width / 2:.1f}" y="{height - 24}" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" transform="rotate(-28 {x + bar_width / 2:.1f} {height - 24})">{escaped}</text>',
            ]
        )
    bars.append('<text x="30" y="330" font-family="Arial, sans-serif" font-size="11" fill="#475569">Equal-weight average across the configured bundled assets. Historical simulation only.</text>')
    bars.append("</svg>")
    path.write_text("\n".join(bars) + "\n", encoding="utf-8")
    return path
