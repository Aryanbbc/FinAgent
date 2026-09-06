"""Strict validation and normalization for OHLCV datasets."""

from __future__ import annotations

import pandas as pd


REQUIRED_OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class DataValidationError(ValueError):
    """Raised when an OHLCV dataset is unsuitable for a backtest."""


class OHLCVValidator:
    """Validates the V0.1 canonical OHLCV schema without silently repairing data."""

    required_columns = REQUIRED_OHLCV_COLUMNS

    def validate(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Return a normalized frame or raise :class:`DataValidationError`.

        Timestamps must already be sorted. Refusing to silently sort data makes a
        potentially dangerous upstream data problem visible to the researcher.
        """
        missing_columns = [column for column in self.required_columns if column not in frame.columns]
        if missing_columns:
            raise DataValidationError(f"Missing required columns: {', '.join(missing_columns)}")

        normalized = frame.loc[:, list(self.required_columns)].copy()
        try:
            normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="raise", utc=True)
        except (TypeError, ValueError) as error:
            raise DataValidationError("Invalid timestamp values") from error

        for column in ("open", "high", "low", "close", "volume"):
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

        if normalized.isna().any().any():
            columns = normalized.columns[normalized.isna().any()].tolist()
            raise DataValidationError(f"Missing or non-numeric values in: {', '.join(columns)}")

        if normalized["timestamp"].duplicated().any():
            raise DataValidationError("Duplicate timestamps are not allowed")
        if not normalized["timestamp"].is_monotonic_increasing:
            raise DataValidationError("Timestamps must be sorted in ascending order")

        price_columns = ["open", "high", "low", "close"]
        if (normalized[price_columns] <= 0).any().any():
            raise DataValidationError("OHLC prices must be positive")
        if (normalized["volume"] < 0).any():
            raise DataValidationError("Volume cannot be negative")

        invalid_high = normalized["high"] < normalized[["open", "low", "close"]].max(axis=1)
        invalid_low = normalized["low"] > normalized[["open", "high", "close"]].min(axis=1)
        if invalid_high.any() or invalid_low.any():
            raise DataValidationError("Invalid OHLC relationship: high/low bounds are inconsistent")

        return normalized.reset_index(drop=True)
