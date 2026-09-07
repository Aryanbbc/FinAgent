#!/usr/bin/env python3
"""Initialize the selected FinAgent SQLite or PostgreSQL experiment database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.database.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize the FinAgent SQLite or PostgreSQL database")
    parser.add_argument("--database", default="data/finagent.db", help="SQLite path or PostgreSQL DATABASE_URL")
    arguments = parser.parse_args()
    database = Database(arguments.database, PROJECT_ROOT)
    database.initialize()
    print(f"Initialized {database.backend} database: {database.database_identifier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
