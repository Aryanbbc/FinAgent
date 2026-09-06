"""SQLite database initialization for local experiment storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Creates and connects to the local V0.1–V0.5 SQLite schema."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create V0.1–V0.5 tables idempotently, including improvement audit records."""
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    starting_capital REAL NOT NULL,
                    random_seed INTEGER,
                    configuration_json TEXT NOT NULL,
                    results_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    transaction_cost REAL NOT NULL,
                    portfolio_value REAL NOT NULL,
                    realized_pnl REAL,
                    trade_return REAL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value REAL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE,
                    UNIQUE (experiment_id, name)
                );

                CREATE TABLE IF NOT EXISTS regime_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    rolling_return REAL,
                    rolling_volatility REAL,
                    moving_average_slope REAL,
                    momentum REAL,
                    drawdown REAL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE,
                    UNIQUE (experiment_id, timestamp)
                );

                CREATE TABLE IF NOT EXISTS agent_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    technical_trend TEXT NOT NULL,
                    technical_momentum TEXT NOT NULL,
                    technical_volatility TEXT NOT NULL,
                    technical_rsi TEXT NOT NULL,
                    technical_signal_strength REAL NOT NULL,
                    technical_confidence REAL NOT NULL,
                    regime TEXT NOT NULL,
                    regime_confidence REAL NOT NULL,
                    selected_strategy TEXT NOT NULL,
                    action TEXT NOT NULL,
                    execution_action TEXT NOT NULL,
                    proposal_confidence REAL NOT NULL,
                    requested_position_size REAL NOT NULL,
                    strategy_reason_codes_json TEXT NOT NULL,
                    risk_approved INTEGER NOT NULL,
                    adjusted_position_size REAL NOT NULL,
                    risk_reason_code TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE,
                    UNIQUE (experiment_id, timestamp)
                );

                CREATE TABLE IF NOT EXISTS critiques (
                    experiment_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    strengths_json TEXT NOT NULL,
                    weaknesses_json TEXT NOT NULL,
                    failure_modes_json TEXT NOT NULL,
                    regime_observations_json TEXT NOT NULL,
                    recommendations_json TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    critique_json TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS experiment_memory (
                    experiment_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    agent_version TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    strategy_parameters_json TEXT NOT NULL,
                    regime_distribution_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    maximum_drawdown REAL NOT NULL,
                    turnover REAL,
                    transaction_costs_json TEXT NOT NULL,
                    critique_json TEXT NOT NULL,
                    decision_summary_json TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_regime_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    observations INTEGER NOT NULL,
                    compounded_return REAL NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiment_memory(experiment_id) ON DELETE CASCADE,
                    UNIQUE (experiment_id, regime)
                );

                CREATE TABLE IF NOT EXISTS configuration_versions (
                    version_id TEXT PRIMARY KEY,
                    parent_version_id TEXT,
                    candidate_id TEXT,
                    created_at TEXT NOT NULL,
                    configuration_json TEXT NOT NULL,
                    validation_metrics_json TEXT,
                    status TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    FOREIGN KEY (parent_version_id) REFERENCES configuration_versions(version_id)
                );

                CREATE TABLE IF NOT EXISTS candidate_configurations (
                    candidate_id TEXT PRIMARY KEY,
                    parent_version_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    configuration_json TEXT NOT NULL,
                    parameter_changes_json TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    FOREIGN KEY (parent_version_id) REFERENCES configuration_versions(version_id)
                );

                CREATE TABLE IF NOT EXISTS walk_forward_validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    window_index INTEGER NOT NULL,
                    train_start TEXT NOT NULL,
                    train_end TEXT NOT NULL,
                    test_start TEXT NOT NULL,
                    test_end TEXT NOT NULL,
                    train_observations INTEGER NOT NULL,
                    test_observations INTEGER NOT NULL,
                    parent_metrics_json TEXT NOT NULL,
                    candidate_metrics_json TEXT NOT NULL,
                    FOREIGN KEY (candidate_id) REFERENCES candidate_configurations(candidate_id) ON DELETE CASCADE,
                    UNIQUE (candidate_id, window_index)
                );

                CREATE TABLE IF NOT EXISTS candidate_evaluations (
                    candidate_id TEXT PRIMARY KEY,
                    parent_version_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    parent_metrics_json TEXT NOT NULL,
                    candidate_metrics_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    window_pass_rate REAL NOT NULL,
                    FOREIGN KEY (candidate_id) REFERENCES candidate_configurations(candidate_id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_version_id) REFERENCES configuration_versions(version_id)
                );
                """
            )
