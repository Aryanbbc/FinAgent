"""Moving-average crossover baseline strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finagent.strategies.base import Signal, Strategy


@dataclass(frozen=True)
class MovingAverageCrossoverStrategy(Strategy):
    """Go long when the fast average is above the slow average; otherwise exit."""

    fast_window: int = 20
    slow_window: int = 50
    name: str = "moving_average"

    def __post_init__(self) -> None:
        if self.fast_window < 1 or self.slow_window <= self.fast_window:
            raise ValueError("slow_window must be greater than fast_window, and both must be positive")

    def generate_signal(self, market_state: pd.DataFrame) -> Signal:
        if len(market_state) < self.slow_window:
            return Signal.HOLD
        close = market_state["close"]
        fast_average = close.iloc[-self.fast_window :].mean()
        slow_average = close.iloc[-self.slow_window :].mean()
        if fast_average > slow_average:
            return Signal.LONG
        if fast_average < slow_average:
            return Signal.EXIT
        return Signal.HOLD

    def parameters(self) -> dict[str, int]:
        return {"fast_window": self.fast_window, "slow_window": self.slow_window}
