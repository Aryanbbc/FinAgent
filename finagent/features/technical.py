"""Technical indicators computed only from current and past observations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def simple_returns(close: pd.Series) -> pd.Series:
    return close.pct_change(fill_method=None)


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def rolling_volatility(returns: pd.Series, window: int, annualization_factor: int = 252) -> pd.Series:
    return returns.rolling(window=window, min_periods=window).std(ddof=1) * np.sqrt(annualization_factor)


def simple_moving_average(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window, min_periods=window).mean()


def exponential_moving_average(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def momentum(close: pd.Series, window: int) -> pd.Series:
    return close.pct_change(periods=window, fill_method=None)


def rsi(close: pd.Series, window: int) -> pd.Series:
    """Calculate a simple rolling RSI; no future observations are referenced."""
    changes = close.diff()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    average_gain = gains.rolling(window=window, min_periods=window).mean()
    average_loss = losses.rolling(window=window, min_periods=window).mean()
    relative_strength = average_gain / average_loss
    result = 100 - (100 / (1 + relative_strength))
    result = result.mask((average_loss == 0) & (average_gain > 0), 100.0)
    return result.mask((average_loss == 0) & (average_gain == 0), 50.0)


def rolling_volume_mean(volume: pd.Series, window: int) -> pd.Series:
    return volume.rolling(window=window, min_periods=window).mean()


def volume_change(volume: pd.Series) -> pd.Series:
    return volume.pct_change(fill_method=None)
