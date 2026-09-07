#!/usr/bin/env python3
"""Verify the current FinAgent release metadata and retained V1.0 evidence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.1.0"
REQUIRED_FILES = (
    "CHANGELOG.md",
    "config/final_experiment.yaml",
    "config/final_validation.yaml",
    "docs/ARCHITECTURE.md",
    "docs/RESEARCH_METHODOLOGY.md",
    "docs/DEVELOPMENT.md",
    "docs/TROUBLESHOOTING.md",
    "docs/RESULTS.md",
    "docs/DEMO.md",
    "docs/VIVA_GUIDE.md",
    "docs/DEMO_SCRIPT.md",
    "docs/PORTFOLIO.md",
    "docs/RELEASE_CHECKLIST.md",
    "reports/v1.0/research_report.md",
    "reports/v1.0/benchmark_total_returns.svg",
)
SECRET_MARKERS = (
    re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH) PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check current FinAgent release metadata and tracked-file hygiene")
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args()
    errors = check_release()
    payload = {"version": VERSION, "status": "ok" if not errors else "failed", "errors": errors}
    if arguments.as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"FinAgent release check: {payload['status']}")
        for error in errors:
            print(f"- {error}")
    return 0 if not errors else 1


def check_release() -> list[str]:
    errors: list[str] = []
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if pyproject["project"]["version"] != VERSION:
        errors.append(f"pyproject.toml does not declare {VERSION}")
    package = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    if package["version"] != VERSION:
        errors.append(f"frontend/package.json does not declare {VERSION}")
    package_lock = json.loads((PROJECT_ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    if package_lock["version"] != VERSION or package_lock["packages"][""]["version"] != VERSION:
        errors.append(f"frontend/package-lock.json does not declare {VERSION}")
    init_source = (PROJECT_ROOT / "finagent" / "__init__.py").read_text(encoding="utf-8")
    api_source = (PROJECT_ROOT / "finagent" / "api" / "main.py").read_text(encoding="utf-8")
    if f'__version__ = "{VERSION}"' not in init_source:
        errors.append(f"finagent package does not declare {VERSION}")
    if f'version="{VERSION}"' not in api_source:
        errors.append(f"FastAPI metadata does not declare {VERSION}")
    for relative in REQUIRED_FILES:
        if not (PROJECT_ROOT / relative).is_file():
            errors.append(f"missing required release file: {relative}")
    architecture = (PROJECT_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    if "```mermaid" not in architecture:
        errors.append("architecture documentation has no Mermaid diagram")
    errors.extend(_tracked_file_hygiene())
    return errors


def _tracked_file_hygiene() -> list[str]:
    result = subprocess.run(["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        return ["unable to list Git-tracked files for hygiene verification"]
    errors: list[str] = []
    for relative in result.stdout.splitlines():
        path = PROJECT_ROOT / relative
        name = path.name
        if name.startswith(".env") and name != ".env.example":
            errors.append(f"tracked environment file: {relative}")
            continue
        if path.suffix.lower() in {".pem", ".key", ".p12", ".db", ".sqlite3"}:
            errors.append(f"tracked sensitive/generated file: {relative}")
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(marker.search(content) for marker in SECRET_MARKERS):
            errors.append(f"possible secret marker in tracked file: {relative}")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
