#!/usr/bin/env python3
"""Export a persisted FinAgent experiment and optional V0.6 evidence as Markdown."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.database.db import Database  # noqa: E402
from finagent.database.experiment_repository import ExperimentRepository  # noqa: E402
from finagent.validation.report import ResearchReportExporter  # noqa: E402
from finagent.utils.logging import configure_logging, log_event  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a FinAgent Markdown research report")
    parser.add_argument("--experiment", required=True, help="Persisted EXP-XXXXXX identifier")
    parser.add_argument("--database", default="data/finagent.db", help="SQLite database path")
    parser.add_argument("--output", help="Markdown output path (defaults under reports/)")
    arguments = parser.parse_args()
    database_path = Path(arguments.database)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    report_root = Path(os.getenv("REPORTS_PATH", "reports"))
    if not report_root.is_absolute():
        report_root = PROJECT_ROOT / report_root
    output_path = Path(arguments.output) if arguments.output else report_root / f"{arguments.experiment}_research_report.md"
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output = ResearchReportExporter(ExperimentRepository(Database(database_path))).export(arguments.experiment, output_path)
    log_event(configure_logging(), "REPORT_EXPORTED", artifact_id=arguments.experiment, workflow="report_export")
    print(f"Research report exported: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
