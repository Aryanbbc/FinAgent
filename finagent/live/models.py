"""Typed records for the opt-in live market intelligence path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from math import isfinite

from finagent.agents.models import AgentDecision
from finagent.live.market_session import LiveMarketState
from finagent.regime.models import RegimeObservation


class LiveFeedStatus(str, Enum):
    """Presentation-safe combined feed state for the live terminal."""

    CONNECTING = "CONNECTING"
    PRE_MARKET = "PRE_MARKET"
    LIVE = "LIVE"
    AFTER_HOURS = "AFTER_HOURS"
    MARKET_CLOSED = "MARKET_CLOSED"
    DELAYED = "DELAYED"
    RECONNECTING = "RECONNECTING"
    RATE_LIMITED = "RATE_LIMITED"
    OFFLINE = "OFFLINE"


class LiveProviderHealth(str, Enum):
    """Provider transport/authentication health independent of market hours."""

    CONNECTING = "CONNECTING"
    OK = "OK"
    RECONNECTING = "RECONNECTING"
    RATE_LIMITED = "RATE_LIMITED"
    OFFLINE = "OFFLINE"


class LiveSignalAction(str, Enum):
    """Presentation-safe live research actions; these are never orders."""

    BUY = "BUY"
    HOLD = "HOLD"
    EXIT = "EXIT"


@dataclass(frozen=True)
class LiveMarketBar:
    """One normalized recent OHLCV observation from a live/recent feed."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    provider: str

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("LiveMarketBar.timestamp must be timezone-aware")
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(isfinite(value) for value in values):
            raise ValueError("LiveMarketBar OHLCV values must be finite")
        if min(self.open, self.high, self.low, self.close) < 0 or self.volume < 0:
            raise ValueError("LiveMarketBar OHLCV values cannot be negative")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("LiveMarketBar OHLC values are inconsistent")

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class LiveFeedState:
    """Current bounded feed state, deliberately free of credentials.

    ``provider_health`` and ``market_state`` are intentionally separate: an
    old regular-session bar during a holiday can be healthy provider evidence
    with a ``MARKET_CLOSED`` state, rather than a misleading delay.
    """

    symbol: str
    enabled: bool
    status: LiveFeedStatus
    provider_health: LiveProviderHealth
    market_state: LiveMarketState
    provider: str
    feed_mode: str
    interval: str
    last_updated: datetime | None = None
    last_successful_update: datetime | None = None
    last_market_bar_timestamp: datetime | None = None
    last_successful_provider_poll: datetime | None = None
    message: str | None = None
    bars_buffered: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "enabled": self.enabled,
            "status": self.status.value,
            "provider_health": self.provider_health.value,
            "market_state": self.market_state.value,
            "provider": self.provider,
            "feed_mode": self.feed_mode,
            "interval": self.interval,
            "last_updated": self.last_updated.astimezone(UTC).isoformat() if self.last_updated else None,
            "last_successful_update": self.last_successful_update.astimezone(UTC).isoformat() if self.last_successful_update else None,
            "last_market_bar_timestamp": self.last_market_bar_timestamp.astimezone(UTC).isoformat() if self.last_market_bar_timestamp else None,
            "last_successful_provider_poll": self.last_successful_provider_poll.astimezone(UTC).isoformat() if self.last_successful_provider_poll else None,
            "message": self.message,
            "bars_buffered": self.bars_buffered,
        }


@dataclass(frozen=True)
class LiveSignal:
    """A deterministic, non-executing signal emitted for a completed live bar."""

    symbol: str
    timestamp: datetime
    price: float
    provider: str
    decision: AgentDecision
    regime: RegimeObservation
    action: LiveSignalAction
    confidence: float
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("Live signal confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        decision = self.decision
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "price": self.price,
            "provider": self.provider,
            "technical": decision.technical.to_dict(),
            "regime": self.regime.to_dict(),
            "strategy": decision.proposal.to_dict(),
            "action": self.action.value,
            "confidence": self.confidence,
            "risk": decision.risk.to_dict(),
            "reason_codes": list(self.reason_codes),
        }
