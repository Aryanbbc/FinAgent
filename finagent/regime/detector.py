"""Rule-based primary market-regime detector."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from finagent.regime.features import RegimeFeatureCalculator, RegimeFeatureConfig
from finagent.regime.models import MarketRegime, RegimeFeatureValues, RegimeObservation


@dataclass(frozen=True)
class RuleBasedRegimeDetectorConfig(RegimeFeatureConfig):
    """Feature settings and transparent thresholds for V0.2 classification."""

    bull_return_threshold: float = 0.03
    bear_return_threshold: float = -0.03
    moving_average_slope_threshold: float = 0.005
    high_volatility_threshold: float = 0.30
    low_volatility_threshold: float = 0.10
    stress_drawdown_threshold: float = -0.12

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.bull_return_threshold <= 0 or self.bear_return_threshold >= 0:
            raise ValueError("Bull and bear return thresholds must be positive and negative respectively")
        if self.moving_average_slope_threshold <= 0:
            raise ValueError("moving_average_slope_threshold must be positive")
        if self.high_volatility_threshold <= self.low_volatility_threshold or self.low_volatility_threshold < 0:
            raise ValueError("Volatility thresholds must satisfy high > low >= 0")
        if self.stress_drawdown_threshold >= 0:
            raise ValueError("stress_drawdown_threshold must be negative")

    @classmethod
    def from_mapping(
        cls, configuration: Mapping[str, Any] | None, annualization_factor: int = 252
    ) -> "RuleBasedRegimeDetectorConfig":
        """Create typed configuration from the ``regime`` section of experiment YAML."""
        raw = dict(configuration or {})
        raw.pop("enabled", None)
        thresholds = dict(raw.pop("thresholds", {}))
        return cls(annualization_factor=int(raw.pop("annualization_factor", annualization_factor)), **raw, **thresholds)


class RuleBasedRegimeDetector:
    """Classifies each timestamp from a causal data prefix and explicit rules."""

    def __init__(self, configuration: RuleBasedRegimeDetectorConfig | None = None) -> None:
        self.configuration = configuration or RuleBasedRegimeDetectorConfig()
        self.features = RegimeFeatureCalculator(self.configuration)

    def detect(self, market_state: pd.DataFrame) -> RegimeObservation:
        """Classify the latest bar; callers must supply only currently available data."""
        if "timestamp" not in market_state.columns:
            raise ValueError("market_state must contain a timestamp column")
        if not market_state["timestamp"].is_monotonic_increasing:
            raise ValueError("market_state must be chronologically sorted")
        values = self.features.calculate(market_state)
        regime, confidence = self._classify(values)
        return RegimeObservation(pd.Timestamp(market_state["timestamp"].iloc[-1]), regime, confidence, values)

    def detect_history(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Return an auditable regime observation per bar without look-ahead bias."""
        if market_data.empty:
            raise ValueError("Cannot detect regimes for an empty dataset")
        observations = [self.detect(market_data.iloc[: position + 1]).to_record() for position in range(len(market_data))]
        return pd.DataFrame(observations)

    def _classify(self, values: RegimeFeatureValues) -> tuple[MarketRegime, float]:
        if any(value is None for value in values.to_dict().values()):
            return MarketRegime.SIDEWAYS, 0.0

        rolling_return = float(values.rolling_return)
        volatility = float(values.rolling_volatility)
        slope = float(values.moving_average_slope)
        momentum = float(values.momentum)
        drawdown = float(values.drawdown)
        config = self.configuration

        if drawdown <= config.stress_drawdown_threshold or (
            volatility >= config.high_volatility_threshold and rolling_return <= config.bear_return_threshold
        ):
            return MarketRegime.STRESS, self._stress_confidence(drawdown, volatility)
        if volatility >= config.high_volatility_threshold:
            return MarketRegime.HIGH_VOLATILITY, self._clamp(volatility / config.high_volatility_threshold)
        if (
            rolling_return >= config.bull_return_threshold
            and slope >= config.moving_average_slope_threshold
            and momentum >= 0
        ):
            return MarketRegime.BULL, self._trend_confidence(
                rolling_return / config.bull_return_threshold,
                slope / config.moving_average_slope_threshold,
                momentum / config.bull_return_threshold,
            )
        if (
            rolling_return <= config.bear_return_threshold
            and slope <= -config.moving_average_slope_threshold
            and momentum <= 0
        ):
            return MarketRegime.BEAR, self._trend_confidence(
                rolling_return / config.bear_return_threshold,
                slope / -config.moving_average_slope_threshold,
                momentum / config.bear_return_threshold,
            )
        if volatility <= config.low_volatility_threshold:
            return MarketRegime.LOW_VOLATILITY, self._clamp(1 - (volatility / config.low_volatility_threshold))
        return MarketRegime.SIDEWAYS, self._sideways_confidence(rolling_return, slope, momentum)

    @staticmethod
    def _clamp(value: float) -> float:
        return float(max(0.0, min(1.0, value)))

    def _trend_confidence(self, return_strength: float, slope_strength: float, momentum_strength: float) -> float:
        return self._clamp((return_strength + slope_strength + momentum_strength) / 3)

    def _stress_confidence(self, drawdown: float, volatility: float) -> float:
        drawdown_strength = abs(drawdown / self.configuration.stress_drawdown_threshold)
        volatility_strength = volatility / self.configuration.high_volatility_threshold
        return self._clamp(max(drawdown_strength, volatility_strength))

    def _sideways_confidence(self, rolling_return: float, slope: float, momentum: float) -> float:
        trend_strength = max(
            abs(rolling_return) / self.configuration.bull_return_threshold,
            abs(slope) / self.configuration.moving_average_slope_threshold,
            abs(momentum) / self.configuration.bull_return_threshold,
        )
        return self._clamp(1 - trend_strength)
