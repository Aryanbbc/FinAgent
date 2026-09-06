"""Causal sequential backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finagent.agents.decision_system import AgentDecisionSystem
from finagent.agents.models import PortfolioState
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
    agent_decisions: pd.DataFrame


class BacktestEngine:
    """Runs a strategy one bar at a time using close-price simulated execution."""

    def __init__(
        self,
        strategy: Strategy,
        starting_capital: float,
        transaction_costs: TransactionCostModel | None = None,
        position_fraction: float = 1.0,
        agent_decision_system: AgentDecisionSystem | None = None,
    ) -> None:
        if not 0 < position_fraction <= 1:
            raise ValueError("position_fraction must be between 0 and 1")
        self.strategy = strategy
        self.starting_capital = starting_capital
        self.position_fraction = position_fraction
        self.costs = transaction_costs or TransactionCostModel()
        self.execution = ExecutionSimulator(self.costs)
        self.agent_decision_system = agent_decision_system

    def run(self, market_data: pd.DataFrame) -> BacktestResult:
        """Backtest chronologically; strategy input is restricted to each bar's history."""
        if market_data.empty:
            raise ValueError("Cannot backtest an empty dataset")
        if not market_data["timestamp"].is_monotonic_increasing:
            raise ValueError("Market data must be ordered before backtesting")

        portfolio = Portfolio(self.starting_capital)
        trades: list[Trade] = []
        curve_rows: list[dict[str, object]] = []
        agent_decision_records: list[dict[str, object]] = []
        peak_equity = self.starting_capital

        for position, (_, row) in enumerate(market_data.iterrows()):
            timestamp = pd.Timestamp(row["timestamp"])
            price = float(row["close"])
            market_state = market_data.iloc[: position + 1]
            portfolio.mark_to_market(price)
            pre_trade_equity = portfolio.value(price)
            peak_equity = max(peak_equity, pre_trade_equity)
            drawdown = (pre_trade_equity / peak_equity) - 1
            execution_fraction = self.position_fraction
            if self.agent_decision_system is None:
                signal = Signal(self.strategy.generate_signal(market_state))
            else:
                portfolio_state = PortfolioState(
                    timestamp=timestamp,
                    cash=float(portfolio.cash or 0.0),
                    holdings=portfolio.holdings,
                    equity=pre_trade_equity,
                    position=portfolio.position,
                    entry_price=portfolio.entry_price,
                    realized_pnl=portfolio.realized_pnl,
                    unrealized_pnl=portfolio.unrealized_pnl,
                    drawdown=drawdown,
                )
                decision = self.agent_decision_system.decide(market_state, portfolio_state)
                agent_decision_records.append(decision.to_record())
                signal = decision.execution_action.to_signal()
                if signal == Signal.LONG:
                    execution_fraction = min(self.position_fraction, decision.risk.adjusted_position_size)

            if signal == Signal.LONG and portfolio.holdings == 0 and execution_fraction > 0:
                quantity = self.execution.maximum_buy_quantity(portfolio.cash or 0.0, price, execution_fraction)
                if quantity:
                    cost = self.costs.calculate(price * quantity)
                    trades.append(portfolio.buy(timestamp, price, quantity, cost))
            elif signal == Signal.EXIT and portfolio.holdings > 0:
                quantity = portfolio.holdings
                cost = self.costs.calculate(price * quantity)
                trades.append(portfolio.sell(timestamp, price, quantity, cost))

            portfolio.mark_to_market(price)
            peak_equity = max(peak_equity, portfolio.value(price))
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
        decision_columns = [
            "timestamp",
            "technical_trend",
            "technical_momentum",
            "technical_volatility",
            "technical_rsi",
            "technical_signal_strength",
            "technical_confidence",
            "regime",
            "regime_confidence",
            "selected_strategy",
            "action",
            "execution_action",
            "proposal_confidence",
            "requested_position_size",
            "strategy_reason_codes",
            "risk_approved",
            "adjusted_position_size",
            "risk_reason_code",
        ]
        agent_decisions = pd.DataFrame(agent_decision_records, columns=decision_columns)
        return BacktestResult(pd.DataFrame(curve_rows), trades_frame, portfolio, agent_decisions)
