#!/usr/bin/env python3
"""Fetch or register one local historical daily OHLCV dataset for FinAgent V0.8."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.data.manager import DatasetManager  # noqa: E402
from finagent.data.models import MarketDataRequest, MissingDataPolicy  # noqa: E402
from finagent.data.registry import DatasetRegistry  # noqa: E402
from finagent.database.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch historical daily OHLCV data into FinAgent's local registry")
    parser.add_argument("--provider", default="yahoo_finance", choices=("yahoo_finance", "local_csv"))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, help="ISO start date, inclusive")
    parser.add_argument("--end", required=True, help="ISO end date, exclusive for Yahoo Finance")
    parser.add_argument("--interval", default="1d", choices=("1d",))
    parser.add_argument("--source-path", help="Local CSV path when --provider local_csv")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--missing-data-policy", default="reject", choices=[item.value for item in MissingDataPolicy])
    parser.add_argument("--database", default="data/finagent.db")
    parser.add_argument("--cache", default="data/cache")
    arguments = parser.parse_args()
    database = Path(arguments.database)
    cache = Path(arguments.cache)
    if not database.is_absolute(): database = PROJECT_ROOT / database
    if not cache.is_absolute(): cache = PROJECT_ROOT / cache
    manager = DatasetManager(DatasetRegistry(Database(database)), cache)
    result = manager.fetch(
        arguments.provider,
        MarketDataRequest(arguments.symbol, arguments.start, arguments.end, arguments.interval, arguments.force_refresh, arguments.source_path),
        MissingDataPolicy(arguments.missing_data_policy),
    )
    item = result.dataset
    print(f"Dataset:       {item.dataset_id}")
    print(f"Version:       {item.version_id}")
    print(f"Provider:      {item.provider}")
    print(f"Rows:          {item.row_count}")
    print(f"Range:         {item.start_date} to {item.end_date}")
    print(f"Cache:         {item.cache_path}")
    print(f"Quality:       {item.validation.quality.score:.3f} ({item.validation.status.value})")
    print(f"Cache hit:     {result.cache_hit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
