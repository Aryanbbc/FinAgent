"""Order sizing rules for the V0.1 close-price execution simulator."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

from finagent.backtesting.costs import TransactionCostModel


@dataclass(frozen=True)
class ExecutionSimulator:
    """Determines affordable whole-share quantity using the configured cost model."""

    costs: TransactionCostModel

    def maximum_buy_quantity(self, cash: float, price: float, position_fraction: float = 1.0) -> float:
        """Return affordable whole shares, including percentage and fixed fees."""
        if cash <= 0 or price <= 0 or not 0 < position_fraction <= 1:
            return 0.0
        budget = cash * position_fraction
        amount_after_fixed_fee = budget - self.costs.fixed_fee
        if amount_after_fixed_fee <= 0:
            return 0.0
        return float(floor(amount_after_fixed_fee / (price * (1 + self.costs.percentage_fee))))
