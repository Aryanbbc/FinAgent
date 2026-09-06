from __future__ import annotations

import math

import pandas as pd

from finagent.backtesting.costs import TransactionCostModel
from finagent.evaluation.benchmark import buy_and_hold_benchmark


def test_buy_and_hold_benchmark_uses_the_configured_transaction_costs() -> None:
    market = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC"),
            "close": [10.0, 12.0, 11.0],
        }
    )
    benchmark = buy_and_hold_benchmark(market, 100.0, TransactionCostModel(percentage_fee=0.01))
    assert math.isclose(benchmark.iloc[0]["benchmark_equity"], 99.1)
    assert math.isclose(benchmark.iloc[-1]["benchmark_equity"], 108.1)
