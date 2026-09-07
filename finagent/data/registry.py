"""Portable immutable dataset revisions, OHLCV rows, and named collections."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from finagent.data.models import AssetMetadata, DatasetCollection, DatasetValidationResult, DatasetVersion
from finagent.database.db import Database


class DatasetNotFoundError(LookupError):
    """Raised when an API/runner references a dataset that is not registered."""


class DatasetRegistry:
    """Stores append-only content revisions and resolves a dataset's current revision."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        self._initialize()

    def _initialize(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    current_version_id TEXT,
                    UNIQUE(provider, symbol, interval)
                );
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    version_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    exchange TEXT,
                    interval TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    cache_path TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_refreshed_at TEXT NOT NULL,
                    validation_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id),
                    UNIQUE(dataset_id, version_number),
                    UNIQUE(dataset_id, checksum)
                );
                CREATE TABLE IF NOT EXISTS dataset_collections (
                    collection_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dataset_collection_members (
                    collection_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY(collection_id, dataset_id),
                    FOREIGN KEY(collection_id) REFERENCES dataset_collections(collection_id) ON DELETE CASCADE,
                    FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id),
                    FOREIGN KEY(version_id) REFERENCES dataset_versions(version_id)
                );
                CREATE TABLE IF NOT EXISTS dataset_ohlcv_rows (
                    version_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    PRIMARY KEY(version_id, timestamp),
                    FOREIGN KEY(version_id) REFERENCES dataset_versions(version_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_dataset_versions_refreshed ON dataset_versions(last_refreshed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_dataset_versions_filters ON dataset_versions(provider, symbol, validation_json);
                CREATE INDEX IF NOT EXISTS idx_dataset_ohlcv_rows_version_timestamp ON dataset_ohlcv_rows(version_id, timestamp);
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?) "
                "ON CONFLICT(version) DO NOTHING",
                ("datasets-1", datetime.now(UTC).isoformat()),
            )

    @staticmethod
    def make_dataset_id(provider: str, symbol: str, interval: str) -> str:
        clean = re.sub(r"[^A-Z0-9]+", "-", f"{provider}-{symbol}-{interval}".upper()).strip("-")
        return f"DATA-{clean}"

    def latest(self, dataset_id: str) -> DatasetVersion:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT version.* FROM datasets AS dataset JOIN dataset_versions AS version
                   ON version.version_id = dataset.current_version_id WHERE dataset.dataset_id = ?""",
                (dataset_id,),
            ).fetchone()
        if row is None:
            raise DatasetNotFoundError(f"Dataset not found: {dataset_id}")
        return self._version_from_row(row)

    def get_version(self, version_id: str) -> DatasetVersion:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM dataset_versions WHERE version_id = ?", (version_id,)).fetchone()
        if row is None:
            raise DatasetNotFoundError(f"Dataset version not found: {version_id}")
        return self._version_from_row(row)

    def versions(self, dataset_id: str) -> list[DatasetVersion]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM dataset_versions WHERE dataset_id = ? ORDER BY version_number DESC", (dataset_id,)).fetchall()
        if not rows:
            raise DatasetNotFoundError(f"Dataset not found: {dataset_id}")
        return [self._version_from_row(row) for row in rows]

    def list_datasets(self, limit: int = 50, offset: int = 0, *, provider: str | None = None, symbol: str | None = None, status: str | None = None, start_date: str | None = None, end_date: str | None = None) -> tuple[list[DatasetVersion], int]:
        clauses: list[str] = []
        parameters: list[object] = []
        if provider:
            clauses.append("version.provider = ?")
            parameters.append(provider)
        if symbol:
            clauses.append("version.symbol = ?")
            parameters.append(symbol)
        if status:
            clauses.append(f"{self.database.json_text('version.validation_json', ('status',))} = ?")
            parameters.append(status)
        if start_date:
            clauses.append("version.end_date >= ?")
            parameters.append(start_date)
        if end_date:
            clauses.append("version.start_date <= ?")
            parameters.append(end_date)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connect() as connection:
            # The conditional SQL fragments are fixed predicates; all filter values use bindings.
            total = int(connection.execute(
                f"SELECT COUNT(*) AS count FROM datasets AS dataset JOIN dataset_versions AS version ON version.version_id = dataset.current_version_id{where}", parameters  # nosec B608
            ).fetchone()["count"])
            rows = connection.execute(
                """SELECT version.* FROM datasets AS dataset JOIN dataset_versions AS version
                   ON version.version_id = dataset.current_version_id""" + where + " ORDER BY version.last_refreshed_at DESC LIMIT ? OFFSET ?",  # nosec B608
                [*parameters, limit, offset],
            ).fetchall()
        return [self._version_from_row(row) for row in rows], total

    def next_version_number(self, dataset_id: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COALESCE(MAX(version_number), 0) AS number FROM dataset_versions WHERE dataset_id = ?", (dataset_id,)).fetchone()
        return int(row["number"]) + 1

    def save_version(
        self,
        *,
        dataset_id: str,
        provider: str,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        row_count: int,
        cache_path: str | Path,
        checksum: str,
        validation: DatasetValidationResult,
        metadata: AssetMetadata,
        dataset_provider: str | None = None,
    ) -> DatasetVersion:
        """Create a new immutable content revision, or touch the matching cached revision."""
        now = datetime.now(UTC).isoformat()
        path = str(cache_path)
        # Dataset identity may be the requested ``auto`` selector while the
        # immutable version records the concrete provider that supplied rows.
        # Keeping those two notions distinct avoids uniqueness collisions with
        # an explicitly requested Yahoo or Stooq dataset for the same symbol.
        dataset_provider = dataset_provider or provider
        with self.database.connect() as connection:
            existing = connection.execute("SELECT * FROM dataset_versions WHERE dataset_id = ? AND checksum = ?", (dataset_id, checksum)).fetchone()
            if existing is not None:
                connection.execute(
                    "UPDATE dataset_versions SET last_refreshed_at = ?, validation_json = ?, metadata_json = ? WHERE version_id = ?",
                    (now, json.dumps(validation.to_dict(), sort_keys=True), json.dumps(metadata.to_dict(), sort_keys=True), existing["version_id"]),
                )
                connection.execute("UPDATE datasets SET current_version_id = ? WHERE dataset_id = ?", (existing["version_id"], dataset_id))
                refreshed = connection.execute("SELECT * FROM dataset_versions WHERE version_id = ?", (existing["version_id"],)).fetchone()
                return self._version_from_row(refreshed)
            number_row = connection.execute("SELECT COALESCE(MAX(version_number), 0) AS number FROM dataset_versions WHERE dataset_id = ?", (dataset_id,)).fetchone()
            number = int(number_row["number"]) + 1
            version_id = f"{dataset_id}-V{number:03d}"
            connection.execute(
                "INSERT INTO datasets (dataset_id, provider, symbol, interval, created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(dataset_id) DO NOTHING",
                (dataset_id, dataset_provider, symbol, interval, now),
            )
            connection.execute(
                """INSERT INTO dataset_versions (
                    version_id, dataset_id, version_number, provider, symbol, asset_class, exchange, interval,
                    start_date, end_date, row_count, cache_path, checksum, created_at, last_refreshed_at,
                    validation_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id, dataset_id, number, provider, symbol, metadata.asset_class, metadata.exchange, interval,
                    start_date, end_date, row_count, path, checksum, now, now,
                    json.dumps(validation.to_dict(), sort_keys=True), json.dumps(metadata.to_dict(), sort_keys=True),
                ),
            )
            connection.execute("UPDATE datasets SET current_version_id = ? WHERE dataset_id = ?", (version_id, dataset_id))
            row = connection.execute("SELECT * FROM dataset_versions WHERE version_id = ?", (version_id,)).fetchone()
        return self._version_from_row(row)

    def create_collection(self, name: str, dataset_ids: list[str], description: str | None = None) -> DatasetCollection:
        collection_id = "COLL-" + re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")
        now = datetime.now(UTC).isoformat()
        members = [(dataset_id, self.latest(dataset_id).version_id) for dataset_id in dataset_ids]
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO dataset_collections (collection_id, name, description, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(collection_id) DO UPDATE SET name = EXCLUDED.name, "
                "description = EXCLUDED.description, created_at = EXCLUDED.created_at",
                (collection_id, name, description, now),
            )
            connection.execute("DELETE FROM dataset_collection_members WHERE collection_id = ?", (collection_id,))
            connection.executemany(
                "INSERT INTO dataset_collection_members (collection_id, dataset_id, version_id, position) VALUES (?, ?, ?, ?)",
                [(collection_id, dataset_id, version_id, position) for position, (dataset_id, version_id) in enumerate(members)],
            )
        return self.get_collection(collection_id)

    def get_collection(self, collection_id: str) -> DatasetCollection:
        with self.database.connect() as connection:
            collection = connection.execute("SELECT * FROM dataset_collections WHERE collection_id = ?", (collection_id,)).fetchone()
            rows = connection.execute(
                """SELECT member.dataset_id, member.version_id, version.symbol, version.metadata_json FROM dataset_collection_members AS member
                   JOIN dataset_versions AS version ON version.version_id = member.version_id
                   WHERE member.collection_id = ? ORDER BY member.position""",
                (collection_id,),
            ).fetchall()
        if collection is None:
            raise DatasetNotFoundError(f"Dataset collection not found: {collection_id}")
        members = []
        adjustment_modes = set()
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            adjustment_mode = str(metadata.get("adjustment_mode", "unknown"))
            adjustment_modes.add(adjustment_mode)
            members.append({"dataset_id": row["dataset_id"], "version_id": row["version_id"], "symbol": row["symbol"], "adjustment_mode": adjustment_mode})
        warnings = ("MIXED_ADJUSTMENT_MODES",) if len(adjustment_modes) > 1 else ()
        return DatasetCollection(collection["collection_id"], collection["name"], collection["description"], tuple(members), collection["created_at"], warnings)

    def list_collections(self, limit: int | None = None, offset: int = 0) -> list[DatasetCollection]:
        with self.database.connect() as connection:
            query = "SELECT collection_id FROM dataset_collections ORDER BY name"
            values: tuple[int, ...] = ()
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                values = (limit, offset)
            rows = connection.execute(query, values).fetchall()
        return [self.get_collection(row["collection_id"]) for row in rows]

    def collection_count(self) -> int:
        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) AS count FROM dataset_collections").fetchone()["count"])

    def has_ohlcv(self, version_id: str) -> bool:
        """Return whether immutable OHLCV rows are available independently of the local cache."""
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM dataset_ohlcv_rows WHERE version_id = ? LIMIT 1", (version_id,)
            ).fetchone() is not None

    def store_ohlcv(self, version_id: str, frame: pd.DataFrame) -> None:
        """Persist canonical historical rows atomically for cloud-safe dataset retrieval."""
        required = ("timestamp", "open", "high", "low", "close", "volume")
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"Cannot persist OHLCV rows without columns: {', '.join(missing)}")
        rows = [
            (
                version_id,
                pd.Timestamp(item["timestamp"]).isoformat(),
                float(item["open"]), float(item["high"]), float(item["low"]),
                float(item["close"]), float(item["volume"]),
            )
            for item in frame.loc[:, list(required)].to_dict(orient="records")
        ]
        with self.database.connect() as connection:
            connection.execute("DELETE FROM dataset_ohlcv_rows WHERE version_id = ?", (version_id,))
            connection.executemany(
                "INSERT INTO dataset_ohlcv_rows (version_id, timestamp, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def load_ohlcv(self, version_id: str) -> pd.DataFrame:
        """Load database-backed canonical OHLCV rows, preserving chronological order."""
        frame = self.database.fetch_dataframe(
            "SELECT timestamp, open, high, low, close, volume FROM dataset_ohlcv_rows "
            "WHERE version_id = ? ORDER BY timestamp",
            (version_id,),
        )
        if frame.empty:
            raise DatasetNotFoundError(f"OHLCV rows not found for dataset version: {version_id}")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        return frame

    @staticmethod
    def _version_from_row(row: object) -> DatasetVersion:
        return DatasetVersion(
            dataset_id=row["dataset_id"], version_id=row["version_id"], version_number=int(row["version_number"]),
            provider=row["provider"], symbol=row["symbol"], asset_class=row["asset_class"], exchange=row["exchange"],
            interval=row["interval"], start_date=row["start_date"], end_date=row["end_date"], row_count=int(row["row_count"]),
            cache_path=row["cache_path"], checksum=row["checksum"], created_at=row["created_at"], last_refreshed_at=row["last_refreshed_at"],
            validation=DatasetValidationResult.from_dict(json.loads(row["validation_json"])), metadata=AssetMetadata(**json.loads(row["metadata_json"])),
        )
