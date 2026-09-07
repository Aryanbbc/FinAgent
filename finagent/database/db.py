"""Portable database initialization for local SQLite and production PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
import sqlite3
from typing import Any, Literal
from urllib.parse import urlsplit

import pandas as pd


DatabaseBackend = Literal["sqlite", "postgresql"]


class DatabaseError(RuntimeError):
    """Raised when a configured database cannot be opened or initialized."""


class DatabaseConnection:
    """Small DB-API adapter that keeps repository bind parameters portable."""

    def __init__(self, database: "Database", raw_connection: Any) -> None:
        self.database = database
        self.raw_connection = raw_connection

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            if exc_type is None:
                self.raw_connection.commit()
            else:
                self.raw_connection.rollback()
        finally:
            self.raw_connection.close()
        return False

    def execute(self, statement: str, parameters: Any = ()) -> Any:
        return self.raw_connection.execute(self.database.prepare_sql(statement), parameters)

    def executemany(self, statement: str, parameters: Any) -> Any:
        if self.database.backend == "sqlite":
            return self.raw_connection.executemany(self.database.prepare_sql(statement), parameters)
        with self.raw_connection.cursor() as cursor:
            return cursor.executemany(self.database.prepare_sql(statement), parameters)

    def executescript(self, script: str) -> None:
        if self.database.backend == "sqlite":
            self.raw_connection.executescript(script)
            return
        for statement in script.split(";"):
            if statement.strip():
                self.raw_connection.execute(self.database.prepare_sql(statement))


class Database:
    """Database abstraction preserving the repository contract across SQLite and PostgreSQL.

    A path (the historic API) remains a SQLite database.  URL inputs select the
    backend explicitly: ``sqlite:///...``, ``postgresql://...``, or ``postgres://``.
    """

    _SCHEMA_VERSION = "core-1"

    def __init__(self, database_url: str | Path, project_root: str | Path | None = None) -> None:
        value = str(database_url)
        self._project_root = Path(project_root).resolve() if project_root else Path.cwd()
        self.path: Path | None = None
        if value.startswith("postgresql://") or value.startswith("postgres://"):
            self.backend: DatabaseBackend = "postgresql"
            self.url = "postgresql://" + value.split("://", 1)[1]
        elif value.startswith("sqlite://"):
            self.backend = "sqlite"
            raw_path = value[len("sqlite:///") :] if value.startswith("sqlite:///") else value[len("sqlite://") :]
            self.path = self._resolve_sqlite_path(raw_path)
            self.url = "sqlite:///:memory:" if raw_path == ":memory:" else f"sqlite:///{self.path}"
        elif "://" not in value:
            self.backend = "sqlite"
            self.path = self._resolve_sqlite_path(value)
            self.url = "sqlite:///:memory:" if value == ":memory:" else f"sqlite:///{self.path}"
        else:
            raise ValueError("DATABASE_URL must use sqlite://, postgresql://, or postgres://")

    def _resolve_sqlite_path(self, raw_path: str) -> Path:
        if raw_path == ":memory:":
            return Path(":memory:")
        path = Path(raw_path)
        return path if path.is_absolute() else (self._project_root / path).resolve()

    @property
    def database_identifier(self) -> str:
        """Safe identifier suitable for health/system responses (no credentials)."""
        if self.backend == "sqlite":
            return str(self.path)
        parsed = urlsplit(self.url)
        return f"{parsed.hostname or 'postgres'}{f':{parsed.port}' if parsed.port else ''}{parsed.path or '/'}"

    def prepare_sql(self, statement: str) -> str:
        """Translate the repository's DB-API qmark parameters for psycopg."""
        if self.backend == "sqlite":
            return statement
        portable = statement.replace("?", "%s")
        return re.sub(
            r"\bid\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
            "id BIGSERIAL PRIMARY KEY",
            portable,
            flags=re.IGNORECASE,
        )

    def json_text(self, column: str, path: tuple[str, ...]) -> str:
        """Return a backend-specific expression for a JSON value kept in a text column."""
        if self.backend == "sqlite":
            return f"json_extract({column}, '$.{'.'.join(path)}')"
        return f"({column}::jsonb #>> '{{{','.join(path)}}}')"

    def json_number(self, column: str, path: tuple[str, ...]) -> str:
        expression = self.json_text(column, path)
        return expression if self.backend == "sqlite" else f"CAST({expression} AS DOUBLE PRECISION)"

    def json_boolean(self, column: str, path: tuple[str, ...]) -> str:
        expression = self.json_text(column, path)
        return expression if self.backend == "sqlite" else f"CAST({expression} AS BOOLEAN)"

    def connect(self) -> DatabaseConnection:
        """Open a bounded connection with backend-specific safety settings."""
        if self.backend == "sqlite":
            assert self.path is not None
            if self.path != Path(":memory:"):
                self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            return DatabaseConnection(self, connection)
        try:
            import psycopg
            from psycopg.rows import dict_row

            return DatabaseConnection(
                self,
                psycopg.connect(self.url, connect_timeout=5, row_factory=dict_row),
            )
        except ImportError as error:  # pragma: no cover - exercised in deployment packaging
            raise DatabaseError("PostgreSQL support requires the 'psycopg' package") from error
        except Exception as error:  # psycopg is intentionally an optional local dependency
            raise DatabaseError(f"Unable to connect to PostgreSQL: {error}") from error

    def initialize(self) -> None:
        """Apply the in-app versioned schema migration before work is accepted."""
        try:
            self._initialize_schema()
        except DatabaseError:
            raise
        except Exception as error:
            raise DatabaseError(f"Unable to initialize {self.backend} schema: {error}") from error

    def _initialize_schema(self) -> None:
        """Run the idempotent schema migration using an already selected backend."""
        with self.connect() as connection:
            if self.backend == "sqlite":
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
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
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?) "
                "ON CONFLICT(version) DO NOTHING",
                (self._SCHEMA_VERSION, datetime.now(UTC).isoformat()),
            )

    def fetch_dataframe(self, statement: str, parameters: Any = ()) -> pd.DataFrame:
        """Read a query into a dataframe without exposing a backend connection to pandas."""
        with self.connect() as connection:
            cursor = connection.execute(statement, parameters)
            rows = cursor.fetchall()
            columns = [item[0] for item in cursor.description]
        return pd.DataFrame([dict(row) for row in rows], columns=columns)

    def health_check(self) -> dict[str, Any]:
        """Return non-destructive status, including the selected database backend."""
        try:
            self.initialize()
            with self.connect() as connection:
                if self.backend == "sqlite":
                    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                    quick = connection.execute("PRAGMA quick_check").fetchone()[0]
                else:
                    connection.execute("SELECT 1").fetchone()
                    integrity = "not_applicable"
                    quick = "not_applicable"
            return {
                "status": "ok" if self.backend == "postgresql" or (integrity == "ok" and quick == "ok") else "degraded",
                "database_status": "ok",
                "database_backend": self.backend,
                "database_connectivity": True,
                "integrity_check": integrity,
                "quick_check": quick,
                "path": self.database_identifier,
                "size_bytes": self.path.stat().st_size if self.backend == "sqlite" and self.path and self.path.exists() else 0,
            }
        except Exception as error:
            return {
                "status": "unavailable",
                "database_status": "unavailable",
                "database_backend": self.backend,
                "database_connectivity": False,
                "message": str(error),
                "path": self.database_identifier,
                "size_bytes": 0,
            }

    def backup_to(self, destination: str | Path, *, overwrite: bool = False) -> Path:
        """Create a consistent SQLite backup without deleting the source database."""
        if self.backend != "sqlite":
            raise ValueError("Database backups are only available for SQLite; use PostgreSQL-native backups in production")
        assert self.path is not None
        target = Path(destination)
        if target.resolve() == self.path.resolve():
            raise ValueError("backup destination must differ from the source database")
        if target.exists() and not overwrite:
            raise FileExistsError(f"backup already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(target) as backup:
            source.raw_connection.backup(backup)
        return target

    def save_demo_seed(self, seed_name: str, version: str, metadata_json: str) -> None:
        """Mark a populated sample database so seed commands remain idempotent."""
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO demo_seed_records (seed_name, created_at, version, metadata_json) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(seed_name) DO UPDATE SET created_at = EXCLUDED.created_at, "
                "version = EXCLUDED.version, metadata_json = EXCLUDED.metadata_json",
                (seed_name, datetime.now(UTC).isoformat(), version, metadata_json),
            )

    def demo_seed(self, seed_name: str) -> Any | None:
        self.initialize()
        with self.connect() as connection:
            return connection.execute("SELECT * FROM demo_seed_records WHERE seed_name = ?", (seed_name,)).fetchone()
