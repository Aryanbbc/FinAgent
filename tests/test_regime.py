from __future__ import annotations

import math

import pandas as pd
import pytest

from finagent.regime.detector import RuleBasedRegimeDetector, RuleBasedRegimeDetectorConfig
from finagent.regime.models import MarketRegime, RegimeObservation


def _market_data(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC"), "close": closes})


def _detector() -> RuleBasedRegimeDetector:
    return RuleBasedRegimeDetector(
        RuleBasedRegimeDetectorConfig(
            return_window=2,
            volatility_window=2,
            moving_average_window=2,
            moving_average_slope_window=1,
            momentum_window=1,
            drawdown_window=5,
            bull_return_threshold=0.01,
            bear_return_threshold=-0.01,
            moving_average_slope_threshold=0.002,
            high_volatility_threshold=0.40,
            low_volatility_threshold=0.05,
            stress_drawdown_threshold=-0.20,
        )
    )


def test_detector_returns_typed_structured_observation_with_causal_feature_values() -> None:
    observation = _detector().detect(_market_data([100.0, 110.0, 121.0, 133.1]))
    assert isinstance(observation, RegimeObservation)
    assert observation.regime == MarketRegime.BULL
    assert 0.0 <= observation.confidence <= 1.0
    assert math.isclose(observation.features.rolling_return, 0.21)
    assert math.isclose(observation.features.moving_average_slope, 0.10)
    assert math.isclose(observation.features.momentum, 0.10)
    assert set(observation.to_record()) == {
        "timestamp",
        "regime",
        "confidence",
        "rolling_return",
        "rolling_volatility",
        "moving_average_slope",
        "momentum",
        "drawdown",
    }
    assert observation.to_dict()["features"]["momentum"] == observation.features.momentum


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        ([100.0, 101.0, 102.0, 103.0], MarketRegime.BULL),
        ([100.0, 99.0, 98.0, 97.0], MarketRegime.BEAR),
        ([100.0, 101.0, 100.0, 101.0, 100.0], MarketRegime.SIDEWAYS),
        ([100.0, 80.0, 100.0, 80.0, 100.0], MarketRegime.HIGH_VOLATILITY),
        ([100.0, 100.01, 100.02, 100.03], MarketRegime.LOW_VOLATILITY),
        ([100.0, 100.0, 100.0, 80.0, 70.0], MarketRegime.STRESS),
    ],
)
def test_detector_classifies_supported_regimes(closes: list[float], expected: MarketRegime) -> None:
    assert _detector().detect(_market_data(closes)).regime == expected


def test_regime_history_is_unchanged_when_only_future_data_changes() -> None:
    market_data = _market_data([100.0, 101.0, 100.0, 102.0, 103.0, 102.0, 104.0])
    detector = _detector()
    original_history = detector.detect_history(market_data)
    altered_data = market_data.copy()
    altered_data.loc[altered_data.index[-1], "close"] = 1000.0
    altered_history = detector.detect_history(altered_data)
    pd.testing.assert_frame_equal(original_history.iloc[:-1], altered_history.iloc[:-1])
