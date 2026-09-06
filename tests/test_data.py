from __future__ import annotations

import pandas as pd
import pytest

from finagent.data.validator import DataValidationError, OHLCVValidator


def test_validator_returns_normalized_ohlcv(ohlcv_frame: pd.DataFrame) -> None:
    result = OHLCVValidator().validate(ohlcv_frame.assign(extra="ignored"))
    assert result.columns.tolist() == ["timestamp", "open", "high", "low", "close", "volume"]
    assert result["timestamp"].dt.tz is not None
    assert len(result) == len(ohlcv_frame)


@pytest.mark.parametrize("defect,message", [
    (lambda frame: frame.drop(columns="volume"), "Missing required columns"),
    (lambda frame: frame.assign(close=[10.5, None, 12.5, 13.5, 14.5, 13.5, 12.5, 11.5]), "Missing"),
    (lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True), "Duplicate"),
    (lambda frame: frame.iloc[[1, 0, 2, 3, 4, 5, 6, 7]].reset_index(drop=True), "sorted"),
    (lambda frame: frame.assign(low=[12.0] + frame.low.tolist()[1:]), "Invalid OHLC"),
])
def test_validator_rejects_invalid_data(ohlcv_frame: pd.DataFrame, defect, message: str) -> None:
    with pytest.raises(DataValidationError, match=message):
        OHLCVValidator().validate(defect(ohlcv_frame.copy()))
