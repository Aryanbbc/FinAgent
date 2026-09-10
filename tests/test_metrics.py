from __future__ import annotations

import math

import pandas as pd

from finagent.evaluation.metrics import calculate_metrics, calculate_trade_activity


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


def test_metrics_include_trade_frequency_diagnostics_when_timestamps_are_available() -> None:
    curve = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC"),
            "equity": [100.0, 100.0, 105.0, 105.0, 110.0],
        }
    )
    trades = pd.DataFrame(
        {
            "timestamp": [curve["timestamp"].iloc[0], curve["timestamp"].iloc[2]],
            "side": ["BUY", "SELL"],
            "price": [100.0, 105.0],
            "quantity": [1.0, 1.0],
            "trade_return": [None, 0.05],
            "realized_pnl": [None, 5.0],
        }
    )

    metrics = calculate_metrics(curve, trades, annualization_factor=2)

    assert metrics["position_changes"] == 2
    assert metrics["trades_per_year"] == 0.5
    assert metrics["average_holding_period_bars"] == 2.0


def test_trade_activity_counts_oos_exit_holding_time_from_causal_training_entry() -> None:
    curve = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC"),
            "equity": [100.0] * 5,
        }
    )
    trades = pd.DataFrame(
        {
            "timestamp": [curve["timestamp"].iloc[0], curve["timestamp"].iloc[3]],
            "side": ["BUY", "SELL"],
            "price": [100.0, 100.0],
            "quantity": [1.0, 1.0],
        }
    )

    activity = calculate_trade_activity(
        trades,
        curve,
        annualization_factor=2,
        start_timestamp=curve["timestamp"].iloc[2],
        observation_periods=2,
    )

    assert activity == {"position_changes": 1, "trades_per_year": 1.0, "average_holding_period_bars": 3.0}
