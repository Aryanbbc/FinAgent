#!/usr/bin/env python3
"""Initialize the local FinAgent V0.2 SQLite experiment database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.database.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize the FinAgent SQLite database")
    parser.add_argument("--database", default="data/finagent.db", help="Database path, relative to the project root")
    arguments = parser.parse_args()
    path = Path(arguments.database)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    Database(path).initialize()
    print(f"Initialized database: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
