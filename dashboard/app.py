"""Minimal Streamlit dashboard for persisted FinAgent V0.1 experiments."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finagent.database.db import Database  # noqa: E402
from finagent.database.experiment_repository import ExperimentRepository  # noqa: E402


def _format_percentage(value: object) -> str:
    return "N/A" if value is None else f"{float(value):.2%}"


def main() -> None:
    st.set_page_config(page_title="FinAgent V0.1", layout="wide")
    st.title("FinAgent V0.1")
    st.caption("Historical quantitative research and simulation — not live trading.")
    database_path = st.sidebar.text_input("SQLite database", value=str(PROJECT_ROOT / "data" / "finagent.db"))
    repository = ExperimentRepository(Database(database_path))
    experiment = repository.latest_experiment()
    if experiment is None:
        st.info("No experiments have been saved yet. Run `python scripts/run_experiment.py --config config/experiments.yaml`.")
        return

    st.subheader("Experiment Summary")
    summary_columns = st.columns(4)
    summary_columns[0].metric("Experiment", experiment.experiment_id)
    summary_columns[1].metric("Strategy", experiment.strategy)
    summary_columns[2].metric("Asset", experiment.asset)
    summary_columns[3].metric("Date range", f"{experiment.start_date} to {experiment.end_date}")

    metrics = experiment.results["metrics"]
    st.subheader("Performance")
    columns = st.columns(5)
    columns[0].metric("Total return", _format_percentage(metrics["total_return"]))
    columns[1].metric("Sharpe ratio", "N/A" if metrics["sharpe_ratio"] is None else f"{metrics['sharpe_ratio']:.3f}")
    columns[2].metric("Maximum drawdown", _format_percentage(metrics["maximum_drawdown"]))
    columns[3].metric("Volatility", _format_percentage(metrics["annualized_volatility"]))
    columns[4].metric("Trades", int(metrics["number_of_trades"]))

    st.subheader("Equity Curve")
    strategy_curve = pd.DataFrame(experiment.results["equity_curve"])
    benchmark_curve = pd.DataFrame(experiment.results["benchmark_curve"])
    curves = strategy_curve.merge(benchmark_curve, on="timestamp", how="inner")
    curves["timestamp"] = pd.to_datetime(curves["timestamp"])
    st.line_chart(curves.set_index("timestamp")[["equity", "benchmark_equity"]], use_container_width=True)

    st.subheader("Trade History")
    trades = repository.get_trades(experiment.experiment_id)
    if trades.empty:
        st.info("This experiment generated no trades.")
    else:
        st.dataframe(trades, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
