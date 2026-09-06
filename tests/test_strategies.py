from __future__ import annotations

import pandas as pd

from finagent.strategies.base import Signal
from finagent.strategies.mean_reversion import MeanReversionStrategy
from finagent.strategies.momentum import MomentumStrategy
from finagent.strategies.moving_average import MovingAverageCrossoverStrategy


def _market_state(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": closes})


def test_moving_average_strategy_signals_trend_direction() -> None:
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    assert strategy.generate_signal(_market_state([1.0, 2.0, 3.0])) == Signal.LONG
    assert strategy.generate_signal(_market_state([3.0, 2.0, 1.0])) == Signal.EXIT


def test_momentum_strategy_signals_from_observed_return() -> None:
    strategy = MomentumStrategy(lookback_window=2, entry_threshold=0.02, exit_threshold=-0.02)
    assert strategy.generate_signal(_market_state([100.0, 100.0, 105.0])) == Signal.LONG
    assert strategy.generate_signal(_market_state([100.0, 100.0, 95.0])) == Signal.EXIT


def test_mean_reversion_strategy_enters_below_mean_and_exits_after_reversion() -> None:
    strategy = MeanReversionStrategy(lookback_window=4, entry_zscore=-1.0, exit_zscore=0.0)
    assert strategy.generate_signal(_market_state([100.0, 100.0, 100.0, 90.0])) == Signal.LONG
    assert strategy.generate_signal(_market_state([100.0, 100.0, 100.0, 110.0])) == Signal.EXIT
