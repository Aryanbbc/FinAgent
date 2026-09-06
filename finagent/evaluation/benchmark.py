"""Passive buy-and-hold comparison with the same transaction-cost model."""

from __future__ import annotations

import pandas as pd

from finagent.backtesting.costs import TransactionCostModel
from finagent.backtesting.execution import ExecutionSimulator


def buy_and_hold_benchmark(
    market_data: pd.DataFrame,
    starting_capital: float,
    transaction_costs: TransactionCostModel | None = None,
) -> pd.DataFrame:
    """Return a benchmark equity curve after an initial affordable purchase.

    Like a strategy's open position, the benchmark's final holding is marked to
    market rather than force-liquidated, so both curves use the same convention.
    """
    if market_data.empty:
        raise ValueError("Cannot benchmark an empty dataset")
    costs = transaction_costs or TransactionCostModel()
    first_price = float(market_data.iloc[0]["close"])
    quantity = ExecutionSimulator(costs).maximum_buy_quantity(starting_capital, first_price)
    fee = costs.calculate(first_price * quantity)
    cash = starting_capital - (first_price * quantity) - fee
    result = market_data.loc[:, ["timestamp", "close"]].copy()
    result["benchmark_equity"] = cash + (quantity * result["close"])
    return result.loc[:, ["timestamp", "benchmark_equity"]]
