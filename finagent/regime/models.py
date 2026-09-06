"""Typed structured outputs for market-regime analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

import pandas as pd


class MarketRegime(str, Enum):
    """Supported primary V0.2 rule-based market regimes."""

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    STRESS = "stress"


@dataclass(frozen=True)
class RegimeFeatureValues:
    """Causal feature values used to classify one market observation."""

    rolling_return: float | None
    rolling_volatility: float | None
    moving_average_slope: float | None
    momentum: float | None
    drawdown: float | None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass(frozen=True)
class RegimeObservation:
    """A timestamped, auditable market-regime classification."""

    timestamp: pd.Timestamp
    regime: MarketRegime
    confidence: float
    features: RegimeFeatureValues

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_record(self) -> dict[str, object]:
        """Return a flattened database-ready representation."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "regime": self.regime.value,
            "confidence": self.confidence,
            **self.features.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        """Return the public nested structured output for one classification."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "regime": self.regime.value,
            "confidence": self.confidence,
            "features": self.features.to_dict(),
        }
