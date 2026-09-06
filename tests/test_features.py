from __future__ import annotations

import math

import pandas as pd

from finagent.features.pipeline import FeaturePipeline


def test_pipeline_calculates_known_rolling_features(ohlcv_frame: pd.DataFrame) -> None:
    frame = FeaturePipeline().generate(
        ohlcv_frame,
        {
            "simple_return": True,
            "log_return": True,
            "sma": {"window": 3},
            "momentum": {"window": 2},
            "rsi": {"window": 3},
            "rolling_volume_mean": {"window": 3},
            "volume_change": True,
        },
    )
    assert frame.loc[1, "simple_return"] == 11.5 / 10.5 - 1
    assert math.isclose(frame.loc[2, "sma_3"], (10.5 + 11.5 + 12.5) / 3)
    assert math.isclose(frame.loc[2, "momentum_2"], 12.5 / 10.5 - 1)
    assert frame.loc[3, "rsi_3"] == 100.0
    assert frame.loc[2, "rolling_volume_mean_3"] == 110.0
    assert math.isclose(frame.loc[1, "volume_change"], 0.1)


def test_features_do_not_change_past_values_when_future_price_changes(ohlcv_frame: pd.DataFrame) -> None:
    config = {"sma": {"window": 3}, "momentum": {"window": 2}, "rsi": {"window": 3}}
    original = FeaturePipeline().generate(ohlcv_frame, config)
    altered = ohlcv_frame.copy()
    altered.loc[altered.index[-1], "close"] = 1000.0
    recomputed = FeaturePipeline().generate(altered, config)
    pd.testing.assert_frame_equal(original.iloc[:-1][["sma_3", "momentum_2", "rsi_3"]], recomputed.iloc[:-1][["sma_3", "momentum_2", "rsi_3"]])
