"""Simple price-momentum baseline strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finagent.strategies.base import Signal, Strategy


@dataclass(frozen=True)
class MomentumStrategy(Strategy):
    """Enter on positive lookback return and exit on a configurable negative return."""

    lookback_window: int = 20
    entry_threshold: float = 0.0
    exit_threshold: float = 0.0
    name: str = "momentum"

    def __post_init__(self) -> None:
        if self.lookback_window < 1:
            raise ValueError("lookback_window must be positive")
        if self.exit_threshold > self.entry_threshold:
            raise ValueError("exit_threshold cannot exceed entry_threshold")

    def generate_signal(self, market_state: pd.DataFrame) -> Signal:
        if len(market_state) <= self.lookback_window:
            return Signal.HOLD
        close = market_state["close"]
        observed_return = (close.iloc[-1] / close.iloc[-1 - self.lookback_window]) - 1
        if observed_return > self.entry_threshold:
            return Signal.LONG
        if observed_return < self.exit_threshold:
            return Signal.EXIT
        return Signal.HOLD

    def parameters(self) -> dict[str, float | int]:
        return {
            "lookback_window": self.lookback_window,
            "entry_threshold": self.entry_threshold,
            "exit_threshold": self.exit_threshold,
        }
