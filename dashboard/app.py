"""Legacy/debug Streamlit dashboard for persisted FinAgent V1.0.0 records."""

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


def _format_decimal(value: object) -> str:
    return "N/A" if value is None else f"{float(value):.3f}"


def main() -> None:
    st.set_page_config(page_title="FinAgent 1.0.0 Legacy / Debug", layout="wide")
    st.title("FinAgent 1.0.0 Legacy / Debug Dashboard")
    st.caption("Historical quantitative research and simulation — not live trading. The V1.0.0 Next.js workspace is the primary interface.")
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

    regime = experiment.results.get("regime", {})
    if regime.get("enabled") and regime.get("latest"):
        latest_regime = regime["latest"]
        st.subheader("Market Regime")
        regime_columns = st.columns(3)
        regime_columns[0].metric("Latest regime", latest_regime["regime"].replace("_", " ").title())
        regime_columns[1].metric("Confidence", _format_percentage(latest_regime["confidence"]))
        regime_columns[2].metric("Observations", int(regime["observations"]))
        regime_history = repository.get_regime_observations(experiment.experiment_id)
        if not regime_history.empty:
            counts = regime_history["regime"].value_counts().rename_axis("regime").to_frame("observations")
            st.bar_chart(counts, use_container_width=True)
            with st.expander("Regime observation history"):
                st.dataframe(regime_history, use_container_width=True, hide_index=True)

    agents = experiment.results.get("agents", {})
    if agents.get("enabled") and agents.get("latest"):
        decision = agents["latest"]
        st.subheader("Agent Decision Flow")
        agent_columns = st.columns(4)
        agent_columns[0].metric("Technical trend", decision["technical"]["trend"].title())
        agent_columns[1].metric("Selected strategy", decision["proposal"]["selected_strategy"])
        agent_columns[2].metric("Execution action", decision["execution_action"].title())
        agent_columns[3].metric("Risk decision", decision["risk"]["reason_code"])
        with st.expander("Agent decision history"):
            agent_history = repository.get_agent_decisions(experiment.experiment_id)
            st.dataframe(agent_history, use_container_width=True, hide_index=True)

    critique = experiment.results.get("critique", {})
    if critique.get("enabled") and critique.get("output"):
        output = critique["output"]
        st.subheader("Experiment Critique")
        st.metric("Critic confidence", _format_percentage(output["confidence"]))
        critique_columns = st.columns(3)
        for column, title, items in (
            (critique_columns[0], "Strengths", output["strengths"]),
            (critique_columns[1], "Weaknesses", output["weaknesses"]),
            (critique_columns[2], "Failure modes", output["failure_modes"]),
        ):
            column.markdown(f"#### {title}")
            if items:
                column.markdown("\n".join(f"- `{item['code']}` — {item['summary']}" for item in items))
            else:
                column.caption("None detected by the configured rules.")
        st.markdown("#### Recommendations")
        recommendations = pd.DataFrame(output["recommendations"])
        if recommendations.empty:
            st.caption("No deterministic recommendation was generated.")
        else:
            st.dataframe(recommendations, use_container_width=True, hide_index=True)
        st.markdown("#### Regime observations")
        st.dataframe(pd.DataFrame(output["regime_observations"]), use_container_width=True, hide_index=True)

    current_version = repository.current_configuration_version()
    latest_evaluation = repository.latest_candidate_evaluation()
    if current_version is not None or latest_evaluation is not None:
        st.subheader("Self-Improvement")
        st.caption("User-invoked, configuration-bounded walk-forward research — no autonomous execution or code changes.")
        improvement_columns = st.columns(4)
        improvement_columns[0].metric("Current version", current_version.version_id if current_version else "None")
        improvement_columns[1].metric("Parent version", current_version.parent_version_id if current_version else "N/A")
        improvement_columns[2].metric(
            "Latest candidate", latest_evaluation.candidate_id if latest_evaluation is not None else "None"
        )
        improvement_columns[3].metric(
            "Latest decision", latest_evaluation.status.value if latest_evaluation is not None else "N/A"
        )
        if latest_evaluation is not None:
            st.markdown("#### Latest Promotion Decision")
            decision_columns = st.columns(4)
            decision_columns[0].metric("OOS Sharpe", _format_decimal(latest_evaluation.candidate_metrics.sharpe_ratio))
            decision_columns[1].metric("OOS return", _format_percentage(latest_evaluation.candidate_metrics.total_return))
            decision_columns[2].metric("OOS drawdown", _format_percentage(latest_evaluation.candidate_metrics.maximum_drawdown))
            decision_columns[3].metric("Window pass rate", _format_percentage(latest_evaluation.window_pass_rate))
            st.markdown("**Reason codes:** " + ", ".join(f"`{code.value}`" for code in latest_evaluation.reason_codes))
            candidate = repository.get_candidate_configuration(latest_evaluation.candidate_id)
            if candidate is not None:
                with st.expander("Candidate configuration changes"):
                    st.dataframe(
                        pd.DataFrame([change.to_dict() for change in candidate.parameter_changes]),
                        use_container_width=True,
                        hide_index=True,
                    )
            st.markdown("#### Walk-Forward Test Windows")
            windows = repository.get_validation_windows(latest_evaluation.candidate_id)
            if windows:
                window_rows = [
                    {
                        "window": window.window_index,
                        "test_start": window.test_start[:10],
                        "test_end": window.test_end[:10],
                        "parent_sharpe": window.parent_metrics.sharpe_ratio,
                        "candidate_sharpe": window.candidate_metrics.sharpe_ratio,
                        "parent_drawdown": window.parent_metrics.maximum_drawdown,
                        "candidate_drawdown": window.candidate_metrics.maximum_drawdown,
                        "parent_return": window.parent_metrics.total_return,
                        "candidate_return": window.candidate_metrics.total_return,
                        "candidate_beats_parent": (
                            window.candidate_metrics.sharpe_ratio is not None
                            and window.parent_metrics.sharpe_ratio is not None
                            and window.candidate_metrics.sharpe_ratio > window.parent_metrics.sharpe_ratio
                        ),
                    }
                    for window in windows
                ]
                st.dataframe(pd.DataFrame(window_rows), use_container_width=True, hide_index=True)
        st.markdown("#### Evolution History")
        history = repository.configuration_version_history()
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "version": item.version_id,
                        "parent": item.parent_version_id,
                        "candidate": item.candidate_id,
                        "status": item.status.value,
                        "created_at": item.created_at,
                        "reason_codes": ", ".join(code.value for code in item.reason_codes),
                    }
                    for item in history
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    validation = repository.latest_research_validation(experiment.experiment_id)
    if validation is not None:
        st.subheader("Research Validation")
        st.caption("Historical robustness diagnostics. Confidence intervals are bootstrap estimates, not statistical guarantees.")
        validation_columns = st.columns(4)
        validation_columns[0].metric("Robustness score", f"{validation.robustness.score:.3f}")
        validation_columns[1].metric("Leakage status", "Passed" if validation.leakage.passed else "Failed")
        validation_columns[2].metric("Assets", len(validation.asset_results))
        validation_columns[3].metric("Walk-forward windows", len(validation.windows))
        st.markdown("#### Multi-Asset Summary")
        asset_frame = pd.DataFrame(
            [
                {
                    "asset": item.asset,
                    "return": item.metrics.total_return,
                    "sharpe": item.metrics.sharpe_ratio,
                    "max_drawdown": item.metrics.maximum_drawdown,
                    "passed": item.passed,
                }
                for item in validation.asset_results
            ]
        )
        st.dataframe(asset_frame, use_container_width=True, hide_index=True)
        if not asset_frame.empty:
            st.bar_chart(asset_frame.set_index("asset")[["return", "sharpe", "max_drawdown"]], use_container_width=True)
        st.markdown("#### Robustness Decomposition")
        st.dataframe(
            pd.DataFrame(
                [{"component": name, "score": value, "weight": validation.robustness.weights.get(name, 0.0)}
                 for name, value in validation.robustness.components.items()]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("#### Confidence Intervals (estimated)")
        st.dataframe(
            pd.DataFrame([item.to_dict() for item in validation.confidence_intervals]),
            use_container_width=True,
            hide_index=True,
        )
        with st.expander("Leakage checks"):
            st.write({"passed": validation.leakage.passed, "checks": validation.leakage.checks, "errors": validation.leakage.errors})

        st.subheader("Ablation Study")
        ablation_frame = pd.DataFrame(
            [
                {
                    "variant": item.variant,
                    "components": ", ".join(item.enabled_components),
                    **item.metrics.to_dict(),
                    "robustness_score": item.robustness.score,
                }
                for item in validation.ablations
            ]
        )
        if ablation_frame.empty:
            st.caption("No ablation study was configured.")
        else:
            st.dataframe(ablation_frame, use_container_width=True, hide_index=True)

        st.subheader("Sensitivity Analysis")
        sensitivity_frame = pd.DataFrame(
            [
                {"parameter": item.parameter, "value": item.value, **item.metrics.to_dict(), "stability_score": item.stability_score}
                for item in validation.sensitivity
            ]
        )
        if sensitivity_frame.empty:
            st.caption("No sensitivity analysis was configured.")
        else:
            st.dataframe(sensitivity_frame, use_container_width=True, hide_index=True)
            for parameter, group in sensitivity_frame.groupby("parameter"):
                st.caption(f"{parameter} sensitivity")
                st.line_chart(group.set_index("value")[["sharpe_ratio", "total_return", "stability_score"]], use_container_width=True)

        st.subheader("Benchmark Suite")
        benchmark_frame = pd.DataFrame(
            [{"asset": item.asset, "benchmark": item.benchmark, **item.metrics.to_dict()} for item in validation.benchmarks]
        )
        if benchmark_frame.empty:
            st.caption("No benchmark suite was configured.")
        else:
            st.dataframe(benchmark_frame, use_container_width=True, hide_index=True)

        st.subheader("Reproducibility")
        manifest = validation.manifest
        st.write(
            {
                "code_version": manifest.code_version,
                "evaluation_mode": manifest.evaluation_mode,
                "assets": manifest.assets,
                "random_seeds": manifest.random_seeds,
                "transaction_costs": manifest.transaction_costs,
                "walk_forward": manifest.walk_forward,
            }
        )

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
