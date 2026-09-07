"""Portable persistence for bounded live-monitoring research evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from finagent.database.db import Database
from finagent.live.models import LiveFeedState, LiveSignal
from finagent.regime.models import RegimeObservation


class LiveMarketRepository:
    """Keeps live feed evidence separate from immutable historical experiments."""

    _MIGRATION = "live-market-1"

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        self.initialize()

    def initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    price REAL NOT NULL,
                    provider TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    technical_json TEXT NOT NULL,
                    regime_json TEXT NOT NULL,
                    strategy_json TEXT NOT NULL,
                    risk_json TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(symbol, timestamp)
                );
                CREATE TABLE IF NOT EXISTS live_regime_observations (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    rolling_return REAL,
                    rolling_volatility REAL,
                    moving_average_slope REAL,
                    momentum REAL,
                    drawdown REAL,
                    provider TEXT NOT NULL,
                    PRIMARY KEY(symbol, timestamp)
                );
                CREATE TABLE IF NOT EXISTS live_feed_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    feed_status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_live_signals_symbol_timestamp ON live_signals(symbol, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_live_regimes_symbol_timestamp ON live_regime_observations(symbol, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_live_events_symbol_timestamp ON live_feed_events(symbol, timestamp DESC);
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?) ON CONFLICT(version) DO NOTHING",
                (self._MIGRATION, datetime.now(UTC).isoformat()),
            )

    def save_signal(self, signal: LiveSignal, retention: int) -> None:
        record = signal.to_dict()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO live_signals (
                    symbol, timestamp, price, provider, action, confidence, technical_json,
                    regime_json, strategy_json, risk_json, reason_codes_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp) DO UPDATE SET
                    price = EXCLUDED.price, provider = EXCLUDED.provider, action = EXCLUDED.action,
                    confidence = EXCLUDED.confidence, technical_json = EXCLUDED.technical_json,
                    regime_json = EXCLUDED.regime_json, strategy_json = EXCLUDED.strategy_json,
                    risk_json = EXCLUDED.risk_json, reason_codes_json = EXCLUDED.reason_codes_json,
                    created_at = EXCLUDED.created_at
                """,
                (
                    signal.symbol,
                    record["timestamp"],
                    signal.price,
                    signal.provider,
                    signal.action.value,
                    signal.confidence,
                    json.dumps(record["technical"], sort_keys=True),
                    json.dumps(record["regime"], sort_keys=True),
                    json.dumps(record["strategy"], sort_keys=True),
                    json.dumps(record["risk"], sort_keys=True),
                    json.dumps(record["reason_codes"]),
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._trim(connection, "live_signals", signal.symbol, retention)

    def save_regime(self, symbol: str, regime: RegimeObservation, provider: str, retention: int) -> None:
        values = regime.features
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO live_regime_observations (
                    symbol, timestamp, regime, confidence, rolling_return, rolling_volatility,
                    moving_average_slope, momentum, drawdown, provider
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp) DO UPDATE SET
                    regime = EXCLUDED.regime, confidence = EXCLUDED.confidence,
                    rolling_return = EXCLUDED.rolling_return, rolling_volatility = EXCLUDED.rolling_volatility,
                    moving_average_slope = EXCLUDED.moving_average_slope, momentum = EXCLUDED.momentum,
                    drawdown = EXCLUDED.drawdown, provider = EXCLUDED.provider
                """,
                (
                    symbol,
                    regime.timestamp.isoformat(),
                    regime.regime.value,
                    regime.confidence,
                    values.rolling_return,
                    values.rolling_volatility,
                    values.moving_average_slope,
                    values.momentum,
                    values.drawdown,
                    provider,
                ),
            )
            self._trim(connection, "live_regime_observations", symbol, retention)

    def save_event(self, symbol: str, state: LiveFeedState, event_type: str, summary: str, metadata: dict[str, object], retention: int) -> None:
        timestamp = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO live_feed_events (
                    symbol, timestamp, event_type, provider, feed_status, summary, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (symbol, timestamp, event_type, state.provider, state.status.value, summary, json.dumps(metadata, sort_keys=True, default=str)),
            )
            self._trim(connection, "live_feed_events", symbol, retention)

    @staticmethod
    def _trim(connection: Any, table: str, symbol: str, retention: int) -> None:
        """Keep bounded recent evidence without retaining an unbounded tick stream."""
        connection.execute(
            f"DELETE FROM {table} WHERE symbol = ? AND id NOT IN (SELECT id FROM {table} WHERE symbol = ? ORDER BY id DESC LIMIT ?)",
            (symbol, symbol, retention),
        ) if table in {"live_signals", "live_feed_events"} else connection.execute(
            """DELETE FROM live_regime_observations WHERE symbol = ? AND timestamp NOT IN (
                SELECT timestamp FROM live_regime_observations WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?
            )""",
            (symbol, symbol, retention),
        )

    def signals(self, symbol: str, limit: int) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM live_signals WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?", (symbol, limit)
            ).fetchall()
        return [
            {
                "symbol": row["symbol"],
                "timestamp": row["timestamp"],
                "price": float(row["price"]),
                "provider": row["provider"],
                "technical": json.loads(row["technical_json"]),
                "regime": json.loads(row["regime_json"]),
                "strategy": json.loads(row["strategy_json"]),
                "action": row["action"],
                "confidence": float(row["confidence"]),
                "risk": json.loads(row["risk_json"]),
                "reason_codes": json.loads(row["reason_codes_json"]),
            }
            for row in rows
        ]

    def events(self, symbol: str, limit: int) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM live_feed_events WHERE symbol = ? ORDER BY id DESC LIMIT ?", (symbol, limit)
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "provider": row["provider"],
                "feed_status": row["feed_status"],
                "summary": row["summary"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]
