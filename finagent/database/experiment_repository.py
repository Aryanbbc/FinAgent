"""Persistence and retrieval of experiments, trades, and metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from finagent.critique.models import ExperimentCritique
from finagent.database.db import Database
from finagent.database.models import ExperimentRecord
from finagent.memory.models import ExperimentMemoryRecord, MemoryQueryResult
from finagent.validation.models import ReproducibilityManifest, ResearchValidationResult
from finagent.learning.models import (
    CandidateProposal,
    ConfigurationVersion,
    PromotionDecision,
    PromotionStatus,
    WalkForwardEvaluation,
    WalkForwardWindow,
)
from finagent.utils.ids import format_experiment_id


class ExperimentRepository:
    """A small repository layer that keeps database concerns out of the runner."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def next_experiment_id(self) -> str:
        with self.database.connect() as connection:
            return self._next_experiment_id(connection)

    @staticmethod
    def _next_experiment_id(connection: Any) -> str:
        row = connection.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(experiment_id, 5) AS INTEGER)), 0) AS last_number FROM experiments"
        ).fetchone()
        return format_experiment_id(int(row["last_number"]) + 1)

    def save_experiment(
        self,
        *,
        strategy: str,
        asset: str,
        dataset: str,
        start_date: str,
        end_date: str,
        starting_capital: float,
        random_seed: int | None,
        configuration: Mapping[str, Any],
        results: Mapping[str, Any],
        metrics: Mapping[str, float | int | None],
        trades: pd.DataFrame,
        regime_observations: pd.DataFrame | None = None,
        agent_decisions: pd.DataFrame | None = None,
    ) -> str:
        """Atomically save a complete reproducible experiment and return its ID."""
        created_at = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            if self.database.backend == "postgresql":
                # IDs retain their established EXP-000001 format while the
                # table lock prevents concurrent production writers colliding.
                connection.execute("LOCK TABLE experiments IN EXCLUSIVE MODE")
            experiment_id = self._next_experiment_id(connection)
            connection.execute(
                """
                INSERT INTO experiments (
                    experiment_id, created_at, strategy, asset, dataset, start_date, end_date,
                    starting_capital, random_seed, configuration_json, results_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    created_at,
                    strategy,
                    asset,
                    dataset,
                    start_date,
                    end_date,
                    starting_capital,
                    random_seed,
                    json.dumps(configuration, default=str),
                    json.dumps(results, default=str),
                ),
            )
            trade_rows = []
            for trade in trades.to_dict(orient="records"):
                trade_rows.append(
                    (
                        experiment_id,
                        str(trade["timestamp"]),
                        trade["side"],
                        float(trade["price"]),
                        float(trade["quantity"]),
                        float(trade["transaction_cost"]),
                        float(trade["portfolio_value"]),
                        self._optional_float(trade.get("realized_pnl")),
                        self._optional_float(trade.get("trade_return")),
                    )
                )
            connection.executemany(
                """
                INSERT INTO trades (
                    experiment_id, timestamp, side, price, quantity, transaction_cost,
                    portfolio_value, realized_pnl, trade_return
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                trade_rows,
            )
            connection.executemany(
                "INSERT INTO metrics (experiment_id, name, value) VALUES (?, ?, ?)",
                [(experiment_id, name, self._optional_float(value)) for name, value in metrics.items()],
            )
            if regime_observations is not None and not regime_observations.empty:
                observation_rows = [
                    (
                        experiment_id,
                        str(observation["timestamp"]),
                        observation["regime"],
                        float(observation["confidence"]),
                        self._optional_float(observation.get("rolling_return")),
                        self._optional_float(observation.get("rolling_volatility")),
                        self._optional_float(observation.get("moving_average_slope")),
                        self._optional_float(observation.get("momentum")),
                        self._optional_float(observation.get("drawdown")),
                    )
                    for observation in regime_observations.to_dict(orient="records")
                ]
                connection.executemany(
                    """
                    INSERT INTO regime_observations (
                        experiment_id, timestamp, regime, confidence, rolling_return, rolling_volatility,
                        moving_average_slope, momentum, drawdown
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    observation_rows,
                )
            if agent_decisions is not None and not agent_decisions.empty:
                decision_rows = [
                    (
                        experiment_id,
                        str(decision["timestamp"]),
                        decision["technical_trend"],
                        decision["technical_momentum"],
                        decision["technical_volatility"],
                        decision["technical_rsi"],
                        float(decision["technical_signal_strength"]),
                        float(decision["technical_confidence"]),
                        decision["regime"],
                        float(decision["regime_confidence"]),
                        decision["selected_strategy"],
                        decision["action"],
                        decision["execution_action"],
                        float(decision["proposal_confidence"]),
                        float(decision["requested_position_size"]),
                        json.dumps(decision["strategy_reason_codes"]),
                        int(bool(decision["risk_approved"])),
                        float(decision["adjusted_position_size"]),
                        decision["risk_reason_code"],
                    )
                    for decision in agent_decisions.to_dict(orient="records")
                ]
                connection.executemany(
                    """
                    INSERT INTO agent_decisions (
                        experiment_id, timestamp, technical_trend, technical_momentum, technical_volatility,
                        technical_rsi, technical_signal_strength, technical_confidence, regime, regime_confidence,
                        selected_strategy, action, execution_action, proposal_confidence, requested_position_size,
                        strategy_reason_codes_json, risk_approved, adjusted_position_size, risk_reason_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    decision_rows,
                )
        return experiment_id

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        return self._to_record(row) if row else None

    def latest_experiment(self) -> ExperimentRecord | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM experiments ORDER BY created_at DESC LIMIT 1").fetchone()
        return self._to_record(row) if row else None

    def list_experiments(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
        strategy: str | None = None,
        asset: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        regime: str | None = None,
        status: str | None = None,
        version: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[ExperimentRecord], int]:
        """Return filtered experiment records and a total count for paginated local clients."""
        clauses: list[str] = []
        parameters: list[Any] = []
        if search:
            clauses.append("(experiment_id LIKE ? OR strategy LIKE ? OR asset LIKE ?)")
            needle = f"%{search}%"
            parameters.extend([needle, needle, needle])
        if strategy:
            clauses.append("strategy = ?")
            parameters.append(strategy)
        if asset:
            clauses.append("asset = ?")
            parameters.append(asset)
        if start_date:
            clauses.append("end_date >= ?")
            parameters.append(start_date)
        if end_date:
            clauses.append("start_date <= ?")
            parameters.append(end_date)
        if regime:
            clauses.append("EXISTS (SELECT 1 FROM regime_observations AS regime_filter WHERE regime_filter.experiment_id = experiments.experiment_id AND regime_filter.regime = ?)")
            parameters.append(regime)
        if status == "validated":
            clauses.append("EXISTS (SELECT 1 FROM research_validations AS validation_filter WHERE validation_filter.experiment_id = experiments.experiment_id)")
        elif status == "unvalidated":
            clauses.append("NOT EXISTS (SELECT 1 FROM research_validations AS validation_filter WHERE validation_filter.experiment_id = experiments.experiment_id)")
        elif status == "critiqued":
            clauses.append("EXISTS (SELECT 1 FROM critiques AS critique_filter WHERE critique_filter.experiment_id = experiments.experiment_id)")
        elif status == "without_critique":
            clauses.append("NOT EXISTS (SELECT 1 FROM critiques AS critique_filter WHERE critique_filter.experiment_id = experiments.experiment_id)")
        if version:
            clauses.append("configuration_json LIKE ?")
            parameters.append(f"%{version}%")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sort_columns = {
            "created_at": "created_at",
            "total_return": self.database.json_number("results_json", ("metrics", "total_return")),
            "sharpe_ratio": self.database.json_number("results_json", ("metrics", "sharpe_ratio")),
            "maximum_drawdown": self.database.json_number("results_json", ("metrics", "maximum_drawdown")),
            "start_date": "start_date",
        }
        order_column = sort_columns.get(sort_by, "created_at")
        direction = "ASC" if sort_order.lower() == "asc" else "DESC"
        with self.database.connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) AS count FROM experiments{where}", parameters).fetchone()["count"]
            rows = connection.execute(
                f"SELECT * FROM experiments{where} ORDER BY {order_column} {direction}, experiment_id DESC LIMIT ? OFFSET ?", [*parameters, limit, offset]
            ).fetchall()
        return [self._to_record(row) for row in rows], int(total)

    def latest_experiment_memory(self) -> ExperimentMemoryRecord | None:
        """Return the newest completed V0.4 memory record for an opt-in learning run."""
        with self.database.connect() as connection:
            row = connection.execute("SELECT experiment_id FROM experiment_memory ORDER BY created_at DESC LIMIT 1").fetchone()
        return self.get_experiment_memory(row["experiment_id"]) if row else None

    def get_trades(self, experiment_id: str) -> pd.DataFrame:
        return self.database.fetch_dataframe(
            "SELECT timestamp, side, price, quantity, transaction_cost, portfolio_value, realized_pnl, trade_return "
            "FROM trades WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        )

    def get_regime_observations(self, experiment_id: str) -> pd.DataFrame:
        """Return persisted causal regime observations in chronological order."""
        return self.database.fetch_dataframe(
            "SELECT timestamp, regime, confidence, rolling_return, rolling_volatility, "
            "moving_average_slope, momentum, drawdown "
            "FROM regime_observations WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        )

    def get_agent_decisions(self, experiment_id: str) -> pd.DataFrame:
        """Return persisted V0.3 agent decision chains in chronological order."""
        decisions = self.database.fetch_dataframe(
            "SELECT timestamp, technical_trend, technical_momentum, technical_volatility, technical_rsi, "
            "technical_signal_strength, technical_confidence, regime, regime_confidence, selected_strategy, "
            "action, execution_action, proposal_confidence, requested_position_size, strategy_reason_codes_json, "
            "risk_approved, adjusted_position_size, risk_reason_code "
            "FROM agent_decisions WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        )
        if not decisions.empty:
            decisions["strategy_reason_codes"] = decisions.pop("strategy_reason_codes_json").map(json.loads)
            decisions["risk_approved"] = decisions["risk_approved"].astype(bool)
        return decisions

    def list_agent_decisions(self, experiment_id: str, limit: int = 100, offset: int = 0) -> tuple[pd.DataFrame, int]:
        """Return a bounded page of decision history without loading all rows for API clients."""
        with self.database.connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) AS count FROM agent_decisions WHERE experiment_id = ?", (experiment_id,)).fetchone()["count"])
        decisions = self.database.fetch_dataframe(
            "SELECT timestamp, technical_trend, technical_momentum, technical_volatility, technical_rsi, "
            "technical_signal_strength, technical_confidence, regime, regime_confidence, selected_strategy, "
            "action, execution_action, proposal_confidence, requested_position_size, strategy_reason_codes_json, "
            "risk_approved, adjusted_position_size, risk_reason_code FROM agent_decisions WHERE experiment_id = ? "
            "ORDER BY id LIMIT ? OFFSET ?",
            (experiment_id, limit, offset),
        )
        if not decisions.empty:
            decisions["strategy_reason_codes"] = decisions.pop("strategy_reason_codes_json").map(json.loads)
            decisions["risk_approved"] = decisions["risk_approved"].astype(bool)
        return decisions, total

    def update_experiment_results(self, experiment_id: str, results: Mapping[str, Any]) -> None:
        """Attach post-experiment V0.4 output to an already persisted experiment."""
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE experiments SET results_json = ? WHERE experiment_id = ?",
                (json.dumps(results, default=str), experiment_id),
            )

    def save_critique(self, critique: ExperimentCritique) -> None:
        """Persist one typed deterministic critique for an experiment."""
        payload = critique.to_dict()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO critiques (
                    experiment_id, created_at, confidence, strengths_json, weaknesses_json, failure_modes_json,
                    regime_observations_json, recommendations_json, reason_codes_json, critique_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id) DO UPDATE SET
                    created_at = EXCLUDED.created_at, confidence = EXCLUDED.confidence,
                    strengths_json = EXCLUDED.strengths_json, weaknesses_json = EXCLUDED.weaknesses_json,
                    failure_modes_json = EXCLUDED.failure_modes_json,
                    regime_observations_json = EXCLUDED.regime_observations_json,
                    recommendations_json = EXCLUDED.recommendations_json,
                    reason_codes_json = EXCLUDED.reason_codes_json, critique_json = EXCLUDED.critique_json
                """,
                (
                    critique.experiment_id,
                    datetime.now(UTC).isoformat(),
                    critique.confidence,
                    json.dumps(payload["strengths"]),
                    json.dumps(payload["weaknesses"]),
                    json.dumps(payload["failure_modes"]),
                    json.dumps(payload["regime_observations"]),
                    json.dumps(payload["recommendations"]),
                    json.dumps(payload["reason_codes"]),
                    json.dumps(payload),
                ),
            )

    def get_critique(self, experiment_id: str) -> ExperimentCritique | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT critique_json FROM critiques WHERE experiment_id = ?", (experiment_id,)).fetchone()
        return ExperimentCritique.from_dict(json.loads(row["critique_json"])) if row else None

    def save_experiment_memory(self, record: ExperimentMemoryRecord) -> None:
        """Persist the retrieval-oriented V0.4 memory record and regime performance rows."""
        payload = record.to_dict()
        with self.database.connect() as connection:
            experiment = connection.execute(
                "SELECT created_at FROM experiments WHERE experiment_id = ?", (record.experiment_id,)
            ).fetchone()
            if experiment is None:
                raise ValueError(f"Experiment does not exist: {record.experiment_id}")
            connection.execute(
                """
                INSERT INTO experiment_memory (
                    experiment_id, created_at, agent_version, strategy, strategy_parameters_json,
                    regime_distribution_json, metrics_json, maximum_drawdown, turnover, transaction_costs_json,
                    critique_json, decision_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id) DO UPDATE SET
                    created_at = EXCLUDED.created_at, agent_version = EXCLUDED.agent_version,
                    strategy = EXCLUDED.strategy, strategy_parameters_json = EXCLUDED.strategy_parameters_json,
                    regime_distribution_json = EXCLUDED.regime_distribution_json, metrics_json = EXCLUDED.metrics_json,
                    maximum_drawdown = EXCLUDED.maximum_drawdown, turnover = EXCLUDED.turnover,
                    transaction_costs_json = EXCLUDED.transaction_costs_json, critique_json = EXCLUDED.critique_json,
                    decision_summary_json = EXCLUDED.decision_summary_json
                """,
                (
                    record.experiment_id,
                    experiment["created_at"],
                    record.agent_version,
                    record.strategy,
                    json.dumps(payload["strategy_parameters"]),
                    json.dumps(payload["regime_distribution"]),
                    json.dumps(payload["metrics"]),
                    record.maximum_drawdown,
                    record.turnover,
                    json.dumps(payload["transaction_costs"]),
                    json.dumps(payload["critique"]),
                    json.dumps(payload["decision_summary"]),
                ),
            )
            connection.execute("DELETE FROM memory_regime_performance WHERE experiment_id = ?", (record.experiment_id,))
            connection.executemany(
                """
                INSERT INTO memory_regime_performance (
                    experiment_id, strategy, regime, observations, compounded_return
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (record.experiment_id, record.strategy, item.regime, item.observations, item.compounded_return)
                    for item in record.regime_performance
                ],
            )

    def get_experiment_memory(self, experiment_id: str) -> ExperimentMemoryRecord | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM experiment_memory WHERE experiment_id = ?", (experiment_id,)).fetchone()
            performance_rows = connection.execute(
                "SELECT regime, observations, compounded_return FROM memory_regime_performance WHERE experiment_id = ? ORDER BY regime",
                (experiment_id,),
            ).fetchall()
        if row is None:
            return None
        data = {
            "experiment_id": row["experiment_id"],
            "agent_version": row["agent_version"],
            "strategy": row["strategy"],
            "strategy_parameters": json.loads(row["strategy_parameters_json"]),
            "regime_distribution": json.loads(row["regime_distribution_json"]),
            "regime_performance": [dict(item) for item in performance_rows],
            "metrics": json.loads(row["metrics_json"]),
            "maximum_drawdown": row["maximum_drawdown"],
            "turnover": row["turnover"],
            "transaction_costs": json.loads(row["transaction_costs_json"]),
            "critique": json.loads(row["critique_json"]),
            "decision_summary": json.loads(row["decision_summary_json"]),
        }
        return ExperimentMemoryRecord.from_dict(data)

    def best_performing_strategy_by_regime(self, regime: str, limit: int = 1) -> list[MemoryQueryResult]:
        return self._ranked_strategy_by_regime(regime, descending=True, limit=limit)

    def worst_performing_strategy_by_regime(self, regime: str, limit: int = 1) -> list[MemoryQueryResult]:
        return self._ranked_strategy_by_regime(regime, descending=False, limit=limit)

    def _ranked_strategy_by_regime(self, regime: str, descending: bool, limit: int) -> list[MemoryQueryResult]:
        direction = "DESC" if descending else "ASC"
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT memory.experiment_id, memory.strategy, performance.regime, performance.compounded_return,
                       memory.maximum_drawdown, memory.turnover, memory.created_at
                FROM experiment_memory AS memory
                JOIN memory_regime_performance AS performance ON performance.experiment_id = memory.experiment_id
                WHERE performance.regime = ?
                ORDER BY performance.compounded_return {direction}, memory.created_at DESC
                LIMIT ?
                """,
                (regime, limit),
            ).fetchall()
        return [self._memory_query_result(row) for row in rows]

    def experiments_with_high_drawdown(self, threshold: float) -> list[MemoryQueryResult]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT experiment_id, strategy, NULL AS regime, NULL AS regime_return, maximum_drawdown, turnover, created_at
                FROM experiment_memory WHERE maximum_drawdown <= ? ORDER BY maximum_drawdown ASC, created_at DESC
                """,
                (-abs(threshold),),
            ).fetchall()
        return [self._memory_query_result(row) for row in rows]

    def experiments_with_excessive_turnover(self, threshold: float) -> list[MemoryQueryResult]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT experiment_id, strategy, NULL AS regime, NULL AS regime_return, maximum_drawdown, turnover, created_at
                FROM experiment_memory WHERE turnover >= ? ORDER BY turnover DESC, created_at DESC
                """,
                (threshold,),
            ).fetchall()
        return [self._memory_query_result(row) for row in rows]

    def recent_critiques(self, limit: int = 10) -> list[ExperimentCritique]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT critique_json FROM critiques ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [ExperimentCritique.from_dict(json.loads(row["critique_json"])) for row in rows]

    # V0.5 configuration evolution records are append-only.  A candidate or version is never rewritten.
    def next_candidate_number(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTR(candidate_id, 6) AS INTEGER)), 0) AS last_number "
                "FROM candidate_configurations"
            ).fetchone()
        return int(row["last_number"]) + 1

    def next_version_id(self) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTR(version_id, 11) AS INTEGER)), 0) AS last_number "
                "FROM configuration_versions"
            ).fetchone()
        return f"FinAgent-A{int(row['last_number']) + 1:04d}"

    def save_configuration_version(self, version: ConfigurationVersion) -> None:
        """Insert an immutable baseline or promoted configuration version."""
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO configuration_versions (
                    version_id, parent_version_id, candidate_id, created_at, configuration_json,
                    validation_metrics_json, status, reason_codes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.parent_version_id,
                    version.candidate_id,
                    version.created_at,
                    json.dumps(version.configuration, sort_keys=True, default=str),
                    json.dumps(version.validation_metrics.to_dict()) if version.validation_metrics else None,
                    version.status.value,
                    json.dumps([code.value for code in version.reason_codes]),
                ),
            )

    def get_configuration_version(self, version_id: str) -> ConfigurationVersion | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM configuration_versions WHERE version_id = ?", (version_id,)).fetchone()
        return self._version_from_row(row) if row else None

    def current_configuration_version(self) -> ConfigurationVersion | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM configuration_versions
                WHERE status IN (?, ?)
                ORDER BY created_at DESC, version_id DESC LIMIT 1
                """,
                (PromotionStatus.BASELINE.value, PromotionStatus.PROMOTED.value),
            ).fetchone()
        return self._version_from_row(row) if row else None

    def configuration_version_history(self) -> list[ConfigurationVersion]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM configuration_versions ORDER BY created_at, version_id").fetchall()
        return [self._version_from_row(row) for row in rows]

    def save_candidate_configuration(self, candidate: CandidateProposal) -> None:
        """Insert a generated candidate before it is evaluated; duplicate IDs are rejected by the database."""
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO candidate_configurations (
                    candidate_id, parent_version_id, created_at, configuration_json, parameter_changes_json, reason_codes_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.candidate_id,
                    candidate.parent_version_id,
                    datetime.now(UTC).isoformat(),
                    json.dumps(candidate.configuration, sort_keys=True, default=str),
                    json.dumps([change.to_dict() for change in candidate.parameter_changes]),
                    json.dumps([code.value for code in candidate.reason_codes]),
                ),
            )

    def get_candidate_configuration(self, candidate_id: str) -> CandidateProposal | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM candidate_configurations WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            return None
        return CandidateProposal.from_dict(
            {
                "candidate_id": row["candidate_id"],
                "parent_version_id": row["parent_version_id"],
                "configuration": json.loads(row["configuration_json"]),
                "parameter_changes": json.loads(row["parameter_changes_json"]),
                "reason_codes": json.loads(row["reason_codes_json"]),
            }
        )

    def save_walk_forward_evaluation(self, evaluation: WalkForwardEvaluation, decision: PromotionDecision) -> None:
        """Persist every chronological test window plus its aggregate, final gate decision."""
        if evaluation.candidate_id != decision.candidate_id:
            raise ValueError("Walk-forward evaluation and promotion decision candidate IDs must match")
        created_at = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO walk_forward_validations (
                    candidate_id, window_index, train_start, train_end, test_start, test_end,
                    train_observations, test_observations, parent_metrics_json, candidate_metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        evaluation.candidate_id,
                        window.window_index,
                        window.train_start,
                        window.train_end,
                        window.test_start,
                        window.test_end,
                        window.train_observations,
                        window.test_observations,
                        json.dumps(window.parent_metrics.to_dict()),
                        json.dumps(window.candidate_metrics.to_dict()),
                    )
                    for window in evaluation.windows
                ],
            )
            connection.execute(
                """
                INSERT INTO candidate_evaluations (
                    candidate_id, parent_version_id, created_at, parent_metrics_json, candidate_metrics_json,
                    status, reason_codes_json, window_pass_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.candidate_id,
                    evaluation.parent_version_id,
                    created_at,
                    json.dumps(decision.parent_metrics.to_dict()),
                    json.dumps(decision.candidate_metrics.to_dict()),
                    decision.status.value,
                    json.dumps([code.value for code in decision.reason_codes]),
                    decision.window_pass_rate,
                ),
            )

    def get_validation_windows(self, candidate_id: str) -> list[WalkForwardWindow]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM walk_forward_validations WHERE candidate_id = ? ORDER BY window_index", (candidate_id,)
            ).fetchall()
        return [
            WalkForwardWindow.from_dict(
                {
                    "window_index": row["window_index"],
                    "train_start": row["train_start"],
                    "train_end": row["train_end"],
                    "test_start": row["test_start"],
                    "test_end": row["test_end"],
                    "train_observations": row["train_observations"],
                    "test_observations": row["test_observations"],
                    "parent_metrics": json.loads(row["parent_metrics_json"]),
                    "candidate_metrics": json.loads(row["candidate_metrics_json"]),
                }
            )
            for row in rows
        ]

    def get_candidate_evaluation(self, candidate_id: str) -> PromotionDecision | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM candidate_evaluations WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return self._decision_from_row(row) if row else None

    def latest_candidate_evaluation(self) -> PromotionDecision | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM candidate_evaluations ORDER BY created_at DESC LIMIT 1").fetchone()
        return self._decision_from_row(row) if row else None

    def list_candidate_evaluations(self, limit: int = 20, offset: int = 0, *, status: str | None = None, version: str | None = None, start_date: str | None = None, end_date: str | None = None) -> tuple[list[PromotionDecision], int]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        if version:
            clauses.append("parent_version_id = ?")
            parameters.append(version)
        if start_date:
            clauses.append("created_at >= ?")
            parameters.append(start_date)
        if end_date:
            clauses.append("created_at <= ?")
            parameters.append(f"{end_date}T23:59:59")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) AS count FROM candidate_evaluations{where}", parameters).fetchone()["count"]
            rows = connection.execute(
                f"SELECT * FROM candidate_evaluations{where} ORDER BY created_at DESC LIMIT ? OFFSET ?", [*parameters, limit, offset]
            ).fetchall()
        return [self._decision_from_row(row) for row in rows], int(total)

    # V0.6 reproducibility manifests and research-validation records.
    def save_manifest(self, manifest: ReproducibilityManifest) -> None:
        """Persist a configuration/data snapshot needed to reproduce an experiment."""
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_manifests (experiment_id, created_at, manifest_json)
                VALUES (?, ?, ?)
                ON CONFLICT(experiment_id) DO UPDATE SET created_at = EXCLUDED.created_at,
                    manifest_json = EXCLUDED.manifest_json
                """,
                (manifest.experiment_id, manifest.created_at, json.dumps(manifest.to_dict(), sort_keys=True, default=str)),
            )

    def get_manifest(self, experiment_id: str) -> ReproducibilityManifest | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT manifest_json FROM experiment_manifests WHERE experiment_id = ?", (experiment_id,)).fetchone()
        return ReproducibilityManifest.from_dict(json.loads(row["manifest_json"])) if row else None

    def next_validation_id(self) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTR(validation_id, 5) AS INTEGER)), 0) AS last_number FROM research_validations"
            ).fetchone()
        return f"VAL-{int(row['last_number']) + 1:06d}"

    def save_research_validation(self, validation: ResearchValidationResult, configuration: Mapping[str, Any]) -> None:
        """Persist aggregate and granular V0.6 validation evidence for one existing experiment."""
        payload = validation.to_dict()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_validations (
                    validation_id, experiment_id, created_at, configuration_json, aggregate_metrics_json, robustness_json,
                    leakage_json, confidence_intervals_json, manifest_json, validation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    validation.validation_id,
                    validation.experiment_id,
                    datetime.now(UTC).isoformat(),
                    json.dumps(configuration, sort_keys=True, default=str),
                    json.dumps(validation.aggregate_metrics.to_dict()),
                    json.dumps(validation.robustness.to_dict()),
                    json.dumps(validation.leakage.to_dict()),
                    json.dumps([item.to_dict() for item in validation.confidence_intervals]),
                    json.dumps(validation.manifest.to_dict(), sort_keys=True, default=str),
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )
            connection.executemany(
                """
                INSERT INTO research_validation_assets (
                    validation_id, asset, dataset, start_date, end_date, passed, metrics_json, benchmark_metrics_json,
                    regime_distribution_json, agent_observations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        validation.validation_id,
                        item.asset,
                        item.dataset,
                        item.start_date,
                        item.end_date,
                        int(item.passed),
                        json.dumps(item.metrics.to_dict()),
                        json.dumps(item.benchmark_metrics.to_dict()),
                        json.dumps(item.regime_distribution),
                        item.agent_observations,
                    )
                    for item in validation.asset_results
                ],
            )
            connection.executemany(
                """
                INSERT INTO research_validation_windows (
                    validation_id, asset, window_index, window_mode, train_start, train_end, test_start, test_end,
                    train_observations, test_observations, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        validation.validation_id,
                        item.asset,
                        item.window_index,
                        item.window_mode,
                        item.train_start,
                        item.train_end,
                        item.test_start,
                        item.test_end,
                        item.train_observations,
                        item.test_observations,
                        json.dumps(item.metrics.to_dict()),
                    )
                    for item in validation.windows
                ],
            )
            connection.executemany(
                """
                INSERT INTO sensitivity_analysis_results (
                    validation_id, parameter, parameter_value_json, metrics_json, stability_score
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (validation.validation_id, item.parameter, json.dumps(item.value), json.dumps(item.metrics.to_dict()), item.stability_score)
                    for item in validation.sensitivity
                ],
            )
            connection.executemany(
                """
                INSERT INTO ablation_study_results (
                    validation_id, variant, enabled_components_json, metrics_json, robustness_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        validation.validation_id,
                        item.variant,
                        json.dumps(item.enabled_components),
                        json.dumps(item.metrics.to_dict()),
                        json.dumps(item.robustness.to_dict()),
                    )
                    for item in validation.ablations
                ],
            )
            connection.executemany(
                """
                INSERT INTO benchmark_suite_results (validation_id, asset, benchmark, metrics_json)
                VALUES (?, ?, ?, ?)
                """,
                [(validation.validation_id, item.asset, item.benchmark, json.dumps(item.metrics.to_dict())) for item in validation.benchmarks],
            )

    def get_research_validation(self, validation_id: str) -> ResearchValidationResult | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT validation_json FROM research_validations WHERE validation_id = ?", (validation_id,)).fetchone()
        return ResearchValidationResult.from_dict(json.loads(row["validation_json"])) if row else None

    def latest_research_validation(self, experiment_id: str | None = None) -> ResearchValidationResult | None:
        query = "SELECT validation_json FROM research_validations"
        parameters: tuple[Any, ...] = ()
        if experiment_id is not None:
            query += " WHERE experiment_id = ?"
            parameters = (experiment_id,)
        query += " ORDER BY created_at DESC LIMIT 1"
        with self.database.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return ResearchValidationResult.from_dict(json.loads(row["validation_json"])) if row else None

    def list_research_validations(self, limit: int = 20, offset: int = 0, *, asset: str | None = None, status: str | None = None, start_date: str | None = None, end_date: str | None = None) -> tuple[list[ResearchValidationResult], int]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if asset:
            clauses.append("EXISTS (SELECT 1 FROM research_validation_assets AS asset_filter WHERE asset_filter.validation_id = research_validations.validation_id AND asset_filter.asset = ?)")
            parameters.append(asset)
        if status == "passed":
            expected = "1" if self.database.backend == "sqlite" else "TRUE"
            clauses.append(f"{self.database.json_boolean('validation_json', ('leakage', 'passed'))} = {expected}")
        elif status == "failed":
            expected = "0" if self.database.backend == "sqlite" else "FALSE"
            clauses.append(f"{self.database.json_boolean('validation_json', ('leakage', 'passed'))} = {expected}")
        if start_date:
            clauses.append("created_at >= ?")
            parameters.append(start_date)
        if end_date:
            clauses.append("created_at <= ?")
            parameters.append(f"{end_date}T23:59:59")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) AS count FROM research_validations{where}", parameters).fetchone()["count"]
            rows = connection.execute(
                f"SELECT validation_json FROM research_validations{where} ORDER BY created_at DESC LIMIT ? OFFSET ?", [*parameters, limit, offset]
            ).fetchall()
        return [ResearchValidationResult.from_dict(json.loads(row["validation_json"])) for row in rows], int(total)

    def count_configuration_versions(self) -> int:
        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) AS count FROM configuration_versions").fetchone()["count"])

    def latest_validation_created_at(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT created_at FROM research_validations ORDER BY created_at DESC LIMIT 1").fetchone()
        return str(row["created_at"]) if row else None

    @staticmethod
    def _memory_query_result(row: Any) -> MemoryQueryResult:
        regime_return = row["compounded_return"] if "compounded_return" in row.keys() else row["regime_return"]
        return MemoryQueryResult(
            experiment_id=row["experiment_id"],
            strategy=row["strategy"],
            regime=row["regime"],
            regime_return=regime_return,
            maximum_drawdown=row["maximum_drawdown"],
            turnover=row["turnover"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _version_from_row(row: Any) -> ConfigurationVersion:
        payload = {
            "version_id": row["version_id"],
            "parent_version_id": row["parent_version_id"],
            "candidate_id": row["candidate_id"],
            "configuration": json.loads(row["configuration_json"]),
            "validation_metrics": json.loads(row["validation_metrics_json"]) if row["validation_metrics_json"] else None,
            "status": row["status"],
            "reason_codes": json.loads(row["reason_codes_json"]),
            "created_at": row["created_at"],
        }
        return ConfigurationVersion.from_dict(payload)

    @staticmethod
    def _decision_from_row(row: Any) -> PromotionDecision:
        return PromotionDecision.from_dict(
            {
                "candidate_id": row["candidate_id"],
                "parent_version_id": row["parent_version_id"],
                "status": row["status"],
                "reason_codes": json.loads(row["reason_codes_json"]),
                "parent_metrics": json.loads(row["parent_metrics_json"]),
                "candidate_metrics": json.loads(row["candidate_metrics_json"]),
                "window_pass_rate": row["window_pass_rate"],
            }
        )

    @staticmethod
    def _to_record(row: Any) -> ExperimentRecord:
        return ExperimentRecord(
            experiment_id=row["experiment_id"],
            created_at=row["created_at"],
            strategy=row["strategy"],
            asset=row["asset"],
            dataset=row["dataset"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            starting_capital=row["starting_capital"],
            random_seed=row["random_seed"],
            configuration=json.loads(row["configuration_json"]),
            results=json.loads(row["results_json"]),
        )
