"""Strategy contract used by the sequential backtester."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import IntEnum

import pandas as pd


class Signal(IntEnum):
    """Standardized position instruction for a long-only V0.1 strategy."""

    EXIT = -1
    HOLD = 0
    LONG = 1


class Strategy(ABC):
    """A deterministic strategy that sees only observations through the current bar."""

    name: str

    @abstractmethod
    def generate_signal(self, market_state: pd.DataFrame) -> Signal:
        """Return a standardized signal from a chronologically ordered data slice."""

    @abstractmethod
    def parameters(self) -> dict[str, float | int]:
        """Return the reproducibility-relevant strategy parameters."""
