#!/usr/bin/env python3
"""List current local historical-data registry entries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.data.registry import DatasetRegistry  # noqa: E402
from finagent.database.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="List FinAgent V0.8 registered historical datasets")
    parser.add_argument("--database", default="data/finagent.db", help="SQLite path or PostgreSQL DATABASE_URL")
    arguments = parser.parse_args()
    datasets, total = DatasetRegistry(Database(arguments.database, PROJECT_ROOT)).list_datasets(limit=100)
    print(f"Registered datasets: {total}")
    for item in datasets:
        print(f"{item.dataset_id} {item.version_id} {item.provider} {item.symbol} {item.interval} {item.start_date}..{item.end_date} rows={item.row_count} quality={item.validation.quality.score:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
