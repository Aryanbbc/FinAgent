#!/usr/bin/env python3
"""Run one non-executing Twelve Data live-market intelligence smoke update."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.api.settings import Settings  # noqa: E402
from finagent.database.db import Database  # noqa: E402
from finagent.live.repository import LiveMarketRepository  # noqa: E402
from finagent.live.service import LiveMarketService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test FinAgent live market intelligence without execution")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--database", help="SQLite path or PostgreSQL DATABASE_URL; defaults to DATABASE_URL")
    arguments = parser.parse_args()
    symbol = arguments.symbol.strip().upper()
    settings_args: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "live_market_enabled": True,
        "live_default_symbol": symbol,
        "live_symbols": (symbol,),
    }
    if arguments.database:
        settings_args["database_url"] = arguments.database
    settings = Settings(**settings_args)
    repository = LiveMarketRepository(Database(settings.database_url, settings.project_root))
    service = LiveMarketService(settings, repository)
    snapshot = service.refresh(symbol)
    latest = snapshot.get("latest") or {}
    signal = snapshot.get("latest_signal") or {}
    regime = snapshot.get("current_regime") or {}
    strategy = signal.get("strategy") if isinstance(signal, dict) else {}
    risk = signal.get("risk") if isinstance(signal, dict) else {}

    print(f"Provider: {snapshot['provider']}")
    print(f"Feed mode: {snapshot['feed_mode']}")
    print(f"Symbol: {snapshot['symbol']}")
    print(f"Latest timestamp: {latest.get('timestamp', '—')}")
    print(f"Latest price: {latest.get('close', '—')}")
    print(f"Bars buffered: {snapshot['bars_buffered']}")
    print(f"Current regime: {regime.get('regime', '—') if isinstance(regime, dict) else '—'}")
    print(f"Technical state: {signal.get('technical', {}) if isinstance(signal, dict) else {}}")
    print(f"Strategy action: {signal.get('action', strategy.get('action', '—')) if isinstance(signal, dict) and isinstance(strategy, dict) else '—'}")
    print(f"Risk decision: {risk.get('reason_code', '—') if isinstance(risk, dict) else '—'}")
    if snapshot["status"] != "LIVE" or not latest:
        print("LIVE PROVIDER UNVERIFIED")
        message = snapshot.get("message")
        if message:
            print(f"Reason: {message}")
        return 1
    print("Live market intelligence only — no order execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
