"""Rolling z-score mean-reversion baseline strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finagent.strategies.base import Signal, Strategy


@dataclass(frozen=True)
class MeanReversionStrategy(Strategy):
    """Enter after a downward deviation and exit once price mean-reverts."""

    lookback_window: int = 20
    entry_zscore: float = -1.5
    exit_zscore: float = 0.0
    name: str = "mean_reversion"

    def __post_init__(self) -> None:
        if self.lookback_window < 2:
            raise ValueError("lookback_window must be at least 2")
        if self.entry_zscore >= self.exit_zscore:
            raise ValueError("entry_zscore must be lower than exit_zscore")

    def generate_signal(self, market_state: pd.DataFrame) -> Signal:
        if len(market_state) < self.lookback_window:
            return Signal.HOLD
        rolling_close = market_state["close"].iloc[-self.lookback_window :]
        standard_deviation = rolling_close.std(ddof=0)
        if standard_deviation == 0:
            return Signal.HOLD
        zscore = (rolling_close.iloc[-1] - rolling_close.mean()) / standard_deviation
        if zscore <= self.entry_zscore:
            return Signal.LONG
        if zscore >= self.exit_zscore:
            return Signal.EXIT
        return Signal.HOLD

    def parameters(self) -> dict[str, float | int]:
        return {
            "lookback_window": self.lookback_window,
            "entry_zscore": self.entry_zscore,
            "exit_zscore": self.exit_zscore,
        }
