#!/usr/bin/env python3
"""Export the final tables, SVG chart, report, and validation JSON for a V1.0 run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.database.db import Database  # noqa: E402
from finagent.database.experiment_repository import ExperimentRepository  # noqa: E402
from finagent.validation.release_export import ReleaseArtifactExporter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export persisted FinAgent V1.0 release evidence without rerunning research")
    parser.add_argument("--experiment", required=True, help="Validated EXP-XXXXXX identifier")
    parser.add_argument("--database", default="data/release/finagent_v1.db", help="SQLite path or PostgreSQL DATABASE_URL")
    parser.add_argument("--output", default="reports/v1.0", help="Directory for Markdown, CSV, SVG, and JSON artifacts")
    arguments = parser.parse_args()
    output_path = Path(arguments.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    artifacts = ReleaseArtifactExporter(ExperimentRepository(Database(arguments.database, PROJECT_ROOT))).export(arguments.experiment, output_path)
    print(f"Release artifacts exported for {arguments.experiment}:")
    for name, path in artifacts.items():
        print(f"- {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
