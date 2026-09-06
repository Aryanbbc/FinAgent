"""Causal sequential backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finagent.backtesting.costs import TransactionCostModel
from finagent.backtesting.execution import ExecutionSimulator
from finagent.backtesting.portfolio import Portfolio, Trade
from finagent.strategies.base import Signal, Strategy


@dataclass(frozen=True)
class BacktestResult:
    """Complete audit trail from one simulated strategy run."""

    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    final_portfolio: Portfolio


class BacktestEngine:
    """Runs a strategy one bar at a time using close-price simulated execution."""

    def __init__(
        self,
        strategy: Strategy,
        starting_capital: float,
        transaction_costs: TransactionCostModel | None = None,
        position_fraction: float = 1.0,
    ) -> None:
        if not 0 < position_fraction <= 1:
            raise ValueError("position_fraction must be between 0 and 1")
        self.strategy = strategy
        self.starting_capital = starting_capital
        self.position_fraction = position_fraction
        self.costs = transaction_costs or TransactionCostModel()
        self.execution = ExecutionSimulator(self.costs)

    def run(self, market_data: pd.DataFrame) -> BacktestResult:
        """Backtest chronologically; strategy input is restricted to each bar's history."""
        if market_data.empty:
            raise ValueError("Cannot backtest an empty dataset")
        if not market_data["timestamp"].is_monotonic_increasing:
            raise ValueError("Market data must be ordered before backtesting")

        portfolio = Portfolio(self.starting_capital)
        trades: list[Trade] = []
        curve_rows: list[dict[str, object]] = []

        for position, (_, row) in enumerate(market_data.iterrows()):
            timestamp = pd.Timestamp(row["timestamp"])
            price = float(row["close"])
            signal = Signal(self.strategy.generate_signal(market_data.iloc[: position + 1]))

            if signal == Signal.LONG and portfolio.holdings == 0:
                quantity = self.execution.maximum_buy_quantity(portfolio.cash or 0.0, price, self.position_fraction)
                if quantity:
                    cost = self.costs.calculate(price * quantity)
                    trades.append(portfolio.buy(timestamp, price, quantity, cost))
            elif signal == Signal.EXIT and portfolio.holdings > 0:
                quantity = portfolio.holdings
                cost = self.costs.calculate(price * quantity)
                trades.append(portfolio.sell(timestamp, price, quantity, cost))

            portfolio.mark_to_market(price)
            curve_rows.append(
                {
                    "timestamp": timestamp,
                    "equity": portfolio.value(price),
                    "cash": portfolio.cash,
                    "holdings": portfolio.holdings,
                    "position": portfolio.position,
                    "entry_price": portfolio.entry_price,
                    "realized_pnl": portfolio.realized_pnl,
                    "unrealized_pnl": portfolio.unrealized_pnl,
                }
            )

        trade_columns = [
            "timestamp", "side", "price", "quantity", "transaction_cost", "portfolio_value", "realized_pnl", "trade_return"
        ]
        trades_frame = pd.DataFrame([trade.to_record() for trade in trades], columns=trade_columns)
        return BacktestResult(pd.DataFrame(curve_rows), trades_frame, portfolio)
