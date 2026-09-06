#!/usr/bin/env python3
"""Run a configured FinAgent V0.4 historical experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.runner import load_configuration, run_experiment  # noqa: E402
from finagent.utils.logging import configure_logging  # noqa: E402


def _percentage(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.2%}"


def _decimal(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a FinAgent V0.4 experiment")
    parser.add_argument("--config", default="config/experiments.yaml", help="Path to experiment YAML configuration")
    arguments = parser.parse_args()

    configuration = load_configuration(arguments.config, PROJECT_ROOT)
    experiment_id, results = run_experiment(arguments.config, PROJECT_ROOT, configure_logging())
    experiment = configuration["experiment"]
    metrics = results["metrics"]
    benchmark_metrics = results["benchmark_metrics"]
    dataset_timestamps = results["equity_curve"]

    print("\n========================================")
    print("\n               FINAGENT V0.4\n")
    print("========================================\n")
    print(f"Experiment:         {experiment_id}")
    print(f"Strategy:           {configuration['strategy']['name']}")
    print(f"Asset:              {experiment['asset']}")
    print(f"Start:              {dataset_timestamps[0]['timestamp'][:10]}")
    print(f"End:                {dataset_timestamps[-1]['timestamp'][:10]}")
    print(f"\nInitial Capital:    {float(experiment['starting_capital']):.2f}")
    print("\n----------------------------------------\n")
    print(f"Total Return:       {_percentage(metrics['total_return'])}")
    print(f"Annualized Return:  {_percentage(metrics['annualized_return'])}")
    print(f"Volatility:         {_percentage(metrics['annualized_volatility'])}")
    print(f"Sharpe Ratio:       {_decimal(metrics['sharpe_ratio'])}")
    print(f"Sortino Ratio:      {_decimal(metrics['sortino_ratio'])}")
    print(f"Maximum Drawdown:   {_percentage(metrics['maximum_drawdown'])}")
    print(f"Trades:             {metrics['number_of_trades']}")
    print(f"Win Rate:           {_percentage(metrics['win_rate'])}")
    print(f"\nBenchmark Return:   {_percentage(benchmark_metrics['total_return'])}")
    regime = results.get("regime", {})
    if regime.get("enabled") and regime.get("latest"):
        latest_regime = regime["latest"]
        print(f"Latest Regime:      {latest_regime['regime']}")
        print(f"Regime Confidence:  {_percentage(latest_regime['confidence'])}")
    agents = results.get("agents", {})
    if agents.get("enabled") and agents.get("latest"):
        latest_decision = agents["latest"]
        print(f"Agent Strategy:     {latest_decision['proposal']['selected_strategy']}")
        print(f"Agent Action:       {latest_decision['execution_action']}")
        print(f"Risk Decision:      {latest_decision['risk']['reason_code']}")
    critique = results.get("critique", {})
    if critique.get("enabled") and critique.get("output"):
        output = critique["output"]
        strength_codes = ", ".join(item["code"] for item in output["strengths"]) or "None"
        weakness_codes = ", ".join(item["code"] for item in output["weaknesses"]) or "None"
        print(f"Critic Confidence:  {_percentage(output['confidence'])}")
        print(f"Critic Strengths:   {strength_codes}")
        print(f"Critic Weaknesses:  {weakness_codes}")
    print("\n----------------------------------------\n")
    print("EXPERIMENT SAVED SUCCESSFULLY")
    print("\n========================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
