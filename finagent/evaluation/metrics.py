"""Independently usable portfolio-performance calculations."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _ratio(numerator: float, denominator: float) -> float | None:
    if not np.isfinite(denominator) or denominator == 0:
        return None
    return float(numerator / denominator)


def calculate_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame | None = None,
    annualization_factor: int = 252,
    risk_free_rate: float = 0.0,
    initial_equity: float | None = None,
) -> dict[str, Any]:
    """Calculate return, risk, drawdown, and trade metrics from an equity curve."""
    if "equity" not in equity_curve.columns or equity_curve.empty:
        raise ValueError("equity_curve must contain at least one 'equity' observation")
    if annualization_factor <= 0:
        raise ValueError("annualization_factor must be positive")

    equity = equity_curve["equity"].astype(float)
    initial_equity = float(initial_equity) if initial_equity is not None else float(equity.iloc[0])
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    ending_equity = float(equity.iloc[-1])
    total_return = (ending_equity / initial_equity) - 1
    evaluation_equity = equity
    if not np.isclose(initial_equity, float(equity.iloc[0])):
        evaluation_equity = pd.concat([pd.Series([initial_equity]), equity], ignore_index=True)
    returns = evaluation_equity.pct_change(fill_method=None).dropna()
    periods = len(returns)

    annualized_return = total_return if periods == 0 else (ending_equity / initial_equity) ** (annualization_factor / periods) - 1
    annualized_volatility = float(returns.std(ddof=1) * np.sqrt(annualization_factor)) if periods > 1 else 0.0
    per_period_risk_free_rate = risk_free_rate / annualization_factor
    excess_returns = returns - per_period_risk_free_rate
    sharpe_ratio = _ratio(
        float(excess_returns.mean() * np.sqrt(annualization_factor)), float(excess_returns.std(ddof=1))
    ) if periods > 1 else None
    downside_returns = excess_returns[excess_returns < 0]
    sortino_ratio = _ratio(
        float(excess_returns.mean() * np.sqrt(annualization_factor)), float(downside_returns.std(ddof=1))
    ) if len(downside_returns) > 1 else None
    drawdowns = (evaluation_equity / evaluation_equity.cummax()) - 1

    sell_trades = pd.DataFrame()
    if trades is not None and not trades.empty and "side" in trades.columns:
        sell_trades = trades.loc[trades["side"] == "SELL"].copy()
    closed_returns = pd.to_numeric(sell_trades.get("trade_return", pd.Series(dtype=float)), errors="coerce").dropna()
    realized_pnl = pd.to_numeric(sell_trades.get("realized_pnl", pd.Series(dtype=float)), errors="coerce").dropna()
    gains = realized_pnl[realized_pnl > 0].sum()
    losses = -realized_pnl[realized_pnl < 0].sum()
    trade_notional = 0.0
    if trades is not None and not trades.empty:
        trade_notional = float((trades["price"].astype(float) * trades["quantity"].astype(float)).sum())
    activity = _trade_activity(trades, equity_curve, annualization_factor)

    return {
        "total_return": float(total_return),
        "cumulative_return": float(total_return),
        "annualized_return": float(annualized_return),
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "maximum_drawdown": float(drawdowns.min()),
        "number_of_trades": int(len(sell_trades)),
        "win_rate": float((closed_returns > 0).mean()) if not closed_returns.empty else None,
        "average_trade_return": float(closed_returns.mean()) if not closed_returns.empty else None,
        "profit_factor": _ratio(float(gains), float(losses)) if losses > 0 else None,
        "turnover": float(trade_notional / evaluation_equity.mean()) if evaluation_equity.mean() else None,
        "position_changes": activity["position_changes"],
        "trades_per_year": activity["trades_per_year"],
        "average_holding_period_bars": activity["average_holding_period_bars"],
    }


def _trade_activity(
    trades: pd.DataFrame | None,
    equity_curve: pd.DataFrame,
    annualization_factor: int,
) -> dict[str, float | int | None]:
    """Return causal activity diagnostics without changing the legacy turnover unit."""
    if trades is None or trades.empty:
        return {"position_changes": 0, "trades_per_year": 0.0, "average_holding_period_bars": None}
    ordered = trades.copy()
    periods = max(len(equity_curve) - 1, 0)
    closed_trades = int((ordered["side"] == "SELL").sum())
    if "timestamp" not in ordered or "timestamp" not in equity_curve:
        return {
            "position_changes": int(len(ordered)),
            "trades_per_year": float(closed_trades / (periods / annualization_factor)) if periods else None,
            "average_holding_period_bars": None,
        }
    ordered["timestamp"] = pd.to_datetime(ordered["timestamp"], utc=True)
    ordered = ordered.sort_values("timestamp", kind="stable")
    curve_timestamps = pd.DatetimeIndex(pd.to_datetime(equity_curve["timestamp"], utc=True))
    timestamp_positions = {timestamp: index for index, timestamp in enumerate(curve_timestamps)}
    entry_bar: int | None = None
    holding_periods: list[int] = []
    for trade in ordered.itertuples(index=False):
        timestamp = pd.Timestamp(trade.timestamp)
        bar = timestamp_positions.get(timestamp)
        if trade.side == "BUY" and entry_bar is None and bar is not None:
            entry_bar = bar
        elif trade.side == "SELL" and entry_bar is not None and bar is not None:
            holding_periods.append(max(0, bar - entry_bar))
            entry_bar = None
    return {
        "position_changes": int(len(ordered)),
        "trades_per_year": float(closed_trades / (periods / annualization_factor)) if periods else 0.0,
        "average_holding_period_bars": float(np.mean(holding_periods)) if holding_periods else None,
    }
