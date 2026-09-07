"""Backend-selection and durable-dataset coverage without a live PostgreSQL server."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finagent.data.registry import DatasetRegistry
from finagent.database.db import Database


def test_database_url_selects_postgresql_and_translates_portable_sql() -> None:
    database = Database("postgres://postgres.example:5432/finagent")

    assert database.backend == "postgresql"
    assert database.url.startswith("postgresql://")
    assert database.database_identifier == "postgres.example:5432/finagent"
    assert database.prepare_sql("SELECT * FROM experiments WHERE experiment_id = ?") == (
        "SELECT * FROM experiments WHERE experiment_id = %s"
    )
    assert "BIGSERIAL PRIMARY KEY" in database.prepare_sql("id INTEGER PRIMARY KEY AUTOINCREMENT")
    assert "::jsonb" in database.json_number("results_json", ("metrics", "total_return"))


def test_sqlite_registry_retains_durable_ohlcv_rows(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'datasets.db'}")
    registry = DatasetRegistry(database)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO datasets (dataset_id, provider, symbol, interval, created_at) VALUES (?, ?, ?, ?, ?)",
            ("DATA-TEST-1D", "test", "TEST", "1d", "2024-01-01T00:00:00+00:00"),
        )
        connection.execute(
            """INSERT INTO dataset_versions (
                version_id, dataset_id, version_number, provider, symbol, asset_class, exchange, interval,
                start_date, end_date, row_count, cache_path, checksum, created_at, last_refreshed_at,
                validation_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "DATA-TEST-1D-V001", "DATA-TEST-1D", 1, "test", "TEST", "equity", None, "1d",
                "2024-01-01", "2024-01-02", 2, "/ephemeral/cache.csv", "checksum",
                "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00",
                '{"status":"valid","issues":[],"quality":{"score":1.0,"components":{}},"policy":"reject"}',
                '{"symbol":"TEST","asset_class":"equity"}',
            ),
        )
        connection.execute(
            "UPDATE datasets SET current_version_id = ? WHERE dataset_id = ?",
            ("DATA-TEST-1D-V001", "DATA-TEST-1D"),
        )

    expected = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
            "open": [10.0, 11.0], "high": [11.0, 12.0], "low": [9.0, 10.0],
            "close": [10.5, 11.5], "volume": [100.0, 200.0],
        }
    )
    registry.store_ohlcv("DATA-TEST-1D-V001", expected)

    assert registry.has_ohlcv("DATA-TEST-1D-V001")
    loaded = registry.load_ohlcv("DATA-TEST-1D-V001")
    pd.testing.assert_frame_equal(loaded, expected)
