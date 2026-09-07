"""Provider abstraction and public historical-data adapters."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Callable, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
from finagent.data.models import AssetMetadata, MarketDataRequest


class MarketDataProviderError(RuntimeError):
    """A clear provider-level failure suitable for CLI and API presentation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str | None = None,
        status: int | None = None,
        reason: str | None = None,
        retryable: bool = False,
        fallback_used: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.status = status
        self.reason = reason or message
        self.retryable = retryable
        self.fallback_used = fallback_used

    def details(self) -> dict[str, object]:
        """Stable machine-readable context for CLI/API clients and logs."""
        return {
            "provider": self.provider,
            "status": self.status,
            "reason": self.reason,
            "retryable": self.retryable,
            "fallback_used": self.fallback_used,
        }


def _request_error(provider: str, error: BaseException) -> NoReturn:
    """Map network-layer exceptions to a portable, retry-aware provider error."""
    if isinstance(error, HTTPError):
        if error.code == 404:
            raise MarketDataProviderError(
                "SYMBOL_NOT_FOUND", f"{provider} request failed with HTTP 404.", provider=provider,
                status=404, reason="The requested symbol was not found.",
            ) from error
        if error.code == 429:
            raise MarketDataProviderError(
                "RATE_LIMIT", f"{provider} request failed with HTTP 429.", provider=provider,
                status=429, reason="The provider rate limit was reached.", retryable=True,
            ) from error
        retryable = 500 <= error.code <= 599
        raise MarketDataProviderError(
            "PROVIDER_UNAVAILABLE" if retryable else "PROVIDER_HTTP_ERROR",
            f"{provider} request failed with HTTP {error.code}.", provider=provider, status=error.code,
            reason=f"HTTP {error.code} returned by the provider.", retryable=retryable,
        ) from error
    if isinstance(error, (URLError, TimeoutError, ConnectionError, OSError)):
        reason = getattr(error, "reason", error)
        raise MarketDataProviderError(
            "PROVIDER_UNAVAILABLE", f"{provider} is temporarily unavailable: {reason}", provider=provider,
            reason="Temporary network or provider availability failure.", retryable=True,
        ) from error
    raise error


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
            raise MarketDataProviderError("UNSUPPORTED_INTERVAL", "LocalCSVProvider currently supports daily (1d) data only.", provider=self.provider_name)
        if not request.source_path:
            raise MarketDataProviderError("SOURCE_REQUIRED", "LocalCSVProvider requires source_path.", provider=self.provider_name)
        if not Path(request.source_path).is_file():
            raise MarketDataProviderError("SOURCE_NOT_FOUND", f"Local CSV file not found: {request.source_path}", provider=self.provider_name)

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
            raise MarketDataProviderError("INVALID_SYMBOL", "A non-empty symbol without whitespace is required.", provider=self.provider_name)
        if request.interval != "1d":
            raise MarketDataProviderError("UNSUPPORTED_INTERVAL", "YahooFinanceProvider currently supports daily (1d) data only.", provider=self.provider_name)
        try:
            start = datetime.fromisoformat(request.start_date).replace(tzinfo=UTC)
            end = datetime.fromisoformat(request.end_date).replace(tzinfo=UTC)
        except ValueError as error:
            raise MarketDataProviderError("INVALID_DATE", "start_date and end_date must be ISO dates.", provider=self.provider_name) from error
        if end <= start:
            raise MarketDataProviderError("INVALID_DATE_RANGE", "end_date must be later than start_date.", provider=self.provider_name)

    def fetch_ohlcv(self, request: MarketDataRequest) -> pd.DataFrame:
        self.validate_request(request)
        start = int(datetime.fromisoformat(request.start_date).replace(tzinfo=UTC).timestamp())
        end = int(datetime.fromisoformat(request.end_date).replace(tzinfo=UTC).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(request.symbol)}?period1={start}&period2={end}&interval=1d"
        payload = self._fetch_json(url)
        chart = payload.get("chart", {})
        error = chart.get("error")
        if error:
            raise MarketDataProviderError("PROVIDER_ERROR", str(error.get("description", "Yahoo Finance returned an error.")), provider=self.provider_name)
        result = chart.get("result") or []
        if not result:
            raise MarketDataProviderError("EMPTY_RESULT", f"No historical data returned for {request.symbol}.", provider=self.provider_name)
        item = result[0]
        timestamps = item.get("timestamp") or []
        quote_rows = (item.get("indicators", {}).get("quote") or [{}])[0]
        if not timestamps or not quote_rows:
            raise MarketDataProviderError("EMPTY_RESULT", f"No OHLCV rows returned for {request.symbol}.", provider=self.provider_name)
        self._last_metadata = dict(item.get("meta") or {})
        frame = pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quote_rows.get("open", []), "high": quote_rows.get("high", []), "low": quote_rows.get("low", []),
            "close": quote_rows.get("close", []), "volume": quote_rows.get("volume", []),
        })
        if frame.empty:
            raise MarketDataProviderError("EMPTY_RESULT", f"No usable OHLCV rows returned for {request.symbol}.", provider=self.provider_name)
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
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as error:
            _request_error("yahoo_finance", error)

    def _fetch_json(self, url: str) -> dict[str, object]:
        try:
            return dict(json.loads(self._http_get(url).decode("utf-8")))
        except MarketDataProviderError:
            raise
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as error:
            _request_error(self.provider_name, error)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MarketDataProviderError("PROVIDER_INVALID_RESPONSE", "Yahoo Finance returned an invalid response.", provider=self.provider_name) from error


