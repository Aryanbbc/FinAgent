"""V1.0 final-release evidence, version, and export coverage."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from finagent import __version__
from finagent.api.main import create_app
from finagent.api.settings import Settings
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.validation.release_export import ReleaseArtifactExporter
from finagent.validation.workflow import run_research_validation


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINAL_BENCHMARKS = {
    "buy_and_hold",
    "moving_average",
    "momentum",
    "mean_reversion",
    "regime_aware_finagent",
    "multi_agent_finagent",
    "critic_memory_finagent",
    "self_improved_finagent",
}


def test_v10_version_is_aligned_in_package_api_frontend_and_health(tmp_path: Path) -> None:
    assert __version__ == "1.0.0"
    assert tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] == "1.0.0"
    package = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((PROJECT_ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    assert package["version"] == lock["version"] == lock["packages"][""]["version"] == "1.0.0"
    app = create_app(Settings(project_root=PROJECT_ROOT, database_url=f"sqlite:///{tmp_path / 'release.db'}"))
    response = TestClient(app).get("/api/health")
    assert app.version == response.json()["version"] == "1.0.0"


def test_final_suite_exports_all_release_evidence_without_a_promoted_candidate(tmp_path: Path) -> None:
    source_configuration = yaml.safe_load((PROJECT_ROOT / "config" / "final_experiment.yaml").read_text(encoding="utf-8"))
    source_configuration["database_path"] = str(tmp_path / "release.db")
    source_path = tmp_path / "final_experiment.yaml"
    source_path.write_text(yaml.safe_dump(source_configuration), encoding="utf-8")
    validation_configuration = yaml.safe_load((PROJECT_ROOT / "config" / "final_validation.yaml").read_text(encoding="utf-8"))
    validation_configuration["source_experiment_config"] = str(source_path)
    validation_configuration["validation"]["bootstrap"]["samples"] = 10
    validation_path = tmp_path / "final_validation.yaml"
    validation_path.write_text(yaml.safe_dump(validation_configuration), encoding="utf-8")

    result = run_research_validation(validation_path, PROJECT_ROOT)

    assert result is not None
    assert len(result.asset_results) == 2
    assert len(result.windows) == 4
    assert len(result.sensitivity) == 6
    assert len(result.ablations) == 5
    assert len(result.benchmarks) == 16
    assert {item.benchmark for item in result.benchmarks} == FINAL_BENCHMARKS
    unavailable = [item for item in result.benchmarks if item.benchmark == "self_improved_finagent"]
    assert unavailable and all(not item.available and item.unavailable_reason == "no_promoted_configuration" for item in unavailable)
    assert result.leakage.passed

    artifacts = ReleaseArtifactExporter(ExperimentRepository(Database(tmp_path / "release.db"))).export(
        result.experiment_id, tmp_path / "artifacts"
    )
    assert set(artifacts) == {
        "research_report", "experiment_metrics", "multi_asset", "walk_forward", "sensitivity",
        "confidence_intervals", "ablations", "benchmarks", "benchmark_chart", "validation_record",
    }
    assert "self_improved_finagent" in artifacts["benchmarks"].read_text(encoding="utf-8")
    assert artifacts["benchmark_chart"].read_text(encoding="utf-8").startswith("<svg")


def test_required_v10_release_documents_and_mermaid_diagram_are_present() -> None:
    required = (
        "docs/ARCHITECTURE.md", "docs/RESEARCH_METHODOLOGY.md", "docs/DEVELOPMENT.md", "docs/TROUBLESHOOTING.md",
        "docs/RESULTS.md", "docs/DEMO.md", "docs/VIVA_GUIDE.md", "docs/DEMO_SCRIPT.md", "docs/PORTFOLIO.md",
        "docs/RELEASE_CHECKLIST.md", "CHANGELOG.md",
    )
    assert all((PROJECT_ROOT / item).is_file() for item in required)
    assert "```mermaid" in (PROJECT_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    demo = yaml.safe_load((PROJECT_ROOT / "config" / "demo.yaml").read_text(encoding="utf-8"))
    assert demo["application"]["version"] == "1.0.0"
    assert demo["database_path"] == "data/demo/finagent_v1_demo.db"
    assert "DATABASE_URL=sqlite:///data/demo/finagent_v1_demo.db" in (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
