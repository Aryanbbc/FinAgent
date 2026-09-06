"""CSV-backed historical market-data loader."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finagent.data.provider import HistoricalDataProvider
from finagent.data.validator import OHLCVValidator


class CSVDataLoader(HistoricalDataProvider):
    """Loads a CSV file and applies the canonical OHLCV validation policy."""

    def __init__(self, validator: OHLCVValidator | None = None) -> None:
        self.validator = validator or OHLCVValidator()

    def load(self, source: str | Path) -> pd.DataFrame:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Historical data file not found: {path}")
        return self.validator.validate(pd.read_csv(path))
