"""Feature calculator for rule-based regime analysis without look-ahead bias."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import pandas as pd

from finagent.regime.models import RegimeFeatureValues


@dataclass(frozen=True)
class RegimeFeatureConfig:
    """Lookback windows used to calculate causal regime features."""

    return_window: int = 20
    volatility_window: int = 20
    moving_average_window: int = 20
    moving_average_slope_window: int = 5
    momentum_window: int = 10
    drawdown_window: int = 60
    annualization_factor: int = 252

    def __post_init__(self) -> None:
        if any(
            window < 1
            for window in (
                self.return_window,
                self.volatility_window,
                self.moving_average_window,
                self.moving_average_slope_window,
                self.momentum_window,
                self.drawdown_window,
            )
        ):
            raise ValueError("All regime feature windows must be positive")
        if self.annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")


class RegimeFeatureCalculator:
    """Computes features using only the supplied historical market-state prefix."""

    def __init__(self, configuration: RegimeFeatureConfig) -> None:
        self.configuration = configuration

    def calculate(self, market_state: pd.DataFrame) -> RegimeFeatureValues:
        """Calculate values at the final row without observing any later bars."""
        if market_state.empty:
            raise ValueError("Cannot calculate regime features for an empty market state")
        if "close" not in market_state.columns:
            raise ValueError("market_state must contain a close column")
        close = market_state["close"].astype(float)
        config = self.configuration

        rolling_return = self._return(close, config.return_window)
        volatility = self._volatility(close, config.volatility_window)
        moving_average_slope = self._moving_average_slope(
            close, config.moving_average_window, config.moving_average_slope_window
        )
        momentum = self._return(close, config.momentum_window)
        drawdown = self._drawdown(close, config.drawdown_window)
        return RegimeFeatureValues(
            rolling_return=rolling_return,
            rolling_volatility=volatility,
            moving_average_slope=moving_average_slope,
            momentum=momentum,
            drawdown=drawdown,
        )

    @staticmethod
    def _return(close: pd.Series, window: int) -> float | None:
        if len(close) <= window:
            return None
        return float((close.iloc[-1] / close.iloc[-1 - window]) - 1)

    def _volatility(self, close: pd.Series, window: int) -> float | None:
        returns = close.pct_change(fill_method=None).dropna()
        if len(returns) < window:
            return None
        return float(returns.iloc[-window:].std(ddof=1) * sqrt(self.configuration.annualization_factor))

    @staticmethod
    def _moving_average_slope(close: pd.Series, moving_average_window: int, slope_window: int) -> float | None:
        if len(close) < moving_average_window + slope_window:
            return None
        current_average = close.iloc[-moving_average_window:].mean()
        previous_average = close.iloc[-moving_average_window - slope_window : -slope_window].mean()
        if previous_average == 0:
            return None
        return float((current_average / previous_average) - 1)

    @staticmethod
    def _drawdown(close: pd.Series, window: int) -> float | None:
        if len(close) < 2:
            return None
        recent_close = close.iloc[-window:]
        peak = recent_close.max()
        if peak == 0:
            return None
        return float((recent_close.iloc[-1] / peak) - 1)
