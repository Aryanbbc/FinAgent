"""Provider contracts for historical market data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class HistoricalDataProvider(ABC):
    """Loads normalized OHLCV observations from a source."""

    @abstractmethod
    def load(self, source: str | Path) -> pd.DataFrame:
        """Return validated OHLCV data in chronological order."""
