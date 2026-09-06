"""SQLite database initialization for local experiment storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import UTC, datetime
from typing import Any


class Database:
    """Creates and connects to the local V0.1–V0.6 SQLite schema."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        """Open a bounded local connection with foreign keys and lock waiting enabled."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        """Create all local research tables and safe performance indexes idempotently."""
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
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

                CREATE TABLE IF NOT EXISTS experiment_manifests (
                    experiment_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS research_validations (
                    validation_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    configuration_json TEXT NOT NULL,
                    aggregate_metrics_json TEXT NOT NULL,
                    robustness_json TEXT NOT NULL,
                    leakage_json TEXT NOT NULL,
                    confidence_intervals_json TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    validation_json TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS research_validation_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    validation_id TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    benchmark_metrics_json TEXT NOT NULL,
                    regime_distribution_json TEXT NOT NULL,
                    agent_observations INTEGER NOT NULL,
                    FOREIGN KEY (validation_id) REFERENCES research_validations(validation_id) ON DELETE CASCADE,
                    UNIQUE (validation_id, asset)
                );

                CREATE TABLE IF NOT EXISTS research_validation_windows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    validation_id TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    window_index INTEGER NOT NULL,
                    window_mode TEXT NOT NULL,
                    train_start TEXT NOT NULL,
                    train_end TEXT NOT NULL,
                    test_start TEXT NOT NULL,
                    test_end TEXT NOT NULL,
                    train_observations INTEGER NOT NULL,
                    test_observations INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    FOREIGN KEY (validation_id) REFERENCES research_validations(validation_id) ON DELETE CASCADE,
                    UNIQUE (validation_id, asset, window_index)
                );

                CREATE TABLE IF NOT EXISTS sensitivity_analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    validation_id TEXT NOT NULL,
                    parameter TEXT NOT NULL,
                    parameter_value_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    stability_score REAL NOT NULL,
                    FOREIGN KEY (validation_id) REFERENCES research_validations(validation_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ablation_study_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    validation_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    enabled_components_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    robustness_json TEXT NOT NULL,
                    FOREIGN KEY (validation_id) REFERENCES research_validations(validation_id) ON DELETE CASCADE,
                    UNIQUE (validation_id, variant)
                );

                CREATE TABLE IF NOT EXISTS benchmark_suite_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    validation_id TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    benchmark TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    FOREIGN KEY (validation_id) REFERENCES research_validations(validation_id) ON DELETE CASCADE,
                    UNIQUE (validation_id, asset, benchmark)
                );

                CREATE TABLE IF NOT EXISTS demo_seed_records (
                    seed_name TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    version TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_experiments_created_at ON experiments(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_experiments_strategy_asset ON experiments(strategy, asset);
                CREATE INDEX IF NOT EXISTS idx_regime_observations_experiment_regime ON regime_observations(experiment_id, regime);
                CREATE INDEX IF NOT EXISTS idx_agent_decisions_experiment_timestamp ON agent_decisions(experiment_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_candidate_evaluations_created ON candidate_evaluations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_validations_created ON research_validations(created_at DESC);
                """
            )

    def health_check(self) -> dict[str, Any]:
        """Return non-destructive SQLite status and an integrity-check result."""
        try:
            self.initialize()
            with self.connect() as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                quick = connection.execute("PRAGMA quick_check").fetchone()[0]
            return {
                "status": "ok" if integrity == "ok" and quick == "ok" else "degraded",
                "integrity_check": integrity,
                "quick_check": quick,
                "path": str(self.path),
                "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            }
        except sqlite3.Error as error:
            return {"status": "unavailable", "message": str(error), "path": str(self.path), "size_bytes": 0}

    def backup_to(self, destination: str | Path, *, overwrite: bool = False) -> Path:
        """Create a consistent SQLite backup without deleting the source database."""
        target = Path(destination)
        if target.resolve() == self.path.resolve():
            raise ValueError("backup destination must differ from the source database")
        if target.exists() and not overwrite:
            raise FileExistsError(f"backup already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(target) as backup:
            source.backup(backup)
        return target

    def save_demo_seed(self, seed_name: str, version: str, metadata_json: str) -> None:
        """Mark a populated sample database so seed commands remain idempotent."""
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO demo_seed_records (seed_name, created_at, version, metadata_json) VALUES (?, ?, ?, ?)",
                (seed_name, datetime.now(UTC).isoformat(), version, metadata_json),
            )

    def demo_seed(self, seed_name: str) -> sqlite3.Row | None:
        self.initialize()
        with self.connect() as connection:
            return connection.execute("SELECT * FROM demo_seed_records WHERE seed_name = ?", (seed_name,)).fetchone()
