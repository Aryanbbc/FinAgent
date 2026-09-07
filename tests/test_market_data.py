"""V0.8 provider, cache, registry, quality, and dataset-reference coverage without live network calls."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest
import yaml

from finagent.data.manager import DatasetManager
from finagent.data.market_provider import LocalCSVProvider, MarketDataProvider, MarketDataProviderError, ProviderRegistry, StooqProvider, TwelveDataProvider, YahooFinanceProvider
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


class SequencedProvider(MarketDataProvider):
    """Deterministic provider fake for retry/fallback tests without network I/O."""

    def __init__(self, provider_name: str, outcomes: list[pd.DataFrame | MarketDataProviderError]) -> None:
        self.provider_name = provider_name
        self.outcomes = outcomes
        self.calls = 0

    def validate_request(self, request: MarketDataRequest) -> None:
        return None

    def fetch_ohlcv(self, request: MarketDataRequest) -> pd.DataFrame:
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, MarketDataProviderError):
            raise outcome
        return outcome.copy()

    def fetch_metadata(self, request: MarketDataRequest) -> AssetMetadata:
        return AssetMetadata(request.symbol, f"{self.provider_name} metadata", asset_class=request.asset_class, adjustment_mode="unadjusted")


def test_local_csv_provider_and_yahoo_adapter_normalize_without_live_internet() -> None:
    local = LocalCSVProvider().fetch_ohlcv(MarketDataRequest("EXAMPLE", "2024-01-01", "2024-03-01", source_path=str(PROJECT_ROOT / "data/raw/example_ohlcv.csv")))
    assert list(local.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    payload = {"chart": {"result": [{"timestamp": [1704067200, 1704153600], "meta": {"longName": "Apple Inc.", "exchangeName": "NASDAQ", "currency": "USD", "exchangeTimezoneName": "America/New_York"}, "indicators": {"quote": [{"open": [10, 11], "high": [11, 12], "low": [9, 10], "close": [10.5, 11.5], "volume": [100, 110]}]}}], "error": None}}
    provider = YahooFinanceProvider(lambda _: json.dumps(payload).encode("utf-8"))
    frame = provider.fetch_ohlcv(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03"))
    assert len(frame) == 2 and provider.fetch_metadata(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03")).adjustment_mode == "unadjusted"
    with pytest.raises(MarketDataProviderError, match="daily"):
        provider.fetch_ohlcv(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03", interval="1h"))
    stooq = StooqProvider(lambda _: b"Date,Open,High,Low,Close,Volume\n2024-01-02,10,11,9,10.5,100\n")
    assert list(stooq.fetch_ohlcv(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03")).columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def _twelve_payload(*, status: str = "ok", values: object | None = None, **extra: object) -> dict[str, object]:
    return {
        "status": status,
        "meta": {"symbol": "AAPL", "instrument_name": "Apple Inc.", "exchange": "NASDAQ", "currency": "USD", "exchange_timezone": "America/New_York"},
        "values": values if values is not None else [
            {"datetime": "2022-01-04", "open": "180.00", "high": "182.00", "low": "179.00", "close": "181.00", "volume": "1000"},
            {"datetime": "2022-01-03", "open": "178.00", "high": "181.00", "low": "177.00", "close": "180.00", "volume": "1100"},
        ],
        **extra,
    }


def test_twelve_data_daily_ohlcv_normalizes_and_preserves_provider_metadata() -> None:
    requested_urls: list[str] = []

    def response(url: str) -> bytes:
        requested_urls.append(url)
        return json.dumps(_twelve_payload()).encode("utf-8")

    request = MarketDataRequest("AAPL", "2022-01-01", "2022-01-05")
    provider = TwelveDataProvider(api_key="test-key", http_get=response)
    frame = provider.fetch_ohlcv(request)
    metadata = provider.fetch_metadata(request)

    assert list(frame.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert frame["timestamp"].tolist() == ["2022-01-03", "2022-01-04"]
    assert "interval=1day" in requested_urls[0] and "start_date=2022-01-01" in requested_urls[0]
    assert metadata.provider_symbol == "AAPL"
    assert metadata.adjustment_mode == "provider_adjustment_unspecified"


@pytest.mark.parametrize(("payload", "expected_code", "expected_status", "retryable"), [
    ({"status": "error", "code": 401, "message": "Invalid API key"}, "INVALID_API_KEY", 401, False),
    ({"status": "error", "code": 429, "message": "API request limit reached"}, "RATE_LIMIT", 429, True),
    ({"status": "error", "code": 400, "message": "The symbol DOESNOTEXIST does not exist."}, "SYMBOL_NOT_FOUND", 400, False),
])
def test_twelve_data_structures_key_rate_limit_and_symbol_errors_without_secret_leakage(
    payload: dict[str, object], expected_code: str, expected_status: int, retryable: bool,
) -> None:
    secret = "unit-test-secret-must-not-appear"
    provider = TwelveDataProvider(api_key=secret, http_get=lambda _: json.dumps(payload).encode("utf-8"))

    with pytest.raises(MarketDataProviderError) as raised:
        provider.fetch_ohlcv(MarketDataRequest("AAPL", "2022-01-01", "2023-01-01"))

    assert raised.value.code == expected_code
    assert raised.value.status == expected_status
    assert raised.value.retryable is retryable
    assert secret not in str(raised.value)
    assert secret not in str(raised.value.details())


def test_twelve_data_rejects_malformed_response_before_persistence() -> None:
    malformed = _twelve_payload(values=[{"datetime": "2022-01-03", "open": "178.00"}])
    provider = TwelveDataProvider(api_key="test-key", http_get=lambda _: json.dumps(malformed).encode("utf-8"))

    with pytest.raises(MarketDataProviderError) as raised:
        provider.fetch_ohlcv(MarketDataRequest("AAPL", "2022-01-01", "2023-01-01"))

    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


def test_twelve_data_network_failure_is_retryable_and_secret_safe() -> None:
    secret = "unit-test-secret-must-not-appear"

    def unavailable(_: str) -> bytes:
        raise URLError("temporary network failure")

    with pytest.raises(MarketDataProviderError) as raised:
        TwelveDataProvider(api_key=secret, http_get=unavailable).fetch_ohlcv(
            MarketDataRequest("AAPL", "2022-01-01", "2023-01-01")
        )

    assert raised.value.code == "PROVIDER_UNAVAILABLE"
    assert raised.value.retryable is True
    assert secret not in str(raised.value)


def test_auto_uses_twelve_then_falls_back_and_persists_actual_provider_provenance(tmp_path: Path) -> None:
    twelve = TwelveDataProvider(
        api_key="test-key",
        http_get=lambda _: json.dumps({"status": "error", "code": 429, "message": "API request limit reached"}).encode("utf-8"),
    )
    yahoo = SequencedProvider("yahoo_finance", [_frame()])
    stooq = SequencedProvider("stooq", [_frame(close=11.0)])
    manager = DatasetManager(
        DatasetRegistry(Database(tmp_path / "datasets.db")),
        tmp_path / "cache",
        ProviderRegistry((twelve, yahoo, stooq)),
        max_attempts=1,
        sleep=lambda _: None,
    )

    result = manager.fetch("auto", MarketDataRequest("AAPL", "2022-01-01", "2023-01-01"))

    assert result.actual_provider == "yahoo_finance" and result.fallback_used
    assert yahoo.calls == 1 and stooq.calls == 0
    assert result.attempts[0]["provider"] == "twelve_data"
    assert result.dataset.metadata.requested_provider == "auto"
    assert result.dataset.metadata.actual_provider == "yahoo_finance"
    assert result.dataset.metadata.provider_symbol == "AAPL"
    assert result.dataset.metadata.requested_interval == "1d"


def test_auto_skips_unconfigured_twelve_data_and_uses_existing_provider_order(tmp_path: Path) -> None:
    twelve = TwelveDataProvider(api_key="", http_get=lambda _: pytest.fail("unconfigured provider must not be called"))
    yahoo = SequencedProvider("yahoo_finance", [_frame()])
    manager = DatasetManager(
        DatasetRegistry(Database(tmp_path / "datasets.db")), tmp_path / "cache", ProviderRegistry((twelve, yahoo)), sleep=lambda _: None,
    )

    result = manager.fetch("auto", MarketDataRequest("AAPL", "2022-01-01", "2023-01-01"))

    assert result.actual_provider == "yahoo_finance" and not result.fallback_used


def test_twelve_data_provenance_is_persisted_with_the_immutable_dataset_revision(tmp_path: Path) -> None:
    provider = TwelveDataProvider(api_key="test-key", http_get=lambda _: json.dumps(_twelve_payload()).encode("utf-8"))
    registry = DatasetRegistry(Database(tmp_path / "datasets.db"))
    manager = DatasetManager(registry, tmp_path / "cache", ProviderRegistry((provider,)), sleep=lambda _: None)

    result = manager.fetch("twelve_data", MarketDataRequest("AAPL", "2022-01-01", "2023-01-01"))
    persisted = registry.latest(result.dataset.dataset_id)

    assert persisted.metadata.requested_provider == "twelve_data"
    assert persisted.metadata.actual_provider == "twelve_data"
    assert persisted.metadata.provider_symbol == "AAPL"
    assert persisted.metadata.requested_date_range == {"start_date": "2022-01-01", "end_date": "2023-01-01"}
    assert persisted.metadata.requested_interval == "1d"
    assert persisted.metadata.fetch_timestamp is not None


def test_auto_reports_structured_failure_when_twelve_data_and_fallback_both_fail(tmp_path: Path) -> None:
    twelve = TwelveDataProvider(
        api_key="test-key",
        http_get=lambda _: json.dumps({"status": "error", "code": 429, "message": "API request limit reached"}).encode("utf-8"),
    )
    yahoo = SequencedProvider("yahoo_finance", [MarketDataProviderError("PROVIDER_UNAVAILABLE", "Yahoo unavailable", provider="yahoo_finance", status=503, retryable=True)])
    manager = DatasetManager(
        DatasetRegistry(Database(tmp_path / "datasets.db")), tmp_path / "cache", ProviderRegistry((twelve, yahoo)), max_attempts=1, sleep=lambda _: None,
    )

    with pytest.raises(MarketDataProviderError) as raised:
        manager.fetch("auto", MarketDataRequest("AAPL", "2022-01-01", "2023-01-01"))

    assert raised.value.code == "ALL_PROVIDERS_FAILED"
    assert raised.value.details()["provider"] == "auto"
    assert "twelve_data: The Twelve Data rate limit was reached." in str(raised.value.details()["reason"])
    assert "yahoo_finance: Yahoo unavailable" in str(raised.value.details()["reason"])


def test_twelve_data_cache_hit_avoids_a_second_provider_request(tmp_path: Path) -> None:
    calls = 0

    def response(_: str) -> bytes:
        nonlocal calls
        calls += 1
        return json.dumps(_twelve_payload()).encode("utf-8")

    provider = TwelveDataProvider(api_key="test-key", http_get=response)
    manager = DatasetManager(
        DatasetRegistry(Database(tmp_path / "datasets.db")), tmp_path / "cache", ProviderRegistry((provider,)), sleep=lambda _: None,
    )
    request = MarketDataRequest("AAPL", "2022-01-01", "2022-01-05")
    first = manager.fetch("twelve_data", request)
    cached = manager.fetch("twelve_data", request)

    assert not first.cache_hit and cached.cache_hit
    assert calls == 1 and cached.actual_provider == "twelve_data"


@pytest.mark.parametrize(("failure", "expected_code", "expected_status"), [
    (HTTPError("https://example.test", 429, "rate limited", None, None), "RATE_LIMIT", 429),
    (HTTPError("https://example.test", 503, "unavailable", None, None), "PROVIDER_UNAVAILABLE", 503),
    (URLError("temporary network failure"), "PROVIDER_UNAVAILABLE", None),
])
def test_yahoo_transient_transport_errors_are_structured_and_retryable(
    failure: BaseException, expected_code: str, expected_status: int | None,
) -> None:
    def failed_request(_: str) -> bytes:
        raise failure

    with pytest.raises(MarketDataProviderError) as raised:
        YahooFinanceProvider(failed_request).fetch_ohlcv(MarketDataRequest("AAPL", "2024-01-01", "2024-01-03"))

    assert raised.value.code == expected_code
    assert raised.value.details()["status"] == expected_status
    assert raised.value.details()["retryable"] is True


def test_auto_provider_uses_yahoo_success_and_persists_provenance(tmp_path: Path) -> None:
    yahoo = SequencedProvider("yahoo_finance", [_frame()])
    stooq = SequencedProvider("stooq", [_frame(close=11.0)])
    registry = DatasetRegistry(Database(tmp_path / "datasets.db"))
    manager = DatasetManager(registry, tmp_path / "cache", ProviderRegistry((yahoo, stooq)), max_attempts=2, sleep=lambda _: None)

    result = manager.fetch("auto", MarketDataRequest("AAPL", "2024-01-01", "2024-01-10"))

    assert result.actual_provider == "yahoo_finance" and not result.fallback_used
    assert yahoo.calls == 1 and stooq.calls == 0
    assert result.dataset.metadata.requested_provider == "auto"
    assert result.dataset.metadata.actual_provider == "yahoo_finance"
    assert result.dataset.metadata.requested_date_range == {"start_date": "2024-01-01", "end_date": "2024-01-10"}
    assert result.dataset.metadata.fetch_timestamp is not None


def test_auto_retries_yahoo_rate_limit_then_uses_stooq_fallback(tmp_path: Path) -> None:
    rate_limit = MarketDataProviderError("RATE_LIMIT", "Yahoo Finance request failed with HTTP 429.", provider="yahoo_finance", status=429, retryable=True)
    yahoo = SequencedProvider("yahoo_finance", [rate_limit])
    stooq = SequencedProvider("stooq", [_frame(close=11.0)])
    manager = DatasetManager(
        DatasetRegistry(Database(tmp_path / "datasets.db")), tmp_path / "cache", ProviderRegistry((yahoo, stooq)),
        max_attempts=2, retry_backoff_seconds=0.01, sleep=lambda _: None,
    )

    result = manager.fetch("auto", MarketDataRequest("AAPL", "2024-01-01", "2024-01-10"))

    assert result.actual_provider == "stooq" and result.fallback_used
    assert yahoo.calls == 2 and stooq.calls == 1
    assert [attempt["status"] for attempt in result.attempts] == [429, 429]
    assert result.dataset.metadata.requested_provider == "auto"
    assert result.dataset.metadata.actual_provider == "stooq"


def test_auto_reports_structured_error_when_yahoo_and_fallback_fail(tmp_path: Path) -> None:
    yahoo = SequencedProvider("yahoo_finance", [MarketDataProviderError("RATE_LIMIT", "Yahoo rate limited", provider="yahoo_finance", status=429, retryable=True)])
    stooq = SequencedProvider("stooq", [MarketDataProviderError("PROVIDER_UNAVAILABLE", "Stooq unavailable", provider="stooq", status=503, retryable=True)])
    manager = DatasetManager(DatasetRegistry(Database(tmp_path / "datasets.db")), tmp_path / "cache", ProviderRegistry((yahoo, stooq)), max_attempts=1, sleep=lambda _: None)

    with pytest.raises(MarketDataProviderError) as failure:
        manager.fetch("auto", MarketDataRequest("AAPL", "2024-01-01", "2024-01-10"))

    assert failure.value.code == "ALL_PROVIDERS_FAILED"
    assert failure.value.details() == {
        "provider": "auto", "status": 503, "reason": "yahoo_finance: Yahoo rate limited; stooq: Stooq unavailable",
        "retryable": True, "fallback_used": True,
    }


def test_auto_cache_hit_avoids_repeating_provider_requests(tmp_path: Path) -> None:
    yahoo = SequencedProvider("yahoo_finance", [_frame()])
    stooq = SequencedProvider("stooq", [_frame(close=11.0)])
    manager = DatasetManager(DatasetRegistry(Database(tmp_path / "datasets.db")), tmp_path / "cache", ProviderRegistry((yahoo, stooq)), sleep=lambda _: None)
    request = MarketDataRequest("AAPL", "2024-01-01", "2024-01-10")

    first = manager.fetch("auto", request)
    cached = manager.fetch("auto", request)

    assert not first.cache_hit and cached.cache_hit
    assert yahoo.calls == 1 and stooq.calls == 0
    assert cached.actual_provider == "yahoo_finance"


def test_auto_and_explicit_provider_keep_distinct_dataset_identities(tmp_path: Path) -> None:
    yahoo = SequencedProvider("yahoo_finance", [_frame()])
    stooq = SequencedProvider("stooq", [_frame(close=11.0)])
    manager = DatasetManager(DatasetRegistry(Database(tmp_path / "datasets.db")), tmp_path / "cache", ProviderRegistry((yahoo, stooq)), sleep=lambda _: None)
    request = MarketDataRequest("AAPL", "2024-01-01", "2024-01-10")

    explicit = manager.fetch("yahoo_finance", request)
    automatic = manager.fetch("auto", request)

    assert explicit.dataset.dataset_id == "DATA-YAHOO-FINANCE-AAPL-1D"
    assert automatic.dataset.dataset_id == "DATA-AUTO-AAPL-1D"
    assert automatic.dataset.provider == "yahoo_finance"


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
