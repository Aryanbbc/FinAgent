"""Configurable simulated transaction costs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransactionCostModel:
    """Percentage and fixed fees charged per simulated order."""

    percentage_fee: float = 0.0
    fixed_fee: float = 0.0

    def __post_init__(self) -> None:
        if self.percentage_fee < 0 or self.fixed_fee < 0:
            raise ValueError("Transaction costs cannot be negative")

    def calculate(self, notional: float) -> float:
        """Return the fee for a positive order notional."""
        if notional <= 0:
            return 0.0
        return (notional * self.percentage_fee) + self.fixed_fee
