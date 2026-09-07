"""Opt-in, non-executing live market intelligence components.

This package is intentionally separate from historical experiment execution.
It consumes only recent OHLCV bars, produces deterministic research signals,
and never creates orders, accounts, or brokerage requests.
"""

from finagent.live.models import LiveFeedStatus, LiveMarketBar, LiveSignal, LiveSignalAction
from finagent.live.service import LiveMarketService

__all__ = ["LiveFeedStatus", "LiveMarketBar", "LiveMarketService", "LiveSignal", "LiveSignalAction"]
