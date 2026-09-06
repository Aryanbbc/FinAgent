"""Configurable technical-feature pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from finagent.features import technical


class FeaturePipeline:
    """Adds enabled, causal technical indicators to an OHLCV frame."""

    def __init__(self, annualization_factor: int = 252) -> None:
        self.annualization_factor = annualization_factor

    @staticmethod
    def _options(value: Any) -> Mapping[str, Any] | None:
        if value is False or value is None:
            return None
        if value is True:
            return {}
        if isinstance(value, Mapping):
            return value
        raise ValueError("Feature configuration values must be booleans or mappings")

    def generate(self, market_data: pd.DataFrame, configuration: Mapping[str, Any]) -> pd.DataFrame:
        """Return market data augmented with indicators selected by configuration."""
        result = market_data.copy()
        returns: pd.Series | None = None

        def get_returns() -> pd.Series:
            nonlocal returns
            if returns is None:
                returns = technical.simple_returns(result["close"])
            return returns

        if self._options(configuration.get("simple_return")) is not None:
            result["simple_return"] = get_returns()
        if self._options(configuration.get("log_return")) is not None:
            result["log_return"] = technical.log_returns(result["close"])
        if (options := self._options(configuration.get("rolling_volatility"))) is not None:
            window = int(options.get("window", 20))
            result[f"rolling_volatility_{window}"] = technical.rolling_volatility(
                get_returns(), window, self.annualization_factor
            )
        if (options := self._options(configuration.get("sma"))) is not None:
            window = int(options.get("window", 20))
            result[f"sma_{window}"] = technical.simple_moving_average(result["close"], window)
        if (options := self._options(configuration.get("ema"))) is not None:
            span = int(options.get("span", 20))
            result[f"ema_{span}"] = technical.exponential_moving_average(result["close"], span)
        if (options := self._options(configuration.get("momentum"))) is not None:
            window = int(options.get("window", 20))
            result[f"momentum_{window}"] = technical.momentum(result["close"], window)
        if (options := self._options(configuration.get("rsi"))) is not None:
            window = int(options.get("window", 14))
            result[f"rsi_{window}"] = technical.rsi(result["close"], window)
        if (options := self._options(configuration.get("rolling_volume_mean"))) is not None:
            window = int(options.get("window", 20))
            result[f"rolling_volume_mean_{window}"] = technical.rolling_volume_mean(result["volume"], window)
        if self._options(configuration.get("volume_change")) is not None:
            result["volume_change"] = technical.volume_change(result["volume"])
        return result