class StooqProvider(MarketDataProvider):
    """Public Stooq daily CSV adapter used as a non-brokerage Yahoo fallback.

    Stooq uses ``symbol.us`` for most US equities.  A caller may supply a
    provider-specific symbol containing a dot unchanged (for example
    ``7203.jp``); otherwise US equity notation is inferred conservatively.
    """

    provider_name = "stooq"

    def __init__(self, http_get: Callable[[str], bytes] | None = None) -> None:
        self._http_get = http_get or self._default_get

    def validate_request(self, request: MarketDataRequest) -> None:
        if not request.symbol or any(character.isspace() for character in request.symbol):
            raise MarketDataProviderError("INVALID_SYMBOL", "A non-empty symbol without whitespace is required.", provider=self.provider_name)
        if request.interval != "1d":
            raise MarketDataProviderError("UNSUPPORTED_INTERVAL", "StooqProvider currently supports daily (1d) data only.", provider=self.provider_name)
        try:
            start = datetime.fromisoformat(request.start_date).replace(tzinfo=UTC)
            end = datetime.fromisoformat(request.end_date).replace(tzinfo=UTC)
        except ValueError as error:
            raise MarketDataProviderError("INVALID_DATE", "start_date and end_date must be ISO dates.", provider=self.provider_name) from error
        if end <= start:
            raise MarketDataProviderError("INVALID_DATE_RANGE", "end_date must be later than start_date.", provider=self.provider_name)

    def fetch_ohlcv(self, request: MarketDataRequest) -> pd.DataFrame:
        self.validate_request(request)
        symbol = self._stooq_symbol(request.symbol)
        start = request.start_date.replace("-", "")
        end = request.end_date.replace("-", "")
        url = f"https://stooq.com/q/d/l/?s={quote(symbol)}&d1={start}&d2={end}&i=d"
        try:
            payload = self._http_get(url).decode("utf-8")
        except MarketDataProviderError:
            raise
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as error:
            _request_error(self.provider_name, error)
        except UnicodeDecodeError as error:
            raise MarketDataProviderError("PROVIDER_INVALID_RESPONSE", "Stooq returned an invalid response.", provider=self.provider_name) from error
        if not payload.strip() or "no data" in payload.lower():
            raise MarketDataProviderError("EMPTY_RESULT", f"No historical data returned by Stooq for {request.symbol}.", provider=self.provider_name)
        try:
            frame = pd.read_csv(StringIO(payload))
        except (pd.errors.ParserError, ValueError) as error:
            raise MarketDataProviderError("PROVIDER_INVALID_RESPONSE", "Stooq returned an invalid CSV response.", provider=self.provider_name) from error
        if frame.empty or "Date" not in frame.columns:
            raise MarketDataProviderError("EMPTY_RESULT", f"No usable OHLCV rows returned by Stooq for {request.symbol}.", provider=self.provider_name)
        return frame.rename(columns={"Date": "timestamp", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})

    def fetch_metadata(self, request: MarketDataRequest) -> AssetMetadata:
        return AssetMetadata(
            symbol=request.symbol,
            name=f"{request.symbol} (Stooq)",
            asset_class=request.asset_class,
            timezone="UTC",
            # Stooq's public CSV adjustment convention must not be inferred.
            adjustment_mode="provider_adjustment_unspecified",
        )

    @staticmethod
    def _stooq_symbol(symbol: str) -> str:
        lowered = symbol.lower()
        return lowered if "." in lowered else f"{lowered}.us"

    @staticmethod
    def _default_get(url: str) -> bytes:
        try:
            with urlopen(Request(url, headers={"User-Agent": "FinAgent/1.0 historical-research"}), timeout=20) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as error:
            _request_error("stooq", error)


class ProviderRegistry:
    """Lookup table for pluggable local historical providers."""

    auto_provider = "auto"
    auto_provider_order = ("yahoo_finance", "stooq")

    def __init__(self, providers: tuple[MarketDataProvider, ...] | None = None) -> None:
        self._providers = {
            provider.provider_name: provider
            for provider in (providers or (LocalCSVProvider(), YahooFinanceProvider(), StooqProvider()))
        }

    def get(self, name: str) -> MarketDataProvider:
        try:
            return self._providers[name]
        except KeyError as error:
            raise MarketDataProviderError("UNKNOWN_PROVIDER", f"Unknown historical data provider: {name}", provider=name) from error

    def candidates(self, name: str) -> tuple[MarketDataProvider, ...]:
        """Resolve an explicit provider or the deterministic public fallback order."""
        if name != self.auto_provider:
            return (self.get(name),)
        providers = tuple(self._providers[item] for item in self.auto_provider_order if item in self._providers)
        if not providers:
            raise MarketDataProviderError(
                "NO_AUTO_PROVIDERS", "No public providers are configured for automatic historical data fetching.",
                provider=self.auto_provider,
            )
        return providers

    def describe(self) -> list[dict[str, object]]:
        described = [
            {"provider": name, "historical_only": True, "intervals": ["1d"], "requires_credentials": False}
            for name in sorted(self._providers)
        ]
        if all(name in self._providers for name in self.auto_provider_order):
            described.insert(0, {
                "provider": self.auto_provider,
                "historical_only": True,
                "intervals": ["1d"],
                "requires_credentials": False,
            })
        return described
