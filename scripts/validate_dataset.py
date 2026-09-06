#!/usr/bin/env python3
"""Re-run transparent V0.8 quality checks for one cached dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.data.manager import DatasetManager  # noqa: E402
from finagent.data.models import MissingDataPolicy  # noqa: E402
from finagent.data.registry import DatasetRegistry  # noqa: E402
from finagent.database.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a registered FinAgent historical dataset")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--database", default="data/finagent.db")
    parser.add_argument("--cache", default="data/cache")
    parser.add_argument("--missing-data-policy", default="reject", choices=[item.value for item in MissingDataPolicy])
    arguments = parser.parse_args()
    database, cache = Path(arguments.database), Path(arguments.cache)
    if not database.is_absolute(): database = PROJECT_ROOT / database
    if not cache.is_absolute(): cache = PROJECT_ROOT / cache
    dataset = DatasetManager(DatasetRegistry(Database(database)), cache).validate(arguments.dataset, MissingDataPolicy(arguments.missing_data_policy))
    print(f"Dataset:       {dataset.dataset_id} / {dataset.version_id}")
    print(f"Status:        {dataset.validation.status.value}")
    print(f"Quality score: {dataset.validation.quality.score:.3f}")
    for issue in dataset.validation.issues:
        print(f"{issue.severity.upper():7} {issue.code}: {issue.message} ({issue.count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
