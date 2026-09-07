"""Read and controlled-workflow services over the established research engine."""

from __future__ import annotations

import subprocess
import logging
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from finagent import __version__
from finagent.api.settings import Settings
from finagent.configuration import validate_research_configuration
from finagent.data.loader import CSVDataLoader
from finagent.data.manager import DatasetManager
from finagent.data.models import MarketDataRequest, MissingDataPolicy
from finagent.data.registry import DatasetRegistry
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.database.models import ExperimentRecord
from finagent.learning.workflow import run_improvement
from finagent.live.repository import LiveMarketRepository
from finagent.live.service import LiveMarketService
from finagent.runner import load_configuration, run_experiment
from finagent.validation.workflow import run_research_validation
from finagent.validation.report import ResearchReportExporter
from finagent.utils.logging import configure_logging, log_event


class NotFoundError(LookupError):
    """A requested local research artifact is absent."""


class InvalidConfigurationError(ValueError):
    """A controlled workflow requested a config outside the permitted config directory."""


class ResearchService:
    """Maps V0.1–V0.9 records into API-safe structures and runs existing local workflows."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database = Database(settings.database_url, settings.project_root)
        self.repository = ExperimentRepository(self.database)
        self.dataset_registry = DatasetRegistry(self.database)
        self.dataset_manager = DatasetManager(self.dataset_registry, settings.data_cache_path)
        self.logger = configure_logging()
        # Live monitoring owns isolated tables and never alters historical
        # datasets, experiments, trades, or portfolio simulation state.
        self.live_repository = LiveMarketRepository(self.database)
        self.live_market = LiveMarketService(settings, self.live_repository, logger=self.logger)

    def ensure_database_ready(self) -> None:
        """Re-run idempotent schema setup at service startup before requests are accepted."""
        self.database.initialize()
        self.dataset_registry._initialize()
        self.live_repository.initialize()

    async def start_live_monitoring(self) -> None:
        await self.live_market.start()

    async def stop_live_monitoring(self) -> None:
        await self.live_market.stop()

    @staticmethod
    def _dataset_summary(dataset: Any) -> dict[str, Any]:
        return {
            "dataset_id": dataset.dataset_id, "version_id": dataset.version_id, "version_number": dataset.version_number,
            "provider": dataset.provider, "symbol": dataset.symbol, "asset_class": dataset.asset_class,
            "exchange": dataset.exchange, "interval": dataset.interval, "start_date": dataset.start_date,
            "end_date": dataset.end_date, "row_count": dataset.row_count, "checksum": dataset.checksum,
            "created_at": dataset.created_at, "last_refreshed_at": dataset.last_refreshed_at,
            "validation_status": dataset.validation.status.value, "quality_score": dataset.validation.quality.score,
        }

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
        worst: dict[str, list[dict[str, Any]]] = {}
        for regime in distribution:
            best[regime] = [item.__dict__ for item in self.repository.best_performing_strategy_by_regime(regime, limit=3)]
            worst[regime] = [item.__dict__ for item in self.repository.worst_performing_strategy_by_regime(regime, limit=3)]
        memory = self.repository.get_experiment_memory(experiment_id)
        performance = [item.to_dict() for item in memory.regime_performance] if memory else []
        return {
            "experiment_id": record.experiment_id,
            "distribution": distribution,
            "items": items,
            "best_strategies": best,
            "worst_strategies": worst,
            "strategy_performance": performance,
        }

    def agent_decisions(self, experiment_id: str, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        self._require_experiment(experiment_id)
        frame, total = self.repository.list_agent_decisions(experiment_id, limit, offset)
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
        return decisions, total

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

    def improvements(self, limit: int, offset: int, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        rows, total = self.repository.list_candidate_evaluations(limit, offset, **filters)
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

    def validations(self, limit: int, offset: int, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        records, total = self.repository.list_research_validations(limit, offset, **filters)
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
        report = self.settings.reports_path / f"{experiment_id}_research_report.md"
        if not report.is_file() and self.database.backend == "sqlite":
            report = self.settings.project_root / "data" / "demo" / "reports" / f"{experiment_id}_research_report.md"
        if not report.is_file():
            # Reports are derived from persisted evidence, so an ephemeral web
            # filesystem never makes a PostgreSQL-backed experiment unreadable.
            try:
                report = ResearchReportExporter(self.repository).export(experiment_id, report)
            except ValueError as error:
                raise NotFoundError(f"Report not found for experiment: {experiment_id}") from error
        return report

    def report(self, experiment_id: str) -> dict[str, str]:
        path = self.report_path(experiment_id)
        log_event(self.logger, "REPORT_VIEWED", artifact_id=experiment_id)
        return {"experiment_id": experiment_id, "markdown": path.read_text(encoding="utf-8"), "download_url": f"/api/reports/{experiment_id}/download"}

    def configuration(self) -> dict[str, Any]:
        config = load_configuration("config/experiments.yaml", self.settings.project_root)
        diagnostics = validate_research_configuration(config)
        return {
            "safe_defaults": {"strategy": config.get("strategy", {}), "backtest": config.get("backtest", {}), "agents": config.get("agents", {}), "regime": config.get("regime", {})},
            "capabilities": {"local_historical_simulation": True, "live_market_intelligence": self.settings.live_market_enabled, "live_trading": False, "paper_trading": False, "llm_agents": False, "reinforcement_learning": False},
            "warnings": list(diagnostics.warnings),
        }

    def live_status(self) -> dict[str, Any]:
        return self.live_market.status()

    def live_symbols(self) -> list[dict[str, object]]:
        return self.live_market.symbols()

    def live_snapshot(self, symbol: str) -> dict[str, Any]:
        try:
            return self.live_market.snapshot(symbol)
        except KeyError as error:
            raise NotFoundError(str(error)) from error

    def live_history(self, symbol: str) -> list[dict[str, object]]:
        try:
            return self.live_market.history(symbol)
        except KeyError as error:
            raise NotFoundError(str(error)) from error

    def live_signals(self, symbol: str, limit: int) -> list[dict[str, object]]:
        try:
            return self.live_market.signals(symbol, limit)
        except KeyError as error:
            raise NotFoundError(str(error)) from error

    def live_events(self, symbol: str, limit: int) -> list[dict[str, object]]:
        try:
            return self.live_market.events(symbol, limit)
        except KeyError as error:
            raise NotFoundError(str(error)) from error

    def health(self) -> dict[str, Any]:
        database = self.database.health_check()
        latest = self.repository.latest_experiment()
        return {
            "status": "ok" if database["status"] == "ok" else "degraded",
            "database_status": str(database.get("database_status", database["status"])),
            "database_backend": str(database["database_backend"]),
            "database_connectivity": bool(database["database_connectivity"]),
            "dataset_registry_status": "ok" if database["status"] == "ok" else "unavailable",
            "latest_experiment_at": latest.created_at if latest else None,
            "latest_validation_at": self.repository.latest_validation_created_at(),
        }

    def system(self) -> dict[str, Any]:
        latest = self.repository.latest_experiment()
        try:
            revision = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.settings.project_root, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            revision = None
        _, experiment_count = self.repository.list_experiments(limit=1)
        datasets, dataset_count = self.dataset_registry.list_datasets(limit=1)
        latest_dataset = datasets[0] if datasets else None
        _, warnings = self.dataset_registry.list_datasets(limit=1, status="warning")
        health = self.database.health_check()
        demo = self.database.demo_seed("default")
        return {
            "finagent_version": __version__, "database_path": str(health["path"]),
            "database_exists": self.database.backend == "postgresql" or (self.database.path is not None and self.database.path.exists()),
            "database_size_bytes": int(health["size_bytes"]), "database_backend": self.database.backend,
            "database_connectivity": bool(health["database_connectivity"]),
            "git_revision": revision, "experiment_count": experiment_count, "configuration_version_count": self.repository.count_configuration_versions(),
            "latest_experiment_id": latest.experiment_id if latest else None, "dataset_count": dataset_count,
            "latest_dataset_refresh": latest_dataset.last_refreshed_at if latest_dataset else None, "data_providers": self.dataset_manager.providers.describe(),
            "data_quality_warnings": warnings, "database_status": health["status"], "database_integrity": health.get("integrity_check"),
            "latest_experiment_at": latest.created_at if latest else None, "latest_validation_at": self.repository.latest_validation_created_at(),
            "last_successful_run": latest.created_at if latest else None, "frontend_version": __version__,
            "enabled_modules": ["V0.1 backtesting", "V0.2 regimes", "V0.3 agents", "V0.4 critique", "V0.5 controlled improvement", "V0.6 validation", "V0.8 data registry", "V0.9 operations", "V1.0 release suite", "V1.1 live market intelligence"],
            "demo_mode": demo is not None,
        }

    def data_providers(self) -> list[dict[str, object]]:
        return self.dataset_manager.providers.describe()

    def data_datasets(self, limit: int, offset: int, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        datasets, total = self.dataset_registry.list_datasets(limit, offset, **filters)
        return [self._dataset_summary(dataset) for dataset in datasets], total

    def data_dataset(self, dataset_id: str) -> dict[str, Any]:
        dataset = self.dataset_registry.latest(dataset_id)
        sample = (
            self.dataset_registry.load_ohlcv(dataset.version_id).head(50)
            if self.dataset_registry.has_ohlcv(dataset.version_id)
            else pd.read_csv(dataset.cache_path, nrows=50)
        )
        for column in sample.columns:
            sample[column] = sample[column].map(self._clean)
        payload = self._dataset_summary(dataset)
        payload.update({
            "cache_path": dataset.cache_path, "metadata": dataset.metadata.to_dict(), "validation": dataset.validation.to_dict(),
            "sample_rows": sample.to_dict(orient="records"), "versions": [self._dataset_summary(item) for item in self.dataset_registry.versions(dataset_id)],
        })
        return payload

    def _bounded_ohlcv(
        self,
        frame: pd.DataFrame,
        *,
        dataset_id: str | None,
        version_id: str | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
    ) -> dict[str, Any]:
        """Filter and deterministically downsample an existing chronological series.

        This is a presentation concern only: the stored immutable OHLCV data is
        never altered, and the returned final observation is retained.
        """
        values = frame.copy()
        values["timestamp"] = pd.to_datetime(values["timestamp"], utc=True)
        if start_date:
            values = values.loc[values["timestamp"] >= pd.Timestamp(start_date, tz="UTC")]
        if end_date:
            values = values.loc[values["timestamp"] < pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)]
        values = values.sort_values("timestamp", kind="stable")
        downsampled = len(values) > limit
        if downsampled:
            # Evenly spaced indices preserve chronology and both visual bounds.
            indexes = sorted({round(index * (len(values) - 1) / (limit - 1)) for index in range(limit)})
            values = values.iloc[indexes]
        return {
            "dataset_id": dataset_id,
            "version_id": version_id,
            "items": [
                {key: self._clean(value) for key, value in row.items()}
                for row in values.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
            ],
            "downsampled": downsampled,
        }

    def data_ohlcv(
        self,
        dataset_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1200,
    ) -> dict[str, Any]:
        """Return persisted canonical OHLCV safely bounded for terminal charts."""
        dataset = self.dataset_registry.latest(dataset_id)
        frame = (
            self.dataset_registry.load_ohlcv(dataset.version_id)
            if self.dataset_registry.has_ohlcv(dataset.version_id)
            else CSVDataLoader().load(dataset.cache_path)
        )
        return self._bounded_ohlcv(
            frame,
            dataset_id=dataset.dataset_id,
            version_id=dataset.version_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def experiment_market_data(
        self,
        experiment_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1200,
    ) -> dict[str, Any]:
        """Resolve the actual dataset used by a persisted experiment, not a proxy."""
        record = self._require_experiment(experiment_id)
        provenance = record.results.get("dataset_provenance") or {}
        experiment_config = record.configuration.get("experiment", {})
        dataset_id = provenance.get("dataset_id") or experiment_config.get("dataset_id")
        if dataset_id:
            return self.data_ohlcv(str(dataset_id), start_date=start_date, end_date=end_date, limit=limit)
        path = Path(record.dataset)
        if not path.is_absolute():
            path = self.settings.project_root / path
        path = path.resolve()
        if not path.is_relative_to(self.settings.project_root.resolve()) or not path.is_file():
            raise NotFoundError(f"Market data not available for experiment: {experiment_id}")
        return self._bounded_ohlcv(
            CSVDataLoader().load(path),
            dataset_id=None,
            version_id=None,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def activity(
        self,
        *,
        limit: int,
        offset: int,
        event_type: str | None = None,
        source: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Build a safe activity feed from persisted research evidence only.

        The feed intentionally does not expose request bodies, credentials,
        stack traces, or inferred internal reasoning.  Simulation timestamps
        remain historical market timestamps; lifecycle events use their stored
        artifact creation timestamps.
        """
        events: list[dict[str, Any]] = []
        with self.database.connect() as connection:
            datasets = connection.execute(
                "SELECT dataset_id, version_id, symbol, provider, created_at, last_refreshed_at, validation_json "
                "FROM dataset_versions ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
            experiments = connection.execute(
                "SELECT experiment_id, created_at, strategy, asset FROM experiments ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
            trades = connection.execute(
                "SELECT experiment_id, timestamp, side, price FROM trades ORDER BY id DESC LIMIT 300"
            ).fetchall()
            decisions = connection.execute(
                "SELECT experiment_id, timestamp, execution_action, risk_approved, risk_reason_code "
                "FROM agent_decisions ORDER BY id DESC LIMIT 300"
            ).fetchall()
            critiques = connection.execute(
                "SELECT experiment_id, created_at, confidence FROM critiques ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            candidates = connection.execute(
                "SELECT candidate_id, parent_version_id, created_at FROM candidate_configurations ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            promotions = connection.execute(
                "SELECT candidate_id, parent_version_id, created_at, status, reason_codes_json FROM candidate_evaluations "
                "ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            validations = connection.execute(
                "SELECT validation_id, experiment_id, created_at FROM research_validations ORDER BY created_at DESC LIMIT 100"
            ).fetchall()

        for item in datasets:
            metadata = {"dataset_id": item["dataset_id"], "version_id": item["version_id"], "provider": item["provider"]}
            events.append({"timestamp": item["created_at"], "event_type": "DATA_FETCH", "source": "dataset_registry", "artifact_id": item["dataset_id"], "summary": f"{item['symbol']} historical dataset registered", "metadata": metadata})
            validation = json.loads(item["validation_json"])
            events.append({"timestamp": item["last_refreshed_at"], "event_type": "DATA_VALIDATED", "source": "data_quality", "artifact_id": item["dataset_id"], "summary": f"{item['symbol']} validation: {validation.get('status', 'unknown')}", "metadata": {**metadata, "quality_score": validation.get("quality", {}).get("score")}})
        for item in experiments:
            events.append({"timestamp": item["created_at"], "event_type": "EXPERIMENT_COMPLETED", "source": "runner", "artifact_id": item["experiment_id"], "summary": f"{item['strategy']} simulation completed for {item['asset']}", "metadata": {"strategy": item["strategy"], "asset": item["asset"]}})
        for item in trades:
            events.append({"timestamp": item["timestamp"], "event_type": "TRADE_SIMULATED", "source": "backtester", "artifact_id": item["experiment_id"], "summary": f"{item['side']} simulated at {float(item['price']):.2f}", "metadata": {"side": item["side"], "price": float(item["price"])}})
        for item in decisions:
            metadata = {"action": item["execution_action"], "risk_reason_code": item["risk_reason_code"]}
            events.append({"timestamp": item["timestamp"], "event_type": "SIGNAL_CREATED", "source": "agent_decision_system", "artifact_id": item["experiment_id"], "summary": f"Agent execution action: {item['execution_action']}", "metadata": metadata})
            if not bool(item["risk_approved"]):
                events.append({"timestamp": item["timestamp"], "event_type": "RISK_REJECTED", "source": "risk_agent", "artifact_id": item["experiment_id"], "summary": f"Risk proposal rejected: {item['risk_reason_code']}", "metadata": metadata})
        for item in critiques:
            events.append({"timestamp": item["created_at"], "event_type": "CRITIQUE_GENERATED", "source": "critic_agent", "artifact_id": item["experiment_id"], "summary": f"Deterministic critique generated (confidence {float(item['confidence']):.2f})", "metadata": {"confidence": float(item["confidence"])}})
        for item in candidates:
            events.append({"timestamp": item["created_at"], "event_type": "CANDIDATE_CREATED", "source": "learning_workflow", "artifact_id": item["candidate_id"], "summary": f"Candidate created from {item['parent_version_id']}", "metadata": {"parent_version_id": item["parent_version_id"]}})
        for item in promotions:
            status = str(item["status"])
            event = "CANDIDATE_PROMOTED" if status == "PROMOTED" else "CANDIDATE_REJECTED"
            events.append({"timestamp": item["created_at"], "event_type": event, "source": "promotion_gate", "artifact_id": item["candidate_id"], "summary": f"Candidate {status.lower()} by the deterministic promotion gate", "metadata": {"parent_version_id": item["parent_version_id"], "reason_codes": json.loads(item["reason_codes_json"])}})
        for item in validations:
            events.append({"timestamp": item["created_at"], "event_type": "VALIDATION_COMPLETED", "source": "validation_workflow", "artifact_id": item["validation_id"], "summary": f"Research validation completed for {item['experiment_id']}", "metadata": {"experiment_id": item["experiment_id"]}})

        needle = search.lower().strip() if search else None
        filtered = [
            item for item in events
            if (not event_type or item["event_type"] == event_type)
            and (not source or item["source"] == source)
            and (not needle or needle in " ".join([item["event_type"], item["source"], item["artifact_id"] or "", item["summary"]]).lower())
        ]
        filtered.sort(key=lambda item: str(item["timestamp"]), reverse=True)
        return filtered[offset:offset + limit], len(filtered)

    def fetch_data(self, raw: dict[str, Any]) -> dict[str, Any]:
        source_path = raw.get("source_path")
        if source_path:
            candidate = Path(str(source_path)).expanduser()
            if not candidate.is_absolute():
                candidate = self.settings.project_root / candidate
            candidate = candidate.resolve()
            if not candidate.is_relative_to(self.settings.project_root.resolve()):
                raise InvalidConfigurationError("source_path must remain within the local FinAgent project directory")
            raw["source_path"] = str(candidate)
        request = MarketDataRequest(
            symbol=str(raw["symbol"]), start_date=str(raw["start_date"]), end_date=str(raw["end_date"]),
            interval=str(raw.get("interval", "1d")), force_refresh=bool(raw.get("force_refresh", False)),
            source_path=str(raw["source_path"]) if raw.get("source_path") else None,
            asset_class=str(raw.get("asset_class", "equity")),
        )
        result = self.dataset_manager.fetch(str(raw.get("provider", "auto")), request, MissingDataPolicy(str(raw.get("missing_data_policy", "reject"))))
        log_event(
            self.logger,
            "DATA_FETCHED",
            artifact_id=result.dataset.dataset_id,
            workflow="data_fetch",
            requested_provider=result.requested_provider,
            actual_provider=result.actual_provider,
            fallback_used=result.fallback_used,
            cache_hit=result.cache_hit,
        )
        return {
            "dataset": self._dataset_summary(result.dataset),
            "cache_hit": result.cache_hit,
            "requested_provider": result.requested_provider,
            "actual_provider": result.actual_provider,
            "fallback_used": result.fallback_used,
            "attempts": list(result.attempts),
        }

    def validate_data(self, dataset_id: str, policy: str) -> dict[str, Any]:
        dataset = self.dataset_manager.validate(dataset_id, MissingDataPolicy(policy))
        log_event(self.logger, "DATASET_VALIDATED", artifact_id=dataset_id, workflow="data_validation")
        return self._dataset_summary(dataset)

    def data_collections(self, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return [item.to_dict() for item in self.dataset_registry.list_collections(limit, offset)], self.dataset_registry.collection_count()

    def _config_path(self, requested: str) -> str:
        """Accept only an existing local YAML mapping from the repository config directory."""
        config_root = (self.settings.project_root / "config").resolve()
        path = (self.settings.project_root / requested).resolve()
        if path.suffix not in {".yaml", ".yml"} or not path.is_relative_to(config_root) or not path.is_file():
            raise InvalidConfigurationError("config_path must reference an existing YAML file within config/")
        try:
            with path.open(encoding="utf-8") as handle:
                content = yaml.safe_load(handle)
        except yaml.YAMLError as error:
            raise InvalidConfigurationError(f"config_path contains invalid YAML: {error}") from error
        if not isinstance(content, Mapping):
            raise InvalidConfigurationError("config_path must contain a YAML mapping")
        return str(path)

    def run_experiment(self, config_path: str, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        path = self._config_path(config_path)
        configuration = load_configuration(path, self.settings.project_root)
        if not isinstance(configuration.get("experiment"), Mapping) or not isinstance(configuration.get("strategy"), Mapping):
            raise InvalidConfigurationError("experiment configuration requires experiment and strategy mappings")
        raw = dict(request or {})
        dataset_id = raw.get("dataset_id")
        start_date, end_date = raw.get("start_date"), raw.get("end_date")
        if start_date and end_date and str(start_date) > str(end_date):
            raise InvalidConfigurationError("start_date must be on or before end_date")
        overrides: dict[str, Any] = {}
        experiment_overrides = {key: raw[key] for key in ("dataset_id", "starting_capital", "start_date", "end_date") if key in raw}
        strategy_overrides: dict[str, Any] = {}
        if raw.get("strategy_name"):
            selected_strategy = str(raw["strategy_name"])
            # Each baseline constructor has a different parameter contract.
            # Reuse the already validated default allowlist rather than carry
            # momentum parameters into a moving-average or mean-reversion run.
            available = configuration.get("agents", {}).get("strategy", {}).get("available_strategies", {})
            strategy_overrides = {"name": selected_strategy, "parameters": dict(available.get(selected_strategy, {}))}
        backtest_values = {key: raw[key] for key in ("position_fraction",) if key in raw}
        cost_values = {key: raw[key] for key in ("percentage_fee", "fixed_fee") if key in raw}
        if cost_values:
            backtest_values["transaction_costs"] = cost_values
        agent_values: dict[str, Any] = {}
        if "agents_enabled" in raw:
            agent_values["enabled"] = raw["agents_enabled"]
        risk_values = {
            "max_position_size": raw.get("risk_max_position_size"),
            "max_drawdown": raw.get("risk_max_drawdown"),
            "max_volatility": raw.get("risk_max_volatility"),
        }
        risk_values = {key: value for key, value in risk_values.items() if value is not None}
        if risk_values:
            agent_values["risk"] = risk_values
        if experiment_overrides:
            overrides["experiment"] = experiment_overrides
        if strategy_overrides:
            overrides["strategy"] = strategy_overrides
        if backtest_values:
            overrides["backtest"] = backtest_values
        if agent_values:
            overrides["agents"] = agent_values
        log_event(self.logger, "EXPERIMENT_RUN_STARTED", workflow="experiment")
        if dataset_id:
            self.dataset_registry.latest(dataset_id)
        experiment_id, result = run_experiment(
            path,
            self.settings.project_root,
            self.logger,
            database_url=self.settings.database_url,
            configuration_overrides=overrides or None,
        )
        log_event(self.logger, "EXPERIMENT_RUN_COMPLETED", workflow="experiment", artifact_id=experiment_id)
        return {"workflow": "experiment", "status": "completed", "experiment_id": experiment_id, "run_id": None, "validation_id": None, "metadata": {"trade_count": result["metrics"].get("number_of_trades"), "critic_enabled": result.get("critique", {}).get("enabled", False), "dataset_id": dataset_id}}

    def run_improvement(self, config_path: str) -> dict[str, Any]:
        log_event(self.logger, "IMPROVEMENT_RUN_STARTED", workflow="improvement")
        result = run_improvement(self._config_path(config_path), self.settings.project_root, self.logger, database_url=self.settings.database_url)
        if result is None:
            return {"workflow": "improvement", "status": "disabled", "experiment_id": None, "run_id": None, "validation_id": None, "metadata": {"reason": "learning.enabled is false"}}
        latest = result.decisions[-1] if result.decisions else None
        response = {"workflow": "improvement", "status": "completed", "experiment_id": None, "run_id": latest.candidate_id if latest else None, "validation_id": None, "metadata": {"candidate_count": len(result.candidates), "promoted_version": result.promoted_version.version_id if result.promoted_version else None}}
        log_event(self.logger, "IMPROVEMENT_RUN_COMPLETED", workflow="improvement", artifact_id=response["run_id"])
        return response

    def run_validation(self, config_path: str) -> dict[str, Any]:
        log_event(self.logger, "VALIDATION_RUN_STARTED", workflow="validation")
        result = run_research_validation(self._config_path(config_path), self.settings.project_root, self.logger, database_url=self.settings.database_url)
        if result is None:
            return {"workflow": "validation", "status": "disabled", "experiment_id": None, "run_id": None, "validation_id": None, "metadata": {"reason": "validation.enabled is false"}}
        response = {"workflow": "validation", "status": "completed", "experiment_id": result.experiment_id, "run_id": None, "validation_id": result.validation_id, "metadata": {"asset_count": len(result.asset_results), "robustness_score": result.robustness.score}}
        log_event(self.logger, "VALIDATION_RUN_COMPLETED", workflow="validation", artifact_id=result.validation_id)
        return response
