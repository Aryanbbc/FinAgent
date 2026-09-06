"""Typed inputs and outputs shared by all V0.3 agents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import pandas as pd

from finagent.regime.models import RegimeObservation
from finagent.strategies.base import Signal

if TYPE_CHECKING:
    from collections.abc import Mapping

    from finagent.strategies.base import Strategy


class TrendState(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class MomentumState(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class VolatilityState(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class RsiState(str, Enum):
    OVERBOUGHT = "overbought"
    OVERSOLD = "oversold"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class AgentAction(str, Enum):
    LONG = "long"
    HOLD = "hold"
    EXIT = "exit"

    @classmethod
    def from_signal(cls, signal: Signal) -> "AgentAction":
        return {Signal.LONG: cls.LONG, Signal.HOLD: cls.HOLD, Signal.EXIT: cls.EXIT}[signal]

    def to_signal(self) -> Signal:
        return {AgentAction.LONG: Signal.LONG, AgentAction.HOLD: Signal.HOLD, AgentAction.EXIT: Signal.EXIT}[self]


class StrategyReasonCode(str, Enum):
    REGIME_STRATEGY_MAP = "REGIME_STRATEGY_MAP"
    BASELINE_LONG_SIGNAL = "BASELINE_LONG_SIGNAL"
    BASELINE_EXIT_SIGNAL = "BASELINE_EXIT_SIGNAL"
    BASELINE_HOLD_SIGNAL = "BASELINE_HOLD_SIGNAL"
    STRESS_REGIME_EXIT = "STRESS_REGIME_EXIT"
    TECHNICAL_CONFLICT = "TECHNICAL_CONFLICT"
    ALREADY_POSITIONED = "ALREADY_POSITIONED"
    FALLBACK_STRATEGY = "FALLBACK_STRATEGY"


class RiskReasonCode(str, Enum):
    APPROVED = "APPROVED"
    HOLD_NO_ORDER = "HOLD_NO_ORDER"
    EXIT_ALLOWED = "EXIT_ALLOWED"
    MIN_CONFIDENCE = "MIN_CONFIDENCE"
    MAX_DRAWDOWN_LIMIT = "MAX_DRAWDOWN_LIMIT"
    MAX_VOLATILITY_LIMIT = "MAX_VOLATILITY_LIMIT"
    NO_CASH = "NO_CASH"
    POSITION_SIZE_CAPPED = "POSITION_SIZE_CAPPED"
    VOLATILITY_SIZE_REDUCED = "VOLATILITY_SIZE_REDUCED"


@dataclass(frozen=True)
class PortfolioState:
    """Causal portfolio snapshot made available to decision agents."""

    timestamp: pd.Timestamp
    cash: float
    holdings: float
    equity: float
    position: int
    entry_price: float | None
    realized_pnl: float
    unrealized_pnl: float
    drawdown: float

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cash": self.cash,
            "holdings": self.holdings,
            "equity": self.equity,
            "position": self.position,
            "entry_price": self.entry_price,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "drawdown": self.drawdown,
        }


@dataclass(frozen=True)
class TechnicalAgentInput:
    market_state: pd.DataFrame


@dataclass(frozen=True)
class TechnicalAssessment:
    timestamp: pd.Timestamp
    trend: TrendState
    momentum: MomentumState
    volatility: VolatilityState
    rsi: RsiState
    signal_strength: float
    confidence: float
    feature_values: dict[str, float | None]

    def __post_init__(self) -> None:
        if not 0 <= self.signal_strength <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("Technical signal strength and confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "trend": self.trend.value,
            "momentum": self.momentum.value,
            "volatility": self.volatility.value,
            "rsi": self.rsi.value,
            "signal_strength": self.signal_strength,
            "confidence": self.confidence,
            "feature_values": self.feature_values,
        }


@dataclass(frozen=True)
class RegimeAgentInput:
    market_state: pd.DataFrame


@dataclass(frozen=True)
class StrategyAgentInput:
    market_state: pd.DataFrame
    technical: TechnicalAssessment
    regime: RegimeObservation
    portfolio: PortfolioState
    available_strategies: "Mapping[str, Strategy]"


@dataclass(frozen=True)
class StrategyProposal:
    selected_strategy: str
    action: AgentAction
    confidence: float
    requested_position_size: float
    reason_codes: tuple[StrategyReasonCode, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("Strategy proposal confidence must be between 0 and 1")
        if not 0 <= self.requested_position_size <= 1:
            raise ValueError("requested_position_size must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_strategy": self.selected_strategy,
            "action": self.action.value,
            "confidence": self.confidence,
            "requested_position_size": self.requested_position_size,
            "reason_codes": [code.value for code in self.reason_codes],
        }


@dataclass(frozen=True)
class RiskAgentInput:
    proposal: StrategyProposal
    portfolio: PortfolioState
    volatility: float | None
    drawdown: float


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    adjusted_position_size: float
    reason_code: RiskReasonCode

    def __post_init__(self) -> None:
        if not 0 <= self.adjusted_position_size <= 1:
            raise ValueError("adjusted_position_size must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "approved": self.approved,
            "adjusted_position_size": self.adjusted_position_size,
            "reason_code": self.reason_code.value,
        }


@dataclass(frozen=True)
class AgentDecision:
    """Full causal V0.3 decision chain for one simulated bar."""

    timestamp: pd.Timestamp
    technical: TechnicalAssessment
    regime: RegimeObservation
    proposal: StrategyProposal
    risk: RiskDecision

    @property
    def execution_action(self) -> AgentAction:
        """Risk rejection converts an entry proposal to a non-trading hold."""
        if self.proposal.action == AgentAction.LONG and not self.risk.approved:
            return AgentAction.HOLD
        return self.proposal.action

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "technical": self.technical.to_dict(),
            "regime": self.regime.to_dict(),
            "proposal": self.proposal.to_dict(),
            "risk": self.risk.to_dict(),
            "execution_action": self.execution_action.value,
        }

    def to_record(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "technical_trend": self.technical.trend.value,
            "technical_momentum": self.technical.momentum.value,
            "technical_volatility": self.technical.volatility.value,
            "technical_rsi": self.technical.rsi.value,
            "technical_signal_strength": self.technical.signal_strength,
            "technical_confidence": self.technical.confidence,
            "regime": self.regime.regime.value,
            "regime_confidence": self.regime.confidence,
            "selected_strategy": self.proposal.selected_strategy,
            "action": self.proposal.action.value,
            "execution_action": self.execution_action.value,
            "proposal_confidence": self.proposal.confidence,
            "requested_position_size": self.proposal.requested_position_size,
            "strategy_reason_codes": [code.value for code in self.proposal.reason_codes],
            "risk_approved": self.risk.approved,
            "adjusted_position_size": self.risk.adjusted_position_size,
            "risk_reason_code": self.risk.reason_code.value,
        }
