#!/usr/bin/env python3
"""Create a named immutable-reference dataset collection for V0.6 validation."""

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
    parser = argparse.ArgumentParser(description="Create a FinAgent V0.8 multi-asset dataset collection")
    parser.add_argument("--name", required=True)
    parser.add_argument("--datasets", nargs="+", required=True)
    parser.add_argument("--description")
    parser.add_argument("--database", default="data/finagent.db")
    arguments = parser.parse_args()
    database = Path(arguments.database)
    if not database.is_absolute(): database = PROJECT_ROOT / database
    collection = DatasetRegistry(Database(database)).create_collection(arguments.name, arguments.datasets, arguments.description)
    print(f"Collection: {collection.collection_id} ({collection.name})")
    for member in collection.members: print(f"- {member['symbol']}: {member['dataset_id']} @ {member['version_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
