"""Provider abstraction for bounded recent OHLCV market monitoring."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import UTC
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import pandas as pd

from finagent.data.market_provider import MarketDataProviderError
from finagent.live.models import LiveMarketBar


def _fixed_https_get(url: str) -> bytes:
    """The live provider uses only the hard-coded Twelve Data HTTPS endpoint."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.twelvedata.com":
        raise MarketDataProviderError("PROVIDER_SECURITY_ERROR", "Provider endpoint is not an approved HTTPS destination.", provider="twelve_data")
    # Scheme and hostname are checked against a provider constant above.
    with urlopen(Request(url, headers={"User-Agent": "FinAgent/1.1 live-market-intelligence"}), timeout=20) as response:  # nosec B310
        return response.read()


class LiveMarketProvider(ABC):
    """Recent-bar source contract. Implementations never execute trades."""

    provider_name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Whether the adapter can authenticate in the current backend environment."""

    @abstractmethod
    def fetch_recent_bars(self, symbol: str, interval: str, limit: int) -> list[LiveMarketBar]:
        """Fetch a finite set of recent bars, oldest to newest."""


class TwelveDataLiveProvider(LiveMarketProvider):
    """Twelve Data polling adapter for recent OHLCV bars.

    Polling is deliberately the default because WebSocket entitlement varies by
    Twelve Data plan.  It avoids bypassing any provider restriction and keeps
    requests bounded by the configured poll interval.
    """

    provider_name = "twelve_data"
    endpoint = "https://api.twelvedata.com/time_series"
    supported_intervals = {"1min", "5min", "15min"}

    def __init__(self, api_key: str | None = None, http_get: Callable[[str], bytes] | None = None) -> None:
        self._api_key = (api_key if api_key is not None else os.getenv("TWELVE_DATA_API_KEY", "")).strip()
        self._http_get = http_get or self._default_get

    def is_available(self) -> bool:
        return bool(self._api_key)

    def fetch_recent_bars(self, symbol: str, interval: str, limit: int) -> list[LiveMarketBar]:
        if not self._api_key:
            raise MarketDataProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "Twelve Data is not configured on this backend.",
                provider=self.provider_name,
                reason="TWELVE_DATA_API_KEY is not configured on the backend.",
            )
        if not symbol or any(character.isspace() for character in symbol):
            raise MarketDataProviderError("INVALID_SYMBOL", "A non-empty symbol without whitespace is required.", provider=self.provider_name)
        if interval not in self.supported_intervals:
            raise MarketDataProviderError("UNSUPPORTED_INTERVAL", "Live Twelve Data polling supports 1min, 5min, or 15min intervals.", provider=self.provider_name)
        if not 2 <= limit <= 5_000:
            raise MarketDataProviderError("INVALID_BUFFER_SIZE", "Live buffer size must be between 2 and 5000.", provider=self.provider_name)
        url = (
            f"{self.endpoint}?symbol={quote(symbol)}&interval={quote(interval)}&outputsize={limit}"
            f"&timezone=UTC&apikey={quote(self._api_key)}"
        )
        payload = self._fetch_json(url)
        self._raise_response_error(payload)
        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise MarketDataProviderError("EMPTY_RESULT", f"No recent OHLCV bars returned for {symbol}.", provider=self.provider_name, retryable=True)
        try:
            bars = [self._bar(symbol, item) for item in values]
        except (KeyError, TypeError, ValueError) as error:
            raise MarketDataProviderError("PROVIDER_INVALID_RESPONSE", "Twelve Data returned malformed live OHLCV bars.", provider=self.provider_name) from error
        deduplicated = {bar.timestamp: bar for bar in bars}
        return [deduplicated[item] for item in sorted(deduplicated)]

    def _bar(self, symbol: str, value: object) -> LiveMarketBar:
        if not isinstance(value, dict):
            raise ValueError("bar must be an object")
        timestamp = pd.Timestamp(value["datetime"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        return LiveMarketBar(
            symbol=symbol.upper(),
            timestamp=timestamp.to_pydatetime().astimezone(UTC),
            open=float(value["open"]),
            high=float(value["high"]),
            low=float(value["low"]),
            close=float(value["close"]),
            volume=float(value["volume"]),
            provider=self.provider_name,
        )

    @staticmethod
    def _default_get(url: str) -> bytes:
        try:
            return _fixed_https_get(url)
        except HTTPError as error:
            if error.code == 429:
                raise MarketDataProviderError("RATE_LIMIT", "Twelve Data rate limit reached.", provider="twelve_data", status=429, reason="The Twelve Data rate limit was reached.", retryable=True) from error
            retryable = 500 <= error.code <= 599
            raise MarketDataProviderError("PROVIDER_UNAVAILABLE" if retryable else "PROVIDER_HTTP_ERROR", f"Twelve Data request failed with HTTP {error.code}.", provider="twelve_data", status=error.code, reason="Twelve Data returned an HTTP error.", retryable=retryable) from error
        except (URLError, TimeoutError, ConnectionError, OSError) as error:
            raise MarketDataProviderError("PROVIDER_UNAVAILABLE", "Twelve Data is temporarily unavailable.", provider="twelve_data", reason="Temporary network or provider availability failure.", retryable=True) from error

    def _fetch_json(self, url: str) -> dict[str, object]:
        try:
            payload = json.loads(self._http_get(url).decode("utf-8"))
        except MarketDataProviderError:
            raise
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as error:
            # Injectable clients follow the same safe failure contract as the
            # production urllib implementation.
            if isinstance(error, HTTPError) and error.code == 429:
                raise MarketDataProviderError("RATE_LIMIT", "Twelve Data rate limit reached.", provider=self.provider_name, status=429, reason="The Twelve Data rate limit was reached.", retryable=True) from error
            raise MarketDataProviderError("PROVIDER_UNAVAILABLE", "Twelve Data is temporarily unavailable.", provider=self.provider_name, reason="Temporary network or provider availability failure.", retryable=True) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MarketDataProviderError("PROVIDER_INVALID_RESPONSE", "Twelve Data returned an invalid response.", provider=self.provider_name) from error
        if not isinstance(payload, dict):
            raise MarketDataProviderError("PROVIDER_INVALID_RESPONSE", "Twelve Data returned an invalid response.", provider=self.provider_name)
        return payload

    def _raise_response_error(self, payload: dict[str, object]) -> None:
        if payload.get("status") != "error" and "code" not in payload:
            return
        try:
            status = int(payload["code"]) if payload.get("code") is not None else None
        except (TypeError, ValueError):
            status = None
        message = str(payload.get("message") or "Twelve Data returned an error.").lower()
        if status in {401, 403} or "api key" in message or "apikey" in message:
            raise MarketDataProviderError("INVALID_API_KEY", "Twelve Data rejected the configured API key.", provider=self.provider_name, status=status or 401, reason="The Twelve Data API key was rejected.")
        if status == 429 or "rate limit" in message or "too many" in message:
            raise MarketDataProviderError("RATE_LIMIT", "Twelve Data rate limit reached.", provider=self.provider_name, status=429, reason="The Twelve Data rate limit was reached.", retryable=True)
        if "symbol" in message and ("not found" in message or "does not exist" in message or "invalid" in message):
            raise MarketDataProviderError("SYMBOL_NOT_FOUND", "The requested symbol was not found by Twelve Data.", provider=self.provider_name, status=status or 400, reason="The requested symbol was not found.")
        if status is not None and 500 <= status <= 599:
            raise MarketDataProviderError("PROVIDER_UNAVAILABLE", "Twelve Data is temporarily unavailable.", provider=self.provider_name, status=status, reason="Temporary provider availability failure.", retryable=True)
        raise MarketDataProviderError("PROVIDER_ERROR", "Twelve Data rejected the request.", provider=self.provider_name, status=status, reason="Twelve Data returned an error for this request.")
