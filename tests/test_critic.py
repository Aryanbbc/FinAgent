from __future__ import annotations

import pandas as pd

from finagent.critique.critic_agent import CriticAgent
from finagent.critique.models import CriticAgentInput, TradeStatistics, TransactionCostAssumptions


def test_critic_agent_returns_deterministic_evidence_based_findings_and_recommendations() -> None:
    timestamps = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    critique = CriticAgent().run(
        CriticAgentInput(
            experiment_id="EXP-000101",
            strategy="momentum",
            strategy_parameters={"lookback_window": 5},
            metrics={"total_return": -0.05, "sharpe_ratio": -0.2, "maximum_drawdown": -0.25, "turnover": 3.0},
            benchmark_metrics={"total_return": 0.10},
            regime_history=pd.DataFrame({"timestamp": timestamps, "regime": ["bull", "bear", "bear"]}),
            agent_decision_history=pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "execution_action": ["long", "hold", "exit"],
                    "risk_approved": [True, False, True],
                }
            ),
            trade_statistics=TradeStatistics(4, 1, 1000.0, 20.0, 0.02),
            transaction_costs=TransactionCostAssumptions(0.001, 1.0),
        )
    )
    weakness_codes = {finding.code.value for finding in critique.weaknesses}
    failure_codes = {finding.code.value for finding in critique.failure_modes}
    recommendation_codes = {recommendation.reason_code.value for recommendation in critique.recommendations}
    assert critique.experiment_id == "EXP-000101"
    assert {"UNDERPERFORMS_BENCHMARK", "NEGATIVE_RETURN", "HIGH_DRAWDOWN", "EXCESSIVE_TURNOVER"}.issubset(weakness_codes)
    assert {"UNDERPERFORMS_BENCHMARK", "HIGH_DRAWDOWN", "EXCESSIVE_TURNOVER"}.issubset(failure_codes)
    assert "HIGH_DRAWDOWN" in recommendation_codes
    assert critique.regime_observations[0].regime == "bear"
    assert critique.confidence > 0
    assert critique.to_dict()["reason_codes"]
