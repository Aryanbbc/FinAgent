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
from finagent.utils.ids import format_experiment_id


class ExperimentRepository:
    """A small repository layer that keeps database concerns out of the runner."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def next_experiment_id(self) -> str:
        with self.database.connect() as connection:
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
        experiment_id = self.next_experiment_id()
        created_at = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
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

    def get_trades(self, experiment_id: str) -> pd.DataFrame:
        with self.database.connect() as connection:
            return pd.read_sql_query(
                "SELECT timestamp, side, price, quantity, transaction_cost, portfolio_value, realized_pnl, trade_return "
                "FROM trades WHERE experiment_id = ? ORDER BY id",
                connection,
                params=(experiment_id,),
            )

    def get_regime_observations(self, experiment_id: str) -> pd.DataFrame:
        """Return persisted causal regime observations in chronological order."""
        with self.database.connect() as connection:
            return pd.read_sql_query(
                "SELECT timestamp, regime, confidence, rolling_return, rolling_volatility, "
                "moving_average_slope, momentum, drawdown "
                "FROM regime_observations WHERE experiment_id = ? ORDER BY id",
                connection,
                params=(experiment_id,),
            )

    def get_agent_decisions(self, experiment_id: str) -> pd.DataFrame:
        """Return persisted V0.3 agent decision chains in chronological order."""
        with self.database.connect() as connection:
            decisions = pd.read_sql_query(
                "SELECT timestamp, technical_trend, technical_momentum, technical_volatility, technical_rsi, "
                "technical_signal_strength, technical_confidence, regime, regime_confidence, selected_strategy, "
                "action, execution_action, proposal_confidence, requested_position_size, strategy_reason_codes_json, "
                "risk_approved, adjusted_position_size, risk_reason_code "
                "FROM agent_decisions WHERE experiment_id = ? ORDER BY id",
                connection,
                params=(experiment_id,),
            )
        if not decisions.empty:
            decisions["strategy_reason_codes"] = decisions.pop("strategy_reason_codes_json").map(json.loads)
            decisions["risk_approved"] = decisions["risk_approved"].astype(bool)
        return decisions

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
                INSERT OR REPLACE INTO critiques (
                    experiment_id, created_at, confidence, strengths_json, weaknesses_json, failure_modes_json,
                    regime_observations_json, recommendations_json, reason_codes_json, critique_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                INSERT OR REPLACE INTO experiment_memory (
                    experiment_id, created_at, agent_version, strategy, strategy_parameters_json,
                    regime_distribution_json, metrics_json, maximum_drawdown, turnover, transaction_costs_json,
                    critique_json, decision_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
