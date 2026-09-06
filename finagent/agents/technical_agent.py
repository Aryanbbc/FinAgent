"""Deterministic interpretation of the current causal technical-feature row."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finagent.agents.base import BaseAgent
from finagent.agents.models import (
    MomentumState,
    RsiState,
    TechnicalAgentInput,
    TechnicalAssessment,
    TrendState,
    VolatilityState,
)


@dataclass(frozen=True)
class TechnicalAgentConfig:
    trend_threshold: float = 0.003
    momentum_threshold: float = 0.005
    high_volatility_threshold: float = 0.30
    low_volatility_threshold: float = 0.10
    oversold_rsi: float = 30.0
    overbought_rsi: float = 70.0


class TechnicalAgent(BaseAgent[TechnicalAgentInput, TechnicalAssessment]):
    """Summarizes technical features without making portfolio or execution decisions."""

    name = "technical_agent"

    def __init__(self, configuration: TechnicalAgentConfig | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.configuration = configuration or TechnicalAgentConfig()

    def analyze(self, agent_input: TechnicalAgentInput) -> TechnicalAssessment:
        market_state = agent_input.market_state
        if market_state.empty:
            raise ValueError("TechnicalAgent requires a non-empty market state")
        row = market_state.iloc[-1]
        close = float(row["close"])
        moving_average = self._feature_value(row, "sma_")
        momentum = self._feature_value(row, "momentum_")
        volatility = self._feature_value(row, "rolling_volatility_")
        rsi = self._feature_value(row, "rsi_")
        trend = self._trend(close, moving_average)
        momentum_state = self._momentum(momentum)
        volatility_state = self._volatility(volatility)
        rsi_state = self._rsi(rsi)
        signal_strength, confidence = self._strength(close, moving_average, momentum, volatility, rsi)
        return TechnicalAssessment(
            timestamp=pd.Timestamp(row["timestamp"]),
            trend=trend,
            momentum=momentum_state,
            volatility=volatility_state,
            rsi=rsi_state,
            signal_strength=signal_strength,
            confidence=confidence,
            feature_values={
                "close": close,
                "moving_average": moving_average,
                "momentum": momentum,
                "rolling_volatility": volatility,
                "rsi": rsi,
            },
        )

    @staticmethod
    def _feature_value(row: pd.Series, prefix: str) -> float | None:
        def sort_key(column: str) -> int:
            try:
                return int(column.rsplit("_", maxsplit=1)[1])
            except (IndexError, ValueError):
                return 0

        candidates = sorted((column for column in row.index if column.startswith(prefix)), key=sort_key)
        if not candidates:
            return None
        value = row[candidates[-1]]
        return None if pd.isna(value) else float(value)

    def _trend(self, close: float, moving_average: float | None) -> TrendState:
        if moving_average is None or moving_average == 0:
            return TrendState.NEUTRAL
        distance = (close / moving_average) - 1
        if distance >= self.configuration.trend_threshold:
            return TrendState.BULLISH
        if distance <= -self.configuration.trend_threshold:
            return TrendState.BEARISH
        return TrendState.NEUTRAL

    def _momentum(self, momentum: float | None) -> MomentumState:
        if momentum is None:
            return MomentumState.NEUTRAL
        if momentum >= self.configuration.momentum_threshold:
            return MomentumState.POSITIVE
        if momentum <= -self.configuration.momentum_threshold:
            return MomentumState.NEGATIVE
        return MomentumState.NEUTRAL

    def _volatility(self, volatility: float | None) -> VolatilityState:
        if volatility is None:
            return VolatilityState.UNAVAILABLE
        if volatility >= self.configuration.high_volatility_threshold:
            return VolatilityState.HIGH
        if volatility <= self.configuration.low_volatility_threshold:
            return VolatilityState.LOW
        return VolatilityState.MODERATE

    def _rsi(self, rsi: float | None) -> RsiState:
        if rsi is None:
            return RsiState.UNAVAILABLE
        if rsi >= self.configuration.overbought_rsi:
            return RsiState.OVERBOUGHT
        if rsi <= self.configuration.oversold_rsi:
            return RsiState.OVERSOLD
        return RsiState.NEUTRAL

    def _strength(
        self,
        close: float,
        moving_average: float | None,
        momentum: float | None,
        volatility: float | None,
        rsi: float | None,
    ) -> tuple[float, float]:
        strengths: list[float] = []
        if moving_average not in (None, 0):
            strengths.append(min(1.0, abs((close / moving_average) - 1) / self.configuration.trend_threshold))
        if momentum is not None:
            strengths.append(min(1.0, abs(momentum) / self.configuration.momentum_threshold))
        if volatility is not None:
            strengths.append(min(1.0, volatility / self.configuration.high_volatility_threshold))
        if rsi is not None:
            strengths.append(min(1.0, abs(rsi - 50.0) / 20.0))
        if not strengths:
            return 0.0, 0.0
        signal_strength = sum(strengths) / len(strengths)
        confidence = signal_strength * (len(strengths) / 4)
        return float(signal_strength), float(confidence)
