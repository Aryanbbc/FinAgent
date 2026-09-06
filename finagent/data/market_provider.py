"""Provider abstraction and local/Yahoo historical-data adapters."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
from finagent.data.models import AssetMetadata, MarketDataRequest


class MarketDataProviderError(RuntimeError):
    """A clear provider-level failure suitable for CLI and API presentation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MarketDataProvider(ABC):
    """Provider-neutral, historical-only OHLCV source contract."""

    provider_name: str

    @abstractmethod
    def validate_request(self, request: MarketDataRequest) -> None:
        """Reject unsupported symbols, dates, or intervals before a network call."""

    @abstractmethod
    def fetch_ohlcv(self, request: MarketDataRequest) -> pd.DataFrame:
        """Fetch raw historical OHLCV; callers normalize it before persistence."""

    @abstractmethod
    def fetch_metadata(self, request: MarketDataRequest) -> AssetMetadata:
        """Return optional asset metadata without making research logic depend on it."""


class LocalCSVProvider(MarketDataProvider):
    """Backward-compatible local CSV provider for existing FinAgent datasets."""

    provider_name = "local_csv"

    def validate_request(self, request: MarketDataRequest) -> None:
        if request.interval != "1d":
            raise MarketDataProviderError("UNSUPPORTED_INTERVAL", "LocalCSVProvider currently supports daily (1d) data only.")
        if not request.source_path:
            raise MarketDataProviderError("SOURCE_REQUIRED", "LocalCSVProvider requires source_path.")
        if not Path(request.source_path).is_file():
            raise MarketDataProviderError("SOURCE_NOT_FOUND", f"Local CSV file not found: {request.source_path}")

    def fetch_ohlcv(self, request: MarketDataRequest) -> pd.DataFrame:
        self.validate_request(request)
        # The V0.1 CSVDataLoader remains strict and unchanged for legacy runs.
        # V0.8 intentionally returns raw CSV here so the configured data-quality
        # policy can report/reject/drop/forward-fill before registry persistence.
        return pd.read_csv(str(request.source_path))

    def fetch_metadata(self, request: MarketDataRequest) -> AssetMetadata:
        return AssetMetadata(symbol=request.symbol, name=Path(request.source_path or request.symbol).stem, asset_class=request.asset_class, adjustment_mode="unknown")


class YahooFinanceProvider(MarketDataProvider):
    """Small public Yahoo chart adapter, isolated from the research engine and injectable for tests."""

    provider_name = "yahoo_finance"

    def __init__(self, http_get: Callable[[str], bytes] | None = None) -> None:
        self._http_get = http_get or self._default_get
        self._last_metadata: dict[str, object] = {}

    def validate_request(self, request: MarketDataRequest) -> None:
        if not request.symbol or any(character.isspace() for character in request.symbol):
            raise MarketDataProviderError("INVALID_SYMBOL", "A non-empty symbol without whitespace is required.")
        if request.interval != "1d":
            raise MarketDataProviderError("UNSUPPORTED_INTERVAL", "YahooFinanceProvider currently supports daily (1d) data only.")
        try:
            start = datetime.fromisoformat(request.start_date).replace(tzinfo=UTC)
            end = datetime.fromisoformat(request.end_date).replace(tzinfo=UTC)
        except ValueError as error:
            raise MarketDataProviderError("INVALID_DATE", "start_date and end_date must be ISO dates.") from error
        if end <= start:
            raise MarketDataProviderError("INVALID_DATE_RANGE", "end_date must be later than start_date.")

    def fetch_ohlcv(self, request: MarketDataRequest) -> pd.DataFrame:
        self.validate_request(request)
        start = int(datetime.fromisoformat(request.start_date).replace(tzinfo=UTC).timestamp())
        end = int(datetime.fromisoformat(request.end_date).replace(tzinfo=UTC).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(request.symbol)}?period1={start}&period2={end}&interval=1d"
        payload = self._fetch_json(url)
        chart = payload.get("chart", {})
        error = chart.get("error")
        if error:
            raise MarketDataProviderError("PROVIDER_ERROR", str(error.get("description", "Yahoo Finance returned an error.")))
        result = chart.get("result") or []
        if not result:
            raise MarketDataProviderError("EMPTY_RESULT", f"No historical data returned for {request.symbol}.")
        item = result[0]
        timestamps = item.get("timestamp") or []
        quote_rows = (item.get("indicators", {}).get("quote") or [{}])[0]
        if not timestamps or not quote_rows:
            raise MarketDataProviderError("EMPTY_RESULT", f"No OHLCV rows returned for {request.symbol}.")
        self._last_metadata = dict(item.get("meta") or {})
        frame = pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quote_rows.get("open", []), "high": quote_rows.get("high", []), "low": quote_rows.get("low", []),
            "close": quote_rows.get("close", []), "volume": quote_rows.get("volume", []),
        })
        if frame.empty:
            raise MarketDataProviderError("EMPTY_RESULT", f"No usable OHLCV rows returned for {request.symbol}.")
        return frame

    def fetch_metadata(self, request: MarketDataRequest) -> AssetMetadata:
        meta = self._last_metadata
        return AssetMetadata(
            symbol=request.symbol,
            name=self._string(meta.get("longName") or meta.get("shortName")),
            exchange=self._string(meta.get("exchangeName") or meta.get("fullExchangeName")),
            currency=self._string(meta.get("currency")),
            asset_class=request.asset_class,
            timezone=self._string(meta.get("exchangeTimezoneName")) or "UTC",
            # The adapter intentionally uses quote.close rather than adjusted close.
            adjustment_mode="unadjusted",
        )

    @staticmethod
    def _string(value: object) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _default_get(url: str) -> bytes:
        try:
            with urlopen(Request(url, headers={"User-Agent": "FinAgent/0.8 historical-research"}), timeout=20) as response:
                return response.read()
        except HTTPError as error:
            code = "SYMBOL_NOT_FOUND" if error.code == 404 else "RATE_LIMIT" if error.code == 429 else "PROVIDER_UNAVAILABLE"
            raise MarketDataProviderError(code, f"Yahoo Finance request failed with HTTP {error.code}.") from error
        except URLError as error:
            raise MarketDataProviderError("PROVIDER_UNAVAILABLE", f"Yahoo Finance is unavailable: {error.reason}") from error

    def _fetch_json(self, url: str) -> dict[str, object]:
        try:
            return dict(json.loads(self._http_get(url).decode("utf-8")))
        except MarketDataProviderError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MarketDataProviderError("PROVIDER_INVALID_RESPONSE", "Yahoo Finance returned an invalid response.") from error


class ProviderRegistry:
    """Lookup table for pluggable local historical providers."""

    def __init__(self, providers: tuple[MarketDataProvider, ...] | None = None) -> None:
        self._providers = {provider.provider_name: provider for provider in (providers or (LocalCSVProvider(), YahooFinanceProvider()))}

    def get(self, name: str) -> MarketDataProvider:
        try:
            return self._providers[name]
        except KeyError as error:
            raise MarketDataProviderError("UNKNOWN_PROVIDER", f"Unknown historical data provider: {name}") from error

    def describe(self) -> list[dict[str, object]]:
        return [
            {"provider": name, "historical_only": True, "intervals": ["1d"], "requires_credentials": False}
            for name in sorted(self._providers)
        ]
