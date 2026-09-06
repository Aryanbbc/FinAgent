from __future__ import annotations

import math

import pandas as pd

from finagent.evaluation.metrics import calculate_metrics


def test_metrics_total_return_drawdown_and_trade_statistics() -> None:
    curve = pd.DataFrame({"equity": [100.0, 110.0, 99.0, 120.0]})
    trades = pd.DataFrame(
        {
            "side": ["BUY", "SELL", "BUY", "SELL"],
            "price": [100.0, 110.0, 100.0, 95.0],
            "quantity": [1.0, 1.0, 1.0, 1.0],
            "trade_return": [None, 0.1, None, -0.05],
            "realized_pnl": [None, 10.0, None, -5.0],
        }
    )
    metrics = calculate_metrics(curve, trades, annualization_factor=252)
    assert math.isclose(metrics["total_return"], 0.2)
    assert math.isclose(metrics["maximum_drawdown"], -0.1)
    assert metrics["number_of_trades"] == 2
    assert metrics["win_rate"] == 0.5
    assert math.isclose(metrics["average_trade_return"], 0.025)
    assert metrics["profit_factor"] == 2.0
    returns = curve["equity"].pct_change().dropna()
    expected_sharpe = returns.mean() / returns.std(ddof=1) * math.sqrt(252)
    assert math.isclose(metrics["sharpe_ratio"], expected_sharpe)
