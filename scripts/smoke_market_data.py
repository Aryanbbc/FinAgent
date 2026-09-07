#!/usr/bin/env python3
"""Fetch, validate, and persist one historical OHLCV dataset for deployment smoke checks.

The utility intentionally reads provider credentials only from the process
environment through the provider registry.  It never prints environment values
or request URLs, so a Twelve Data API key cannot appear in terminal output.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.data.manager import DatasetManager  # noqa: E402
from finagent.data.market_provider import MarketDataProviderError  # noqa: E402
from finagent.data.models import MarketDataRequest  # noqa: E402
from finagent.data.registry import DatasetRegistry  # noqa: E402
from finagent.database.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a configured FinAgent historical market-data provider")
    parser.add_argument("--provider", default="twelve_data", choices=("auto", "twelve_data", "yahoo_finance", "stooq", "local_csv"))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, help="ISO start date")
    parser.add_argument("--end", required=True, help="ISO end date")
    parser.add_argument("--interval", default="1d", choices=("1d",))
    parser.add_argument("--source-path", help="Local CSV path when provider is local_csv or auto falls through to it")
    parser.add_argument("--database", default=os.getenv("DATABASE_URL", "data/finagent.db"), help="SQLite path or PostgreSQL DATABASE_URL")
    parser.add_argument("--cache", default=os.getenv("DATA_CACHE_PATH", "data/cache"))
    parser.add_argument("--force-refresh", action="store_true")
    arguments = parser.parse_args()

    cache = Path(arguments.cache)
    if not cache.is_absolute():
        cache = PROJECT_ROOT / cache
    request = MarketDataRequest(
        symbol=arguments.symbol,
        start_date=arguments.start,
        end_date=arguments.end,
        interval=arguments.interval,
        force_refresh=arguments.force_refresh,
        source_path=arguments.source_path,
    )
    manager = DatasetManager(DatasetRegistry(Database(arguments.database, PROJECT_ROOT)), cache)
    try:
        result = manager.fetch(arguments.provider, request)
    except MarketDataProviderError as error:
        print("Validation status: failed")
        print(f"Provider error: {error.code}")
        print(f"Provider: {error.provider or arguments.provider}")
        print(f"Reason: {error.reason}")
        return 1

    dataset = result.dataset
    metadata = dataset.metadata
    print(f"Requested provider: {result.requested_provider}")
    print(f"Actual provider: {result.actual_provider}")
    print(f"Provider symbol: {metadata.provider_symbol or dataset.symbol}")
    print(f"Rows received: {dataset.row_count}")
    print(f"Date range: {dataset.start_date} to {dataset.end_date}")
    print(f"Dataset ID: {dataset.dataset_id}")
    print(f"Validation status: {dataset.validation.status.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
