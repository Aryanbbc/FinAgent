from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def ohlcv_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC"),
            "open": [10.0, 11.0, 12.0, 13.0, 14.0, 13.0, 12.0, 11.0],
            "high": [11.0, 12.0, 13.0, 14.0, 15.0, 14.0, 13.0, 12.0],
            "low": [9.0, 10.0, 11.0, 12.0, 13.0, 12.0, 11.0, 10.0],
            "close": [10.5, 11.5, 12.5, 13.5, 14.5, 13.5, 12.5, 11.5],
            "volume": [100, 110, 120, 130, 140, 150, 160, 170],
        }
    )
