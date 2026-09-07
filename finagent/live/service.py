"""Opt-in polling orchestration for non-executing live market intelligence."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Callable

import pandas as pd

from finagent.agents.decision_system import AgentDecisionSystem
from finagent.agents.models import AgentAction, PortfolioState
from finagent.agents.regime_agent import RegimeAgent
from finagent.agents.risk_agent import RiskAgent
from finagent.agents.strategy_agent import StrategyAgent
from finagent.agents.technical_agent import TechnicalAgent
from finagent.data.market_provider import MarketDataProviderError
from finagent.features.pipeline import FeaturePipeline
from finagent.live.buffer import RollingOHLCVBuffer
from finagent.live.models import LiveFeedState, LiveFeedStatus, LiveMarketBar, LiveSignal, LiveSignalAction
from finagent.live.provider import LiveMarketProvider, TwelveDataLiveProvider
from finagent.live.repository import LiveMarketRepository
from finagent.regime.detector import RuleBasedRegimeDetector
from finagent.strategies.mean_reversion import MeanReversionStrategy
from finagent.strategies.momentum import MomentumStrategy
from finagent.strategies.moving_average import MovingAverageCrossoverStrategy
from finagent.utils.logging import log_event


class LiveMarketService:
    """Maintains recent OHLCV state and deterministic research signals.

    The service has no execution adapter and never carries real account or
    holdings state.  A fixed, neutral research context exists solely because
    the established V0.3 strategy/risk agents require a typed portfolio input.
    """

    _feature_configuration = {
        "simple_return": True,
        "rolling_volatility": {"window": 20},
        "sma": {"window": 20},
        "ema": {"span": 20},
        "momentum": {"window": 10},
        "rsi": {"window": 14},
    }

    def __init__(
        self,
        settings: object,
        repository: LiveMarketRepository,
        *,
        provider: LiveMarketProvider | None = None,
        logger: logging.Logger | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.provider = provider or TwelveDataLiveProvider()
        self.logger = logger or logging.getLogger("finagent.live")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._buffers = {
            symbol: RollingOHLCVBuffer(self.settings.live_buffer_size)
            for symbol in self.settings.live_symbols
        }
        self._states = {
            symbol: LiveFeedState(
                symbol=symbol,
                enabled=self.settings.live_market_enabled,
                status=self._initial_status(),
                provider=self.provider.provider_name,
                feed_mode="polling",
                interval=self.settings.live_interval,
                message=self._initial_message(),
            )
            for symbol in self.settings.live_symbols
        }
        self._latest_signals: dict[str, LiveSignal] = {}
        self._latest_regimes: dict[str, object] = {}
        self._last_regime: dict[str, str] = {}
        self._retry_count: dict[str, int] = {symbol: 0 for symbol in self.settings.live_symbols}
        self._next_attempt: dict[str, datetime | None] = {symbol: None for symbol in self.settings.live_symbols}
        self._suspended: dict[str, bool] = {symbol: False for symbol in self.settings.live_symbols}
        self._last_evaluated_timestamp: dict[str, datetime | None] = {symbol: None for symbol in self.settings.live_symbols}
        # A browser request and the background poller can arrive together. One
        # refresh at a time per symbol keeps provider use inside the configured
        # cadence and avoids duplicating a live research decision.
        self._refresh_locks = {symbol: threading.Lock() for symbol in self.settings.live_symbols}
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        detector = RuleBasedRegimeDetector()
        self._features = FeaturePipeline()
        self._decision_system = AgentDecisionSystem(
            technical_agent=TechnicalAgent(),
            regime_agent=RegimeAgent(detector),
            strategy_agent=StrategyAgent(
                {
                    "momentum": MomentumStrategy(),
                    "moving_average": MovingAverageCrossoverStrategy(),
                    "mean_reversion": MeanReversionStrategy(),
                }
            ),
            risk_agent=RiskAgent(),
            logger=self.logger,
        )

    def _initial_status(self) -> LiveFeedStatus:
        if not self.settings.live_market_enabled:
            return LiveFeedStatus.OFFLINE
        return LiveFeedStatus.CONNECTING if self.provider.is_available() else LiveFeedStatus.OFFLINE

    def _initial_message(self) -> str:
        if not self.settings.live_market_enabled:
            return "Live market monitoring is disabled by configuration."
        if not self.provider.is_available():
            return "Twelve Data is not configured on this backend."
        return "Awaiting the first bounded polling update."

    async def start(self) -> None:
        """Start bounded polling only when the explicit opt-in flag is enabled."""
        if not self.settings.live_market_enabled or self._task is not None:
            return
        if not self.provider.is_available():
            for symbol in self.settings.live_symbols:
                self._set_state(symbol, LiveFeedStatus.OFFLINE, "Twelve Data is not configured on this backend.")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_forever(), name="finagent-live-market-polling")

    async def stop(self) -> None:
        """Stop polling gracefully without changing persisted research evidence."""
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def _poll_forever(self) -> None:
        while not self._stop_event.is_set():
            for symbol in self.settings.live_symbols:
                await asyncio.to_thread(self.refresh, symbol)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.settings.live_poll_seconds)
            except TimeoutError:
                continue

    def symbols(self) -> list[dict[str, object]]:
        return [
            {"symbol": symbol, "provider": self.provider.provider_name, "interval": self.settings.live_interval}
            for symbol in self.settings.live_symbols
        ]

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.settings.live_market_enabled,
            "provider": self.provider.provider_name,
            "feed_mode": "polling",
            "poll_seconds": self.settings.live_poll_seconds,
            "interval": self.settings.live_interval,
            "symbols": [self._states[symbol].to_dict() for symbol in self.settings.live_symbols],
            "execution": "disabled",
        }

    def refresh(self, symbol: str) -> dict[str, object]:
        """Fetch at most one bounded provider response and update live research state."""
        symbol = self._symbol(symbol)
        with self._refresh_locks[symbol]:
            return self._refresh_locked(symbol)

    def _refresh_locked(self, symbol: str) -> dict[str, object]:
        """Refresh a symbol while its single-flight lock is held."""
        state = self._states[symbol]
        if not self.settings.live_market_enabled:
            return self.snapshot(symbol, refresh=False)
        now = self._clock()
        if self._suspended[symbol]:
            return self.snapshot(symbol, refresh=False)
        next_attempt = self._next_attempt[symbol]
        if next_attempt is not None and now < next_attempt:
            return self.snapshot(symbol, refresh=False)
        # The background task and a UI refresh may arrive at the same time.
        # Re-check after taking the single-flight lock so only one provider
        # request is made per configured cadence.
        if state.last_updated is not None and now - state.last_updated < timedelta(seconds=self.settings.live_poll_seconds):
            return self.snapshot(symbol, refresh=False)
        was_status = state.status
        self._set_state(symbol, LiveFeedStatus.CONNECTING if state.last_successful_update is None else LiveFeedStatus.RECONNECTING, None)
        try:
            bars = self.provider.fetch_recent_bars(symbol, self.settings.live_interval, self.settings.live_buffer_size)
        except MarketDataProviderError as error:
            self._handle_provider_error(symbol, error)
            return self.snapshot(symbol, refresh=False)
        except Exception:  # pragma: no cover - defensive boundary for future provider adapters
            self._handle_provider_error(
                symbol,
                MarketDataProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "The live provider update failed unexpectedly.",
                    provider=self.provider.provider_name,
                    reason="Temporary provider availability failure.",
                    retryable=True,
                ),
            )
            return self.snapshot(symbol, refresh=False)

        latest, _ = self._buffers[symbol].update(bars)
        if latest is None:
            self._handle_provider_error(symbol, MarketDataProviderError("EMPTY_RESULT", "No recent live bars were returned.", provider=self.provider.provider_name, retryable=True))
            return self.snapshot(symbol, refresh=False)
        self._retry_count[symbol] = 0
        self._next_attempt[symbol] = None
        self._suspended[symbol] = False
        event = "LIVE_FEED_CONNECTED" if was_status in {LiveFeedStatus.CONNECTING, LiveFeedStatus.OFFLINE} else "LIVE_RECONNECTED" if was_status in {LiveFeedStatus.RECONNECTING, LiveFeedStatus.RATE_LIMITED, LiveFeedStatus.DELAYED} else None
        delayed = now - latest.timestamp > timedelta(seconds=self._interval_seconds() * 2)
        feed_status = LiveFeedStatus.DELAYED if delayed else LiveFeedStatus.LIVE
        message = "Latest received bar is delayed relative to the configured interval." if delayed else None
        self._set_state(symbol, feed_status, message, last_successful=now)
        if event:
            self._record_event(symbol, event, "Live market polling feed is available.", {"bars_buffered": len(self._buffers[symbol])})
        completed = self._latest_completed_bar(symbol, now)
        last_evaluated = self._last_evaluated_timestamp[symbol]
        if completed is not None and (last_evaluated is None or completed.timestamp > last_evaluated):
            self._last_evaluated_timestamp[symbol] = completed.timestamp
            self._record_event(symbol, "LIVE_BAR_COMPLETED", "A new completed OHLCV bar was received.", {"timestamp": completed.timestamp.isoformat(), "price": completed.close})
            self._record_event(symbol, "LIVE_PRICE_UPDATE", "Latest live research price updated.", {"timestamp": latest.timestamp.isoformat(), "price": latest.close})
            self._evaluate(symbol, completed)
        return self.snapshot(symbol, refresh=False)

    def snapshot(self, symbol: str, *, refresh: bool = True) -> dict[str, object]:
        symbol = self._symbol(symbol)
        if refresh and self.settings.live_market_enabled:
            state = self._states[symbol]
            if state.last_updated is None or self._clock() - state.last_updated >= timedelta(seconds=self.settings.live_poll_seconds):
                return self.refresh(symbol)
        bars = self._buffers[symbol].bars()
        signal = self._latest_signals.get(symbol)
        if signal is None:
            stored = self.repository.signals(symbol, 1)
            current_signal = stored[0] if stored else None
        else:
            current_signal = signal.to_dict()
        regime = self._latest_regimes.get(symbol)
        return {
            **self._states[symbol].to_dict(),
            "latest": bars[-1].to_dict() if bars else None,
            "current_regime": regime.to_dict() if regime is not None else (current_signal or {}).get("regime"),
            "latest_signal": current_signal,
        }

    def history(self, symbol: str) -> list[dict[str, object]]:
        symbol = self._symbol(symbol)
        return [bar.to_dict() for bar in self._buffers[symbol].bars()]

    def signals(self, symbol: str, limit: int) -> list[dict[str, object]]:
        return self.repository.signals(self._symbol(symbol), limit)

    def events(self, symbol: str, limit: int) -> list[dict[str, object]]:
        return self.repository.events(self._symbol(symbol), limit)

    def _evaluate(self, symbol: str, latest: LiveMarketBar) -> None:
        # The buffer can include the next in-progress candle for display.  The
        # decision frame ends at the completed signal bar so every feature,
        # regime, and agent input stays causal.
        source = self._buffers[symbol].frame()
        source = source.loc[source["timestamp"] <= pd.Timestamp(latest.timestamp)].copy()
        frame = self._features.generate(source, self._feature_configuration)
        detector = self._decision_system.regime_agent.detector
        regime = detector.detect(frame)
        drawdown = regime.features.drawdown or 0.0
        research_context = PortfolioState(
            timestamp=pd.Timestamp(latest.timestamp),
            cash=100_000.0,
            holdings=0.0,
            equity=100_000.0,
            position=0,
            entry_price=None,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            drawdown=drawdown,
        )
        decision = self._decision_system.decide(frame, research_context)
        action = {
            AgentAction.LONG: LiveSignalAction.BUY,
            AgentAction.HOLD: LiveSignalAction.HOLD,
            AgentAction.EXIT: LiveSignalAction.EXIT,
        }[decision.execution_action]
        reason_codes = tuple(
            [*(code.value for code in decision.proposal.reason_codes), decision.risk.reason_code.value]
        )
        signal = LiveSignal(
            symbol=symbol,
            timestamp=latest.timestamp,
            price=latest.close,
            provider=latest.provider,
            decision=decision,
            regime=regime,
            action=action,
            confidence=decision.proposal.confidence,
            reason_codes=reason_codes,
        )
        previous_regime = self._last_regime.get(symbol)
        self._latest_signals[symbol] = signal
        self._latest_regimes[symbol] = regime
        self._last_regime[symbol] = regime.regime.value
        self.repository.save_regime(symbol, regime, latest.provider, self.settings.live_retention)
        self.repository.save_signal(signal, self.settings.live_retention)
        if previous_regime != regime.regime.value:
            self._record_event(symbol, "LIVE_REGIME_CHANGED", f"Live regime changed to {regime.regime.value}.", {"regime": regime.regime.value, "confidence": regime.confidence})
        self._record_event(symbol, "LIVE_AGENT_DECISION", "Deterministic live research decision generated.", {"action": action.value, "risk_approved": decision.risk.approved})
        self._record_event(symbol, "LIVE_SIGNAL_CREATED", "Live research signal persisted; no order was created.", {"action": action.value, "reason_codes": list(reason_codes)})

    def _handle_provider_error(self, symbol: str, error: MarketDataProviderError) -> None:
        if error.retryable:
            self._retry_count[symbol] += 1
            attempts = min(self._retry_count[symbol], 5)
            delay = min(self.settings.live_poll_seconds * (2 ** (attempts - 1)), self.settings.live_max_backoff_seconds)
            self._next_attempt[symbol] = self._clock() + timedelta(seconds=delay)
        else:
            # A missing/invalid key or invalid symbol cannot be repaired by a
            # tight polling loop. A configuration change plus restart is the
            # explicit recovery path.
            self._suspended[symbol] = True
            self._next_attempt[symbol] = None
            delay = None
        if error.code == "RATE_LIMIT":
            status = LiveFeedStatus.RATE_LIMITED
            event = "LIVE_RATE_LIMITED"
        elif error.code == "PROVIDER_NOT_CONFIGURED" or not error.retryable:
            status = LiveFeedStatus.OFFLINE
            event = "LIVE_FEED_DISCONNECTED"
        else:
            status = LiveFeedStatus.RECONNECTING
            event = "LIVE_FEED_DISCONNECTED"
        self._set_state(symbol, status, error.reason)
        self._record_event(symbol, event, "Live provider update was unavailable; bounded retry scheduled when applicable.", {"reason": error.reason, "retryable": error.retryable, "retry_after_seconds": delay})

    def _set_state(
        self,
        symbol: str,
        status: LiveFeedStatus,
        message: str | None,
        *,
        last_successful: datetime | None = None,
    ) -> None:
        previous = self._states[symbol]
        now = self._clock()
        self._states[symbol] = LiveFeedState(
            symbol=symbol,
            enabled=self.settings.live_market_enabled,
            status=status,
            provider=self.provider.provider_name,
            feed_mode="polling",
            interval=self.settings.live_interval,
            last_updated=now,
            last_successful_update=last_successful or previous.last_successful_update,
            message=message,
            bars_buffered=len(self._buffers[symbol]),
        )

    def _record_event(self, symbol: str, event_type: str, summary: str, metadata: dict[str, object]) -> None:
        state = self._states[symbol]
        self.repository.save_event(symbol, state, event_type, summary, metadata, self.settings.live_retention)
        log_event(self.logger, event_type, artifact_id=symbol, workflow="live_market", provider=state.provider, feed_status=state.status.value)

    def _symbol(self, symbol: str) -> str:
        normalized = symbol.upper()
        if normalized not in self._buffers:
            raise KeyError(f"Live symbol is not configured: {normalized}")
        return normalized

    def _interval_seconds(self) -> int:
        return {"1min": 60, "5min": 300, "15min": 900}[self.settings.live_interval]

    def _latest_completed_bar(self, symbol: str, now: datetime) -> LiveMarketBar | None:
        """Return the most recent bar whose configured interval has elapsed.

        A provider can expose an in-progress intraday candle.  Showing it as a
        current price is useful, but generating a research signal from it would
        make the signal unstable.  Decisions therefore remain causal and use
        only a completed bar.
        """
        cutoff = now - timedelta(seconds=self._interval_seconds())
        complete = [bar for bar in self._buffers[symbol].bars() if bar.timestamp <= cutoff]
        return complete[-1] if complete else None
