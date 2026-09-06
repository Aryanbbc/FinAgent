"""Single-asset long-only portfolio accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class Trade:
    """An executed simulated order and the resulting portfolio state."""

    timestamp: pd.Timestamp
    side: str
    price: float
    quantity: float
    transaction_cost: float
    portfolio_value: float
    realized_pnl: float | None = None
    trade_return: float | None = None

    def to_record(self) -> dict[str, object]:
        record = asdict(self)
        record["timestamp"] = self.timestamp.isoformat()
        return record


@dataclass
class Portfolio:
    """Tracks cash, a single long holding, and realized/unrealized P&L."""

    starting_capital: float
    cash: float | None = None
    holdings: float = 0.0
    entry_price: float | None = None
    realized_pnl: float = 0.0
    _open_cost_basis: float = 0.0

    def __post_init__(self) -> None:
        if self.starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        if self.cash is None:
            self.cash = float(self.starting_capital)

    @property
    def position(self) -> int:
        return int(self.holdings > 0)

    @property
    def unrealized_pnl(self) -> float:
        """Use ``mark_to_market`` to calculate an up-to-date value."""
        return getattr(self, "_unrealized_pnl", 0.0)

    def value(self, price: float) -> float:
        return float(self.cash) + (self.holdings * price)

    def mark_to_market(self, price: float) -> None:
        self._unrealized_pnl = (self.holdings * price) - self._open_cost_basis

    def buy(self, timestamp: pd.Timestamp, price: float, quantity: float, transaction_cost: float) -> Trade:
        if quantity <= 0:
            raise ValueError("Buy quantity must be positive")
        notional = price * quantity
        total_cost = notional + transaction_cost
        if total_cost > float(self.cash) + 1e-9:
            raise ValueError("Insufficient cash for simulated buy")
        previous_holdings = self.holdings
        previous_entry_notional = (self.entry_price or 0.0) * previous_holdings
        self.cash = float(self.cash) - total_cost
        self.holdings += quantity
        self.entry_price = (previous_entry_notional + notional) / self.holdings
        self._open_cost_basis += total_cost
        self.mark_to_market(price)
        return Trade(timestamp, "BUY", price, quantity, transaction_cost, self.value(price))

    def sell(self, timestamp: pd.Timestamp, price: float, quantity: float, transaction_cost: float) -> Trade:
        if quantity <= 0 or quantity > self.holdings + 1e-9:
            raise ValueError("Sell quantity must be positive and cannot exceed holdings")
        holdings_before_sale = self.holdings
        closed_cost_basis = self._open_cost_basis * (quantity / holdings_before_sale)
        proceeds = (price * quantity) - transaction_cost
        pnl = proceeds - closed_cost_basis
        trade_return = pnl / closed_cost_basis if closed_cost_basis else 0.0
        self.cash = float(self.cash) + proceeds
        self.holdings -= quantity
        self._open_cost_basis -= closed_cost_basis
        self.realized_pnl += pnl
        if self.holdings <= 1e-9:
            self.holdings = 0.0
            self.entry_price = None
            self._open_cost_basis = 0.0
        self.mark_to_market(price)
        return Trade(timestamp, "SELL", price, quantity, transaction_cost, self.value(price), pnl, trade_return)
