"""A bounded, chronological in-memory OHLCV buffer for live monitoring."""

from __future__ import annotations

from threading import RLock

import pandas as pd

from finagent.live.models import LiveMarketBar


class RollingOHLCVBuffer:
    """Deduplicates timestamped bars and retains only the newest configured window."""

    def __init__(self, capacity: int) -> None:
        if not 2 <= capacity <= 5_000:
            raise ValueError("Live buffer capacity must be between 2 and 5000")
        self.capacity = capacity
        self._bars: dict[pd.Timestamp, LiveMarketBar] = {}
        self._lock = RLock()

    def update(self, bars: list[LiveMarketBar]) -> tuple[LiveMarketBar | None, bool]:
        """Merge recent bars, returning newest bar and whether its timestamp is new."""
        if not bars:
            return None, False
        ordered = sorted(bars, key=lambda item: item.timestamp)
        newest = ordered[-1]
        timestamp = pd.Timestamp(newest.timestamp).tz_convert("UTC")
        with self._lock:
            is_new = timestamp not in self._bars
            for bar in ordered:
                self._bars[pd.Timestamp(bar.timestamp).tz_convert("UTC")] = bar
            retained = sorted(self._bars)[-self.capacity :]
            self._bars = {item: self._bars[item] for item in retained}
        return newest, is_new

    def bars(self) -> list[LiveMarketBar]:
        with self._lock:
            return [self._bars[item] for item in sorted(self._bars)]

    def frame(self) -> pd.DataFrame:
        """Return only received bars in chronological order for causal computation."""
        return pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp(bar.timestamp).tz_convert("UTC"),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in self.bars()
            ],
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

    def __len__(self) -> int:
        with self._lock:
            return len(self._bars)
