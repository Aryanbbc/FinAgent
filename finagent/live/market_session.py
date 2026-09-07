"""Exchange-calendar-aware U.S. equity market-session classification."""

from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd


class LiveMarketState(str, Enum):
    """Market-session state independent of provider availability."""

    PRE_MARKET = "PRE_MARKET"
    LIVE = "LIVE"
    AFTER_HOURS = "AFTER_HOURS"
    MARKET_CLOSED = "MARKET_CLOSED"


class USEquityMarketCalendar:
    """Classify NYSE/Nasdaq equity sessions using the XNYS exchange calendar.

    ``exchange_calendars`` supplies trading days, holidays, early closes, and
    daylight-saving-aware regular-session timestamps. Extended-session labels
    use conventional U.S. equity windows (04:00–open and close–20:00 Eastern)
    only on an XNYS trading day; they do not claim that every provider exposes
    extended-hours bars.
    """

    calendar_name = "XNYS"
    timezone = ZoneInfo("America/New_York")
    pre_market_open = time(4, 0)
    after_hours_close = time(20, 0)

    def __init__(self) -> None:
        self._calendar = xcals.get_calendar(self.calendar_name)

    def state_at(self, timestamp: datetime) -> LiveMarketState:
        if timestamp.tzinfo is None:
            raise ValueError("Market-session timestamps must be timezone-aware")
        local = timestamp.astimezone(self.timezone)
        session_date = pd.Timestamp(local.date())
        if not self._calendar.is_session(session_date):
            return LiveMarketState.MARKET_CLOSED

        session = self._calendar.date_to_session(session_date, direction="none")
        regular_open = self._calendar.session_open(session).to_pydatetime().astimezone(self.timezone)
        regular_close = self._calendar.session_close(session).to_pydatetime().astimezone(self.timezone)
        local_time = local.timetz().replace(tzinfo=None)

        if local < regular_open:
            return LiveMarketState.PRE_MARKET if local_time >= self.pre_market_open else LiveMarketState.MARKET_CLOSED
        if local < regular_close:
            return LiveMarketState.LIVE
        return LiveMarketState.AFTER_HOURS if local_time < self.after_hours_close else LiveMarketState.MARKET_CLOSED
