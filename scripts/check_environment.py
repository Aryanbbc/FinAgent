#!/usr/bin/env python3
"""Verify the local runtime needed for FinAgent's demo and developer workflows."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.database.db import Database  # noqa: E402
from finagent.api.settings import Settings  # noqa: E402


def _node_version() -> str | None:
    executable = shutil.which("node")
    if executable is None:
        return None
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FinAgent local development prerequisites")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print a machine-readable result")
    parser.add_argument("--database", default="data/finagent.db", help="SQLite database path relative to the project root")
    args = parser.parse_args()
    database_path = Path(args.database)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    required_modules = ("numpy", "pandas", "yaml", "fastapi", "uvicorn")
    runtime = Settings(project_root=PROJECT_ROOT, database_url=f"sqlite:///{database_path}")
    checks: dict[str, object] = {
        "python_version": sys.version.split()[0],
        "python_supported": sys.version_info >= (3, 11),
        "node_version": _node_version(),
        "frontend_dependencies": (PROJECT_ROOT / "frontend" / "node_modules").is_dir(),
        "python_dependencies": {name: importlib.util.find_spec(name) is not None for name in required_modules},
        "required_directories": {},
        "environment": {name: bool(os.getenv(name)) for name in ("DATABASE_URL", "DATA_CACHE_PATH", "REPORTS_PATH", "FRONTEND_ORIGIN", "FINAGENT_ENV")},
        "runtime": {"environment": runtime.environment, "host": runtime.host, "port": runtime.port, "cors_origins": runtime.cors_origins},
        "database": Database(database_path).health_check(),
    }
    directories = (PROJECT_ROOT / "data", PROJECT_ROOT / "data" / "cache", PROJECT_ROOT / "reports", PROJECT_ROOT / "experiments")
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        checks["required_directories"][str(directory.relative_to(PROJECT_ROOT))] = os.access(directory, os.W_OK)  # type: ignore[index]
    passed = bool(checks["python_supported"] and checks["node_version"] and checks["frontend_dependencies"] and all(checks["python_dependencies"].values()) and checks["database"]["status"] == "ok")  # type: ignore[index,union-attr]
    checks["status"] = "ok" if passed else "action_required"
    if args.as_json:
        print(json.dumps(checks, indent=2, sort_keys=True))
    else:
        print(f"FinAgent environment: {checks['status']}")
        print(f"Python: {checks['python_version']} ({'supported' if checks['python_supported'] else 'requires 3.11+'})")
        print(f"Node: {checks['node_version'] or 'not found'}")
        print(f"Frontend dependencies: {'ready' if checks['frontend_dependencies'] else 'run npm install in frontend/'}")
        print(f"Database: {checks['database']['status']} ({database_path})")  # type: ignore[index]
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
