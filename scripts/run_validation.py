#!/usr/bin/env python3
"""Run the explicit FinAgent 1.0.0 research-validation suite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.utils.logging import configure_logging  # noqa: E402
from finagent.validation.workflow import run_research_validation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a FinAgent 1.0.0 multi-asset research validation")
    parser.add_argument("--config", default="config/validation.yaml", help="Path to validation YAML")
    arguments = parser.parse_args()
    result = run_research_validation(arguments.config, PROJECT_ROOT, configure_logging())
    if result is None:
        print("Research validation: disabled (validation.enabled: false)")
        return 0
    print("\n========================================")
    print("\n      FINAGENT V1.0.0 VALIDATION\n")
    print("========================================\n")
    print(f"Experiment:         {result.experiment_id}")
    print(f"Validation:         {result.validation_id}")
    print(f"Assets:             {len(result.asset_results)}")
    print(f"Aggregate return:   {result.aggregate_metrics.total_return:.2%}" if result.aggregate_metrics.total_return is not None else "Aggregate return:   N/A")
    print(f"Aggregate Sharpe:   {result.aggregate_metrics.sharpe_ratio:.3f}" if result.aggregate_metrics.sharpe_ratio is not None else "Aggregate Sharpe:   N/A")
    print(f"Robustness score:   {result.robustness.score:.3f}")
    print(f"Leakage checks:     {'PASSED' if result.leakage.passed else 'FAILED'}")
    print(f"Sensitivity points: {len(result.sensitivity)}")
    print(f"Ablation variants:  {len(result.ablations)}")
    print(f"Benchmarks:         {len(result.benchmarks)}")
    print("\n========================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
