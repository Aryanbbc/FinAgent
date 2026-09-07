"""Deterministic coverage for opt-in, non-executing V1.1 live monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from finagent.api.main import create_app
from finagent.api.settings import Settings
from finagent.data.market_provider import MarketDataProviderError
from finagent.database.db import Database
from finagent.live.buffer import RollingOHLCVBuffer
from finagent.live.market_session import LiveMarketState, USEquityMarketCalendar
from finagent.live.models import LiveFeedStatus, LiveMarketBar, LiveProviderHealth
from finagent.live.provider import LiveMarketProvider, TwelveDataLiveProvider
from finagent.live.repository import LiveMarketRepository
from finagent.live.service import LiveMarketService


class Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


class SequencedLiveProvider(LiveMarketProvider):
    provider_name = "mock_live"

    def __init__(self, outcomes: list[list[LiveMarketBar] | MarketDataProviderError]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def fetch_recent_bars(self, symbol: str, interval: str, limit: int) -> list[LiveMarketBar]:
        self.calls += 1
        result = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(result, MarketDataProviderError):
            raise result
        return result


def _bars(now: datetime, count: int = 80) -> list[LiveMarketBar]:
    start = now - timedelta(minutes=count - 1)
    return [
        LiveMarketBar(
            symbol="AAPL",
            timestamp=start + timedelta(minutes=index),
            open=100.0 + index * 0.2,
            high=100.4 + index * 0.2,
            low=99.8 + index * 0.2,
            close=100.2 + index * 0.2,
            volume=1_000.0 + index,
            provider="mock_live",
        )
        for index in range(count)
    ]


def _service(tmp_path: Path, provider: LiveMarketProvider, clock: Clock, *, enabled: bool = True) -> LiveMarketService:
    settings = Settings(
        project_root=Path(__file__).resolve().parents[1],
        database_url=f"sqlite:///{tmp_path / 'live.db'}",
        live_market_enabled=enabled,
        live_default_symbol="AAPL",
        live_symbols=("AAPL",),
        live_interval="1min",
        live_buffer_size=100,
        live_poll_seconds=60,
        live_retention=50,
        live_max_backoff_seconds=300,
    )
    repository = LiveMarketRepository(Database(settings.database_url, settings.project_root))
    return LiveMarketService(settings, repository, provider=provider, clock=clock)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (datetime(2025, 9, 2, 15, 0, tzinfo=UTC), LiveMarketState.LIVE),  # 11:00 EDT regular session
        (datetime(2025, 9, 6, 15, 0, tzinfo=UTC), LiveMarketState.MARKET_CLOSED),  # Saturday
        (datetime(2025, 9, 1, 15, 0, tzinfo=UTC), LiveMarketState.MARKET_CLOSED),  # Labor Day
        (datetime(2025, 9, 2, 12, 30, tzinfo=UTC), LiveMarketState.PRE_MARKET),  # 08:30 EDT
        (datetime(2025, 9, 2, 21, 0, tzinfo=UTC), LiveMarketState.AFTER_HOURS),  # 17:00 EDT
        (datetime(2025, 1, 2, 15, 0, tzinfo=UTC), LiveMarketState.LIVE),  # 10:00 EST, DST-aware
    ],
)
def test_us_equity_calendar_classifies_sessions_holidays_weekends_and_dst(timestamp: datetime, expected: LiveMarketState) -> None:
    assert USEquityMarketCalendar().state_at(timestamp) is expected


def test_twelve_live_provider_parses_recent_ohlcv_in_chronological_order() -> None:
    payload = {
        "status": "ok",
        "values": [
            {"datetime": "2026-01-02 14:31:00", "open": "102", "high": "103", "low": "101", "close": "102.5", "volume": "1200"},
            {"datetime": "2026-01-02 14:30:00", "open": "101", "high": "102", "low": "100", "close": "101.5", "volume": "1100"},
        ],
    }
    provider = TwelveDataLiveProvider(api_key="test-key", http_get=lambda _: json.dumps(payload).encode("utf-8"))

    bars = provider.fetch_recent_bars("AAPL", "1min", 50)

    assert [bar.timestamp.minute for bar in bars] == [30, 31]
    assert bars[-1].close == 102.5 and bars[-1].provider == "twelve_data"


def test_rolling_live_buffer_deduplicates_updates_and_enforces_capacity() -> None:
    now = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    buffer = RollingOHLCVBuffer(3)
    initial = _bars(now, 3)
    latest, created = buffer.update(initial)
    replacement = LiveMarketBar("AAPL", latest.timestamp, latest.open, latest.high + 1, latest.low, latest.close + 0.1, latest.volume, "mock_live")
    _, updated_existing = buffer.update([replacement])
    buffer.update(_bars(now + timedelta(minutes=2), 2))

    assert created and not updated_existing
    assert len(buffer) == 3
    assert buffer.bars()[-1].timestamp == now + timedelta(minutes=2)


def test_live_service_recomputes_features_regime_agents_and_persists_signal(tmp_path: Path) -> None:
    now = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    service = _service(tmp_path, SequencedLiveProvider([_bars(now)]), Clock(now))

    snapshot = service.refresh("AAPL")
    signal = snapshot["latest_signal"]

    assert snapshot["status"] == LiveFeedStatus.LIVE.value
    assert snapshot["provider_health"] == LiveProviderHealth.OK.value
    assert snapshot["market_state"] == LiveMarketState.LIVE.value
    assert snapshot["bars_buffered"] == 80
    assert signal is not None
    # The most recent mocked minute is the in-progress display candle; the
    # persisted decision is anchored to the preceding completed bar.
    assert signal["timestamp"] == (now - timedelta(minutes=1)).isoformat()
    assert snapshot["latest"]["timestamp"] == now.isoformat()
    assert signal["action"] in {"BUY", "HOLD", "EXIT"}
    assert set(signal["technical"]) >= {"trend", "momentum", "volatility", "rsi", "feature_values"}
    assert signal["regime"]["regime"] in {"bull", "bear", "sideways", "high_volatility", "low_volatility", "stress"}
    assert signal["risk"]["reason_code"]
    assert service.signals("AAPL", 10)[0]["timestamp"] == signal["timestamp"]
    event_types = {item["event_type"] for item in service.events("AAPL", 20)}
    assert {"LIVE_BAR_COMPLETED", "LIVE_REGIME_CHANGED", "LIVE_AGENT_DECISION", "LIVE_SIGNAL_CREATED"} <= event_types


def test_closed_market_is_not_delayed_when_provider_health_is_ok(tmp_path: Path) -> None:
    saturday = datetime(2025, 9, 6, 15, 0, tzinfo=UTC)
    service = _service(tmp_path, SequencedLiveProvider([_bars(saturday - timedelta(days=1))]), Clock(saturday))

    snapshot = service.refresh("AAPL")

    assert snapshot["provider_health"] == LiveProviderHealth.OK.value
    assert snapshot["market_state"] == LiveMarketState.MARKET_CLOSED.value
    assert snapshot["status"] == LiveFeedStatus.MARKET_CLOSED.value
    assert snapshot["last_market_bar_timestamp"] == (saturday - timedelta(days=1)).isoformat()
    assert snapshot["last_successful_provider_poll"] == saturday.isoformat()


def test_provider_health_is_ok_but_open_market_old_bar_is_delayed(tmp_path: Path) -> None:
    open_market = datetime(2025, 9, 2, 15, 0, tzinfo=UTC)
    service = _service(tmp_path, SequencedLiveProvider([_bars(open_market - timedelta(minutes=10))]), Clock(open_market))

    snapshot = service.refresh("AAPL")

    assert snapshot["provider_health"] == LiveProviderHealth.OK.value
    assert snapshot["market_state"] == LiveMarketState.LIVE.value
    assert snapshot["status"] == LiveFeedStatus.DELAYED.value


def test_feed_transitions_from_pre_market_to_live_on_fresh_market_bars(tmp_path: Path) -> None:
    pre_market = datetime(2025, 9, 2, 13, 0, tzinfo=UTC)  # 09:00 EDT
    open_market = datetime(2025, 9, 2, 13, 31, tzinfo=UTC)  # 09:31 EDT
    clock = Clock(pre_market)
    service = _service(tmp_path, SequencedLiveProvider([_bars(pre_market), _bars(open_market)]), clock)

    before_open = service.refresh("AAPL")
    clock.advance(int((open_market - pre_market).total_seconds()))
    after_open = service.refresh("AAPL")

    assert before_open["market_state"] == LiveMarketState.PRE_MARKET.value
    assert before_open["status"] == LiveFeedStatus.PRE_MARKET.value
    assert after_open["provider_health"] == LiveProviderHealth.OK.value
    assert after_open["market_state"] == LiveMarketState.LIVE.value
    assert after_open["status"] == LiveFeedStatus.LIVE.value


def test_live_service_handles_rate_limit_with_bounded_reconnect_then_recovers(tmp_path: Path) -> None:
    now = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    clock = Clock(now)
    provider = SequencedLiveProvider([
        MarketDataProviderError("RATE_LIMIT", "rate limited", provider="mock_live", status=429, reason="Provider rate limit reached.", retryable=True),
        _bars(now + timedelta(minutes=1)),
    ])
    service = _service(tmp_path, provider, clock)

    limited = service.refresh("AAPL")
    suppressed = service.refresh("AAPL")
    calls_while_suppressed = provider.calls
    clock.advance(60)
    recovered = service.refresh("AAPL")

    assert limited["status"] == LiveFeedStatus.RATE_LIMITED.value
    assert limited["provider_health"] == LiveProviderHealth.RATE_LIMITED.value
    assert suppressed["status"] == LiveFeedStatus.RATE_LIMITED.value and calls_while_suppressed == 1
    assert recovered["status"] == LiveFeedStatus.LIVE.value and provider.calls == 2
    event_types = {item["event_type"] for item in service.events("AAPL", 20)}
    assert {"LIVE_RATE_LIMITED", "LIVE_RECONNECTED"} <= event_types


def test_live_service_does_not_repeat_permanent_provider_failures_or_fresh_requests(tmp_path: Path) -> None:
    now = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    clock = Clock(now)
    invalid_key = SequencedLiveProvider([
        MarketDataProviderError("INVALID_API_KEY", "invalid key", provider="mock_live", reason="The configured key was rejected."),
    ])
    offline = _service(tmp_path, invalid_key, clock)

    first = offline.refresh("AAPL")
    clock.advance(3_600)
    second = offline.refresh("AAPL")

    assert first["status"] == second["status"] == LiveFeedStatus.OFFLINE.value
    assert invalid_key.calls == 1

    available = SequencedLiveProvider([_bars(now)])
    active = _service(tmp_path, available, Clock(now))
    active.refresh("AAPL")
    active.refresh("AAPL")
    assert available.calls == 1


def test_disabled_live_mode_is_safe_and_does_not_call_provider(tmp_path: Path) -> None:
    now = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    provider = SequencedLiveProvider([_bars(now)])
    service = _service(tmp_path, provider, Clock(now), enabled=False)

    snapshot = service.snapshot("AAPL")

    assert snapshot["enabled"] is False
    assert snapshot["status"] == LiveFeedStatus.OFFLINE.value
    assert provider.calls == 0


def test_disabled_live_api_routes_return_typed_state_without_network(tmp_path: Path) -> None:
    settings = Settings(
        project_root=Path(__file__).resolve().parents[1],
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        live_market_enabled=False,
        live_default_symbol="AAPL",
        live_symbols=("AAPL",),
    )
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/live/status")
        snapshot = client.get("/api/live/snapshot/AAPL")
        symbols = client.get("/api/live/symbols")
        history = client.get("/api/live/history/AAPL")
        signals = client.get("/api/live/signals/AAPL")
        events = client.get("/api/live/events/AAPL")
        documented = client.get("/openapi.json").json()["paths"]

    assert status.status_code == 200 and status.json()["execution"] == "disabled"
    assert snapshot.status_code == 200 and snapshot.json()["enabled"] is False
    assert symbols.json()["items"][0]["symbol"] == "AAPL"
    assert history.json() == {"symbol": "AAPL", "items": []}
    assert signals.json() == {"symbol": "AAPL", "items": []}
    assert events.json() == {"symbol": "AAPL", "items": []}
    assert {"/api/live/status", "/api/live/symbols", "/api/live/snapshot/{symbol}", "/api/live/history/{symbol}", "/api/live/signals/{symbol}", "/api/live/events/{symbol}"} <= set(documented)
