"""V0.8 provider, cache, registry, quality, and dataset-reference coverage without live network calls."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from finagent.data.manager import DatasetManager
from finagent.data.market_provider import LocalCSVProvider, MarketDataProvider, MarketDataProviderError, ProviderRegistry, YahooFinanceProvider
from finagent.data.models import AssetMetadata, MarketDataRequest, MissingDataPolicy
from finagent.data.quality import DataValidationPipeline
from finagent.data.registry import DatasetRegistry
from finagent.data.validator import DataValidationError
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.runner import run_experiment
from finagent.validation.workflow import run_research_validation

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _frame(close: float = 10.5) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC"),
        "open": [10.0] * 8, "high": [11.0] * 8, "low": [9.0] * 8, "close": [close] * 8, "volume": [100.0] * 8,
    })


class MutableProvider(MarketDataProvider):
    provider_name = "mock_public"

    def __init__(self) -> None: self.frame = _frame(); self.calls = 0
    def validate_request(self, request: MarketDataRequest) -> None: return None
    def fetch_ohlcv(self, request: MarketDataRequest) -> pd.DataFrame: self.calls += 1; return self.frame.copy()
    def fetch_metadata(self, request: MarketDataRequest) -> AssetMetadata: return AssetMetadata(request.symbol, "Mock", "TEST", "USD", request.asset_class, "UTC", "unadjusted")


def test_local_csv_provider_and_yahoo_adapter_normalize_without_live_internet() -> None:
    local = LocalCSVProvider().fetch_ohlcv(MarketDataRequest("EXAMPLE", "2024-01-01", "2024-03-01", source_path=str(PROJECT_ROOT / "data/raw/example_ohlcv.csv")))
    assert list(local.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    payload = {"chart": {"result": [{"timestamp": [1704067200, 1704153600], "meta": {"longName": "Apple Inc.", "exchangeName": "NASDAQ", "currency": "USD", "exchangeTimezoneName": "America/New_York"}, "indicators": {"quote": [{"open": [10, 11], "high": [11, 12], "low": [9, 10], "close": [10.5, 11.5], "volume": [100, 110]}]}}], "error": None}}
    provider = YahooFinanceProvider(lambda _: json.dumps(payload).encode("utf-8"))
    frame = provider.fetch_ohlcv(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03"))
    assert len(frame) == 2 and provider.fetch_metadata(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03")).adjustment_mode == "unadjusted"
    with pytest.raises(MarketDataProviderError, match="daily"):
        provider.fetch_ohlcv(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03", interval="1h"))


def test_quality_pipeline_reports_gaps_and_never_backfills_future_values() -> None:
    gapped = _frame()
    gapped.loc[7, "timestamp"] = pd.Timestamp("2024-02-01", tz="UTC")
    report = DataValidationPipeline(max_gap_days=7).assess(gapped)
    assert report.status.value == "warning"
    assert report.quality.score < 1.0
    assert {"completeness", "nan_rate", "duplicate_rate", "chronological_consistency", "ohlc_validity", "gap_severity"} <= set(report.quality.components)
    assert any(issue.code == "SUSPICIOUS_GAPS" for issue in report.issues)
    missing = _frame(); missing.loc[2, "close"] = None
    with pytest.raises(DataValidationError):
        DataValidationPipeline().prepare(missing, MissingDataPolicy.REJECT)
    repaired, _ = DataValidationPipeline().prepare(missing, MissingDataPolicy.FORWARD_FILL)
    assert repaired.loc[2, "close"] == repaired.loc[1, "close"]


def test_cache_registry_checksum_revisions_and_collections_are_immutable(tmp_path: Path) -> None:
    provider = MutableProvider()
    registry = DatasetRegistry(Database(tmp_path / "datasets.db"))
    manager = DatasetManager(registry, tmp_path / "cache", ProviderRegistry((provider,)))
    request = MarketDataRequest("MOCK", "2024-01-01", "2024-01-10")
    first = manager.fetch("mock_public", request)
    cached = manager.fetch("mock_public", request)
    assert cached.cache_hit and provider.calls == 1 and cached.dataset.version_id == first.dataset.version_id
    provider.frame.loc[0, "close"] = 10.7
    refreshed = manager.fetch("mock_public", MarketDataRequest("MOCK", "2024-01-01", "2024-01-10", force_refresh=True))
    assert refreshed.dataset.version_number == 2
    assert len(registry.versions(first.dataset.dataset_id)) == 2
    collection = registry.create_collection("US_TECH_SAMPLE", [first.dataset.dataset_id])
    assert collection.members[0]["version_id"] == refreshed.dataset.version_id


def test_dataset_id_experiment_reference_records_provenance_and_collection_validation(tmp_path: Path) -> None:
    database_path = tmp_path / "research.db"
    registry = DatasetRegistry(Database(database_path))
    manager = DatasetManager(registry, tmp_path / "cache", ProviderRegistry((LocalCSVProvider(),)))
    first = manager.fetch("local_csv", MarketDataRequest("PRIMARY", "2024-01-01", "2024-03-01", source_path=str(PROJECT_ROOT / "data/raw/example_ohlcv.csv"))).dataset
    second = manager.fetch("local_csv", MarketDataRequest("SECONDARY", "2024-01-01", "2024-03-01", source_path=str(PROJECT_ROOT / "data/raw/example_ohlcv_secondary.csv"))).dataset
    registry.create_collection("US_TECH_SAMPLE", [first.dataset_id, second.dataset_id])
    source = tmp_path / "dataset-id.yaml"
    source.write_text(yaml.safe_dump({"experiment": {"asset": "PRIMARY", "dataset_id": first.dataset_id, "starting_capital": 10000.0, "random_seed": 7}, "database_path": str(database_path), "strategy": {"name": "momentum", "parameters": {"lookback_window": 5, "entry_threshold": 0.0, "exit_threshold": -0.02}}, "agents": {"enabled": False}, "critic": {"enabled": False}}), encoding="utf-8")
    experiment_id, results = run_experiment(source, PROJECT_ROOT)
    manifest = ExperimentRepository(Database(database_path)).get_manifest(experiment_id)
    assert results["dataset_provenance"]["dataset_id"] == first.dataset_id
    assert manifest is not None and manifest.datasets[0]["registry"]["dataset_version"] == first.version_id
    validation = tmp_path / "collection-validation.yaml"
    validation.write_text(yaml.safe_dump({"source_experiment_config": str(source), "validation": {"enabled": True, "dataset_collection_id": "COLL-US-TECH-SAMPLE", "asset_pass": {"maximum_drawdown": 0.20, "minimum_trades": 0}, "walk_forward": {"window_mode": "rolling", "train_size": 15, "test_size": 10, "step_size": 10, "minimum_train_length": 15, "minimum_test_length": 10, "non_overlapping_test_windows": True}, "leakage_checks": {"enabled": True}, "sensitivity": {"enabled": False}, "bootstrap": {"enabled": False}, "ablation": {"enabled": False}, "benchmarks": {"enabled": False}}}), encoding="utf-8")
    result = run_research_validation(validation, PROJECT_ROOT)
    assert result is not None and {item.asset for item in result.asset_results} == {"PRIMARY", "SECONDARY"}
