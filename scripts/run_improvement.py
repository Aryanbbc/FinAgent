#!/usr/bin/env python3
"""Run one explicit, deterministic FinAgent V0.5 improvement cycle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.learning.workflow import run_improvement  # noqa: E402
from finagent.utils.logging import configure_logging  # noqa: E402


def _metric(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded FinAgent V0.5 improvement cycle")
    parser.add_argument("--config", default="config/improvement.yaml", help="Path to V0.5 improvement configuration")
    arguments = parser.parse_args()
    result = run_improvement(arguments.config, PROJECT_ROOT, configure_logging())
    print("\n========================================")
    print("\n       FINAGENT V0.5 IMPROVEMENT\n")
    print("========================================\n")
    if result is None:
        print("Learning:           disabled (learning.enabled: false)")
        return 0
    print(f"Current version:    {result.current_version.version_id}")
    print(f"Candidates:         {len(result.candidates)} generated / {len(result.evaluations)} evaluated")
    candidates = {candidate.candidate_id: candidate for candidate in result.candidates}
    for decision in result.decisions:
        candidate = candidates[decision.candidate_id]
        print(f"\nCandidate:          {decision.candidate_id}")
        changes = ", ".join(
            f"{change.parameter}: {change.previous_value!r} -> {change.proposed_value!r}"
            for change in candidate.parameter_changes
        )
        print(f"Changes:            {changes or 'none'}")
        print(f"Promotion:          {decision.status.value}")
        evaluation = next(item for item in result.evaluations if item.candidate_id == decision.candidate_id)
        print(f"Walk-forward windows:{len(evaluation.windows):>5}")
        print(f"OOS Sharpe:         {_metric(decision.candidate_metrics.sharpe_ratio)}")
        print(f"OOS Return:         {_metric(decision.candidate_metrics.total_return)}")
        print(f"OOS Drawdown:       {_metric(decision.candidate_metrics.maximum_drawdown)}")
        print(f"OOS Trades:         {decision.candidate_metrics.number_of_trades}")
        print(f"Trades / year:      {_metric(decision.candidate_metrics.trades_per_year)}")
        print(f"Avg hold (bars):    {_metric(decision.candidate_metrics.average_holding_period_bars)}")
        print(f"Position changes:   {decision.candidate_metrics.position_changes}")
        print(f"OOS Turnover:       {_metric(decision.candidate_metrics.turnover)}")
        print(f"Window pass rate:   {decision.window_pass_rate:.0%}")
        print(f"Reason codes:       {', '.join(code.value for code in decision.reason_codes)}")
    print(f"\nNew version:        {result.promoted_version.version_id if result.promoted_version else 'none'}")
    print("\n========================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
