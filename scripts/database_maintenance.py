#!/usr/bin/env python3
"""Safe health and summary export utility; backup remains intentionally SQLite-only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.database.db import Database  # noqa: E402
from finagent.database.experiment_repository import ExperimentRepository  # noqa: E402


def _database_value(value: str) -> str | Path:
    if value.startswith(("sqlite://", "postgresql://", "postgres://")):
        return value
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely inspect FinAgent data or back up a SQLite database")
    parser.add_argument("--database", default="data/finagent.db", help="SQLite path or PostgreSQL DATABASE_URL")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("health", help="Run database connectivity/integrity checks")
    backup = subcommands.add_parser("backup", help="Create a SQLite copy; refuses to overwrite by default")
    backup.add_argument("--output", required=True)
    backup.add_argument("--overwrite", action="store_true", help="Explicitly permit replacing the requested backup file")
    export = subcommands.add_parser("export", help="Write a JSON summary of local experiment records")
    export.add_argument("--output", required=True)
    args = parser.parse_args()
    database = Database(_database_value(args.database), PROJECT_ROOT)
    if args.command == "health":
        print(json.dumps(database.health_check(), indent=2, sort_keys=True))
        return 0
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    if args.command == "backup":
        target = database.backup_to(output, overwrite=bool(args.overwrite))
        print(f"Backup created: {target}")
        return 0
    if output.exists():
        raise FileExistsError(f"export already exists: {output}; choose a new output path")
    repository = ExperimentRepository(database)
    records, total = repository.list_experiments(limit=100, offset=0)
    payload = {"kind": "finagent_experiment_summary", "total": total, "items": [record.__dict__ for record in records]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Summary export created: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
