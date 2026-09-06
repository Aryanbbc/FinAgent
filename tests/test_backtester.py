from __future__ import annotations

import pandas as pd

from finagent.backtesting.costs import TransactionCostModel
from finagent.backtesting.engine import BacktestEngine
from finagent.strategies.base import Signal, Strategy


class ScriptedStrategy(Strategy):
    name = "scripted"

    def __init__(self, signals: list[Signal]) -> None:
        self.signals = signals
        self.observed_lengths: list[int] = []

    def generate_signal(self, market_state: pd.DataFrame) -> Signal:
        self.observed_lengths.append(len(market_state))
        return self.signals[len(market_state) - 1]

    def parameters(self) -> dict[str, int]:
        return {}


def test_backtester_accounts_for_cash_positions_and_transaction_costs() -> None:
    market = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC"),
            "close": [10.0, 12.0, 11.0],
        }
    )
    strategy = ScriptedStrategy([Signal.LONG, Signal.EXIT, Signal.HOLD])
    result = BacktestEngine(strategy, 100.0, TransactionCostModel(percentage_fee=0.01)).run(market)

    assert result.trades["side"].tolist() == ["BUY", "SELL"]
    assert result.trades["quantity"].tolist() == [9.0, 9.0]
    assert result.trades.loc[0, "transaction_cost"] == 0.9
    assert result.trades.loc[1, "transaction_cost"] == 1.08
    assert result.final_portfolio.cash == 116.02
    assert result.final_portfolio.holdings == 0.0
    assert result.equity_curve.iloc[-1]["equity"] == 116.02


def test_backtester_only_exposes_history_through_current_bar() -> None:
    market = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC"),
            "close": [10.0, 11.0, 12.0, 13.0],
        }
    )
    strategy = ScriptedStrategy([Signal.HOLD] * 4)
    BacktestEngine(strategy, 100.0).run(market)
    assert strategy.observed_lengths == [1, 2, 3, 4]
