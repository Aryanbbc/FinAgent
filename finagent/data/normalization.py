"""Provider-independent normalization to FinAgent's canonical OHLCV schema."""

from __future__ import annotations

import pandas as pd

from finagent.data.validator import DataValidationError, REQUIRED_OHLCV_COLUMNS


class OHLCVNormalizer:
    """Normalizes common provider column spellings without making value repairs."""

    _aliases = {
        "date": "timestamp", "datetime": "timestamp", "time": "timestamp",
        "open": "open", "high": "high", "low": "low", "close": "close",
        "adj close": "close", "adj_close": "close", "adjusted_close": "close",
        "volume": "volume",
    }

    def normalize(self, frame: pd.DataFrame) -> pd.DataFrame:
        renamed = frame.rename(columns={column: self._aliases.get(str(column).strip().lower(), str(column).strip().lower()) for column in frame.columns})
        if renamed.columns.duplicated().any():
            renamed = renamed.loc[:, ~renamed.columns.duplicated(keep="first")]
        missing = [column for column in REQUIRED_OHLCV_COLUMNS if column not in renamed.columns]
        if missing:
            raise DataValidationError(f"Missing required columns: {', '.join(missing)}")
        normalized = renamed.loc[:, list(REQUIRED_OHLCV_COLUMNS)].copy()
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce", utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce").astype(float)
        return normalized.sort_values("timestamp", kind="stable", na_position="last").reset_index(drop=True)

