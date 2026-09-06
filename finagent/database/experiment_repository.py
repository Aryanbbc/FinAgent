"""Persistence and retrieval of experiments, trades, and metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from finagent.database.db import Database
from finagent.database.models import ExperimentRecord
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
