"""Read and controlled-workflow services over the established research engine."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from finagent import __version__
from finagent.api.settings import Settings
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.database.models import ExperimentRecord
from finagent.learning.workflow import run_improvement
from finagent.runner import load_configuration, run_experiment
from finagent.validation.workflow import run_research_validation


class NotFoundError(LookupError):
    """A requested local research artifact is absent."""


class InvalidConfigurationError(ValueError):
    """A controlled workflow requested a config outside the permitted config directory."""


class ResearchService:
    """Maps persisted V0.1–V0.6 records into API-safe structures and runs existing workflows."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = ExperimentRepository(Database(settings.database_path))

    @staticmethod
    def _clean(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, float) and pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return value.item() if hasattr(value, "item") else value

    def _experiment_summary(self, record: ExperimentRecord) -> dict[str, Any]:
        metrics = record.results.get("metrics", {})
        return {
            "experiment_id": record.experiment_id,
            "created_at": record.created_at,
            "strategy": record.strategy,
            "asset": record.asset,
            "start_date": record.start_date,
            "end_date": record.end_date,
            "total_return": self._clean(metrics.get("total_return")),
            "sharpe_ratio": self._clean(metrics.get("sharpe_ratio")),
            "maximum_drawdown": self._clean(metrics.get("maximum_drawdown")),
            "number_of_trades": self._clean(metrics.get("number_of_trades")),
        }

    def _require_experiment(self, experiment_id: str) -> ExperimentRecord:
        record = self.repository.get_experiment(experiment_id)
        if record is None:
            raise NotFoundError(f"Experiment not found: {experiment_id}")
        return record

    def list_experiments(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        records, total = self.repository.list_experiments(**filters)
        return [self._experiment_summary(record) for record in records], total

    def experiment_detail(self, experiment_id: str) -> dict[str, Any]:
        record = self._require_experiment(experiment_id)
        result = record.results
        payload = self._experiment_summary(record)
        payload.update(
            {
                "dataset": record.dataset,
                "starting_capital": record.starting_capital,
                "random_seed": record.random_seed,
                "metrics": result.get("metrics", {}),
                "benchmark_metrics": result.get("benchmark_metrics", {}),
                "regime": result.get("regime", {}),
                "agents": result.get("agents", {}),
                "final_portfolio": result.get("final_portfolio", {}),
                "equity_curve": result.get("equity_curve", []),
                "benchmark_curve": result.get("benchmark_curve", []),
                "manifest": result.get("manifest"),
            }
        )
        return payload

    def trades(self, experiment_id: str) -> list[dict[str, Any]]:
        self._require_experiment(experiment_id)
        frame = self.repository.get_trades(experiment_id)
        return [{key: self._clean(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]

    def regimes(self, experiment_id: str) -> dict[str, Any]:
        record = self._require_experiment(experiment_id)
        frame = self.repository.get_regime_observations(experiment_id)
        items = [{key: self._clean(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]
        distribution = {str(key): int(value) for key, value in frame["regime"].value_counts().items()} if not frame.empty else {}
        best: dict[str, list[dict[str, Any]]] = {}
        for regime in distribution:
            best[regime] = [item.__dict__ for item in self.repository.best_performing_strategy_by_regime(regime, limit=3)]
        return {"experiment_id": record.experiment_id, "distribution": distribution, "items": items, "best_strategies": best}

    def agent_decisions(self, experiment_id: str) -> list[dict[str, Any]]:
        self._require_experiment(experiment_id)
        frame = self.repository.get_agent_decisions(experiment_id)
        decisions = []
        for row in frame.to_dict(orient="records"):
            decisions.append(
                {
                    "timestamp": self._clean(row["timestamp"]),
                    "technical": {
                        "trend": row["technical_trend"], "momentum": row["technical_momentum"],
                        "volatility": row["technical_volatility"], "rsi": row["technical_rsi"],
                        "signal_strength": self._clean(row["technical_signal_strength"]), "confidence": self._clean(row["technical_confidence"]),
                    },
                    "regime": {"regime": row["regime"], "confidence": self._clean(row["regime_confidence"])},
                    "proposal": {
                        "selected_strategy": row["selected_strategy"], "action": row["action"],
                        "confidence": self._clean(row["proposal_confidence"]),
                        "requested_position_size": self._clean(row["requested_position_size"]),
                        "reason_codes": list(row["strategy_reason_codes"]),
                    },
                    "risk": {"approved": bool(row["risk_approved"]), "adjusted_position_size": self._clean(row["adjusted_position_size"]), "reason_code": row["risk_reason_code"]},
                    "execution_action": row["execution_action"],
                }
            )
        return decisions

    def critique(self, experiment_id: str) -> dict[str, Any]:
        self._require_experiment(experiment_id)
        critique = self.repository.get_critique(experiment_id)
        if critique is None:
            raise NotFoundError(f"Critique not found for experiment: {experiment_id}")
        return critique.to_dict()

    def versions(self) -> list[dict[str, Any]]:
        return [
            {
                "version_id": item.version_id, "parent_version_id": item.parent_version_id, "candidate_id": item.candidate_id,
                "created_at": item.created_at, "status": item.status.value,
                "reason_codes": [code.value for code in item.reason_codes],
                "validation_metrics": item.validation_metrics.to_dict() if item.validation_metrics else None,
            }
            for item in self.repository.configuration_version_history()
        ]

    def version(self, version_id: str) -> dict[str, Any]:
        version = self.repository.get_configuration_version(version_id)
        if version is None:
            raise NotFoundError(f"Configuration version not found: {version_id}")
        return {**version.to_dict(), "status": version.status.value, "reason_codes": [code.value for code in version.reason_codes]}

    @staticmethod
    def _improvement(decision: Any, parameter_changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "run_id": decision.candidate_id, "parent_version_id": decision.parent_version_id, "status": decision.status.value,
            "reason_codes": [code.value for code in decision.reason_codes], "parent_metrics": decision.parent_metrics.to_dict(),
            "candidate_metrics": decision.candidate_metrics.to_dict(), "window_pass_rate": decision.window_pass_rate,
            "parameter_changes": parameter_changes or [],
        }

    def improvements(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        rows, total = self.repository.list_candidate_evaluations(limit, offset)
        return [
            self._improvement(
                row,
                [item.to_dict() for item in candidate.parameter_changes]
                if (candidate := self.repository.get_candidate_configuration(row.candidate_id)) else [],
            )
            for row in rows
        ], total

    def improvement(self, run_id: str) -> dict[str, Any]:
        decision = self.repository.get_candidate_evaluation(run_id)
        if decision is None:
            raise NotFoundError(f"Improvement run not found: {run_id}")
        candidate = self.repository.get_candidate_configuration(run_id)
        payload = self._improvement(decision, [item.to_dict() for item in candidate.parameter_changes] if candidate else [])
        payload["windows"] = [item.to_dict() for item in self.repository.get_validation_windows(run_id)]
        return payload

    @staticmethod
    def _validation_summary(validation: Any) -> dict[str, Any]:
        return {
            "validation_id": validation.validation_id, "experiment_id": validation.experiment_id,
            "robustness_score": validation.robustness.score, "leakage_passed": validation.leakage.passed,
            "asset_count": len(validation.asset_results), "window_count": len(validation.windows),
        }

    def validations(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        records, total = self.repository.list_research_validations(limit, offset)
        return [self._validation_summary(record) for record in records], total

    def validation_for_experiment(self, experiment_id: str) -> dict[str, Any]:
        self._require_experiment(experiment_id)
        validation = self.repository.latest_research_validation(experiment_id)
        if validation is None:
            raise NotFoundError(f"Validation not found for experiment: {experiment_id}")
        payload = validation.to_dict()
        return {
            "validation_id": payload["validation_id"], "experiment_id": payload["experiment_id"],
            "aggregate_metrics": payload["aggregate_metrics"], "robustness": payload["robustness"], "leakage": payload["leakage"],
            "confidence_intervals": payload["confidence_intervals"], "asset_results": payload["asset_results"],
            "windows": payload["windows"], "sensitivity": payload["sensitivity"], "ablations": payload["ablations"], "benchmarks": payload["benchmarks"],
        }

    def report_path(self, experiment_id: str) -> Path:
        self._require_experiment(experiment_id)
        report = self.settings.project_root / "reports" / f"{experiment_id}_research_report.md"
        if not report.is_file():
            raise NotFoundError(f"Report not found for experiment: {experiment_id}")
        return report

    def report(self, experiment_id: str) -> dict[str, str]:
        return {"experiment_id": experiment_id, "markdown": self.report_path(experiment_id).read_text(encoding="utf-8"), "download_url": f"/api/reports/{experiment_id}/download"}

    def configuration(self) -> dict[str, Any]:
        config = load_configuration("config/experiments.yaml", self.settings.project_root)
        return {
            "safe_defaults": {"strategy": config.get("strategy", {}), "backtest": config.get("backtest", {}), "agents": config.get("agents", {}), "regime": config.get("regime", {})},
            "capabilities": {"local_historical_simulation": True, "live_trading": False, "paper_trading": False, "llm_agents": False, "reinforcement_learning": False},
        }

    def system(self) -> dict[str, Any]:
        latest = self.repository.latest_experiment()
        try:
            revision = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.settings.project_root, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            revision = None
        _, experiment_count = self.repository.list_experiments(limit=1)
        path = self.settings.database_path
        return {"finagent_version": __version__, "database_path": str(path), "database_exists": path.exists(), "database_size_bytes": path.stat().st_size if path.exists() else 0, "git_revision": revision, "experiment_count": experiment_count, "configuration_version_count": self.repository.count_configuration_versions(), "latest_experiment_id": latest.experiment_id if latest else None}

    def _config_path(self, requested: str) -> str:
        config_root = (self.settings.project_root / "config").resolve()
        path = (self.settings.project_root / requested).resolve()
        if path.suffix not in {".yaml", ".yml"} or not path.is_relative_to(config_root) or not path.is_file():
            raise InvalidConfigurationError("config_path must reference an existing YAML file within config/")
        return str(path)

    def run_experiment(self, config_path: str) -> dict[str, Any]:
        path = self._config_path(config_path)
        experiment_id, result = run_experiment(path, self.settings.project_root)
        return {"workflow": "experiment", "status": "completed", "experiment_id": experiment_id, "run_id": None, "validation_id": None, "metadata": {"trade_count": result["metrics"].get("number_of_trades"), "critic_enabled": result.get("critique", {}).get("enabled", False)}}

    def run_improvement(self, config_path: str) -> dict[str, Any]:
        result = run_improvement(self._config_path(config_path), self.settings.project_root)
        if result is None:
            return {"workflow": "improvement", "status": "disabled", "experiment_id": None, "run_id": None, "validation_id": None, "metadata": {"reason": "learning.enabled is false"}}
        latest = result.decisions[-1] if result.decisions else None
        return {"workflow": "improvement", "status": "completed", "experiment_id": None, "run_id": latest.candidate_id if latest else None, "validation_id": None, "metadata": {"candidate_count": len(result.candidates), "promoted_version": result.promoted_version.version_id if result.promoted_version else None}}

    def run_validation(self, config_path: str) -> dict[str, Any]:
        result = run_research_validation(self._config_path(config_path), self.settings.project_root)
        if result is None:
            return {"workflow": "validation", "status": "disabled", "experiment_id": None, "run_id": None, "validation_id": None, "metadata": {"reason": "validation.enabled is false"}}
        return {"workflow": "validation", "status": "completed", "experiment_id": result.experiment_id, "run_id": None, "validation_id": result.validation_id, "metadata": {"asset_count": len(result.asset_results), "robustness_score": result.robustness.score}}
