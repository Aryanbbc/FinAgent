#!/usr/bin/env python3
"""Create a clearly marked, idempotent local V0.9 demonstration database."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent import __version__  # noqa: E402
from finagent.data.manager import DatasetManager  # noqa: E402
from finagent.data.models import MarketDataRequest, MissingDataPolicy  # noqa: E402
from finagent.data.registry import DatasetRegistry  # noqa: E402
from finagent.database.db import Database  # noqa: E402
from finagent.database.experiment_repository import ExperimentRepository  # noqa: E402
from finagent.learning.workflow import run_improvement  # noqa: E402
from finagent.runner import run_experiment  # noqa: E402
from finagent.validation.report import ResearchReportExporter  # noqa: E402
from finagent.validation.workflow import run_research_validation  # noqa: E402


DATABASE_PATH = PROJECT_ROOT / "data" / "demo" / "finagent_demo.db"


def main() -> int:
    database = Database(DATABASE_PATH)
    if database.demo_seed("default") is not None:
        print(f"Demo data already prepared: {DATABASE_PATH}")
        return 0

    registry = DatasetRegistry(database)
    manager = DatasetManager(registry, PROJECT_ROOT / "data" / "demo" / "cache")
    manager.fetch(
        "local_csv",
        MarketDataRequest("DEMO_EXAMPLE", "2024-01-01", "2024-03-01", source_path=str(PROJECT_ROOT / "data" / "raw" / "example_ohlcv.csv")),
        MissingDataPolicy.REJECT,
    )
    manager.fetch(
        "local_csv",
        MarketDataRequest("DEMO_SECONDARY", "2024-01-01", "2024-03-01", source_path=str(PROJECT_ROOT / "data" / "raw" / "example_ohlcv_secondary.csv")),
        MissingDataPolicy.REJECT,
    )
    registry.create_collection("DEMO_SAMPLE", ["DATA-LOCAL-CSV-DEMO-EXAMPLE-1D", "DATA-LOCAL-CSV-DEMO-SECONDARY-1D"], "Clearly marked bundled sample data")

    experiment_id, _ = run_experiment("config/demo.yaml", PROJECT_ROOT)
    validation = run_research_validation("config/demo_validation.yaml", PROJECT_ROOT)
    improvement = run_improvement("config/demo_improvement.yaml", PROJECT_ROOT)
    report_experiment = validation.experiment_id if validation else experiment_id
    report = ResearchReportExporter(ExperimentRepository(database)).export(report_experiment, PROJECT_ROOT / "data" / "demo" / "reports" / f"{report_experiment}_research_report.md")
    database.save_demo_seed(
        "default",
        __version__,
        json.dumps({
            "sample_data": True,
            "dataset_count": 2,
            "primary_experiment_id": experiment_id,
            "validation_id": validation.validation_id if validation else None,
            "candidate_count": len(improvement.candidates) if improvement else 0,
            "report": str(report),
        }, sort_keys=True),
    )
    print(f"Demo data prepared: {DATABASE_PATH}")
    print("Marked as sample/demo data; it is simulated historical research, not trading advice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
