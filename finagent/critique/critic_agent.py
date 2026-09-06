"""Rules-based post-experiment critique agent for FinAgent V0.4."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finagent.agents.base import BaseAgent
from finagent.critique.models import (
    CriticAgentInput,
    CritiqueFinding,
    CritiqueReasonCode,
    CritiqueRecommendation,
    ExperimentCritique,
    RegimeObservationSummary,
)


@dataclass(frozen=True)
class CriticAgentConfig:
    strong_sharpe_threshold: float = 1.0
    weak_sharpe_threshold: float = 0.0
    controlled_drawdown_threshold: float = 0.10
    high_drawdown_threshold: float = 0.15
    low_turnover_threshold: float = 0.50
    excessive_turnover_threshold: float = 2.00
    high_transaction_cost_ratio: float = 0.01
    minimum_closed_trades: int = 3


class CriticAgent(BaseAgent[CriticAgentInput, ExperimentCritique]):
    """Produces evidence-based critique findings; it never changes a strategy."""

    name = "critic_agent"

    def __init__(self, configuration: CriticAgentConfig | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.configuration = configuration or CriticAgentConfig()

    def analyze(self, agent_input: CriticAgentInput) -> ExperimentCritique:
        metrics = agent_input.metrics
        benchmark = agent_input.benchmark_metrics
        config = self.configuration
        total_return = self._number(metrics.get("total_return"))
        benchmark_return = self._number(benchmark.get("total_return"))
        sharpe = self._number(metrics.get("sharpe_ratio"))
        drawdown = abs(self._number(metrics.get("maximum_drawdown")))
        turnover = self._number(metrics.get("turnover"))
        strengths: list[CritiqueFinding] = []
        weaknesses: list[CritiqueFinding] = []
        failure_modes: list[CritiqueFinding] = []
        recommendations: list[CritiqueRecommendation] = []
        reason_codes = [CritiqueReasonCode.CRITIQUE_COMPLETED]

        if total_return > benchmark_return:
            finding = CritiqueFinding(
                CritiqueReasonCode.OUTPERFORMS_BENCHMARK,
                "Strategy return exceeded the buy-and-hold benchmark.",
                {"strategy_return": total_return, "benchmark_return": benchmark_return},
            )
            strengths.append(finding)
            reason_codes.append(finding.code)
        else:
            finding = CritiqueFinding(
                CritiqueReasonCode.UNDERPERFORMS_BENCHMARK,
                "Strategy return did not exceed the buy-and-hold benchmark.",
                {"strategy_return": total_return, "benchmark_return": benchmark_return},
            )
            weaknesses.append(finding)
            failure_modes.append(finding)
            reason_codes.append(finding.code)
            recommendations.append(
                CritiqueRecommendation(
                    "strategy_selection",
                    "review",
                    "Review regime-to-strategy mapping before any future manual research change.",
                    finding.code,
                )
            )

        if total_return > 0:
            finding = CritiqueFinding(CritiqueReasonCode.POSITIVE_RETURN, "Experiment finished with a positive return.", {"total_return": total_return})
            strengths.append(finding)
            reason_codes.append(finding.code)
        elif total_return < 0:
            finding = CritiqueFinding(CritiqueReasonCode.NEGATIVE_RETURN, "Experiment finished with a negative return.", {"total_return": total_return})
            weaknesses.append(finding)
            failure_modes.append(finding)
            reason_codes.append(finding.code)

        if sharpe >= config.strong_sharpe_threshold:
            finding = CritiqueFinding(CritiqueReasonCode.STRONG_SHARPE, "Risk-adjusted return met the strong Sharpe threshold.", {"sharpe_ratio": sharpe})
            strengths.append(finding)
            reason_codes.append(finding.code)
        elif sharpe <= config.weak_sharpe_threshold:
            finding = CritiqueFinding(CritiqueReasonCode.WEAK_SHARPE, "Risk-adjusted return was at or below the weak Sharpe threshold.", {"sharpe_ratio": sharpe})
            weaknesses.append(finding)
            reason_codes.append(finding.code)

        if drawdown <= config.controlled_drawdown_threshold:
            finding = CritiqueFinding(CritiqueReasonCode.CONTROLLED_DRAWDOWN, "Maximum drawdown remained within the controlled threshold.", {"maximum_drawdown": -drawdown})
            strengths.append(finding)
            reason_codes.append(finding.code)
        elif drawdown >= config.high_drawdown_threshold:
            finding = CritiqueFinding(CritiqueReasonCode.HIGH_DRAWDOWN, "Maximum drawdown exceeded the configured risk threshold.", {"maximum_drawdown": -drawdown})
            weaknesses.append(finding)
            failure_modes.append(finding)
            reason_codes.append(finding.code)
            recommendations.append(
                CritiqueRecommendation(
                    "max_drawdown",
                    "tighten",
                    "Review risk limits manually because drawdown exceeded the V0.4 critique threshold.",
                    finding.code,
                )
            )

        if turnover <= config.low_turnover_threshold:
            finding = CritiqueFinding(CritiqueReasonCode.LOW_TURNOVER, "Turnover remained within the low-turnover threshold.", {"turnover": turnover})
            strengths.append(finding)
            reason_codes.append(finding.code)
        elif turnover >= config.excessive_turnover_threshold:
            finding = CritiqueFinding(CritiqueReasonCode.EXCESSIVE_TURNOVER, "Turnover exceeded the configured threshold.", {"turnover": turnover})
            weaknesses.append(finding)
            failure_modes.append(finding)
            reason_codes.append(finding.code)
            recommendations.append(
                CritiqueRecommendation(
                    "turnover",
                    "reduce",
                    "Inspect signal frequency and transaction-cost assumptions in a future manual experiment.",
                    finding.code,
                )
            )

        cost_ratio = agent_input.trade_statistics.transaction_cost_ratio
        if cost_ratio is not None and cost_ratio >= config.high_transaction_cost_ratio:
            finding = CritiqueFinding(
                CritiqueReasonCode.HIGH_TRANSACTION_COSTS,
                "Transaction costs consumed a high share of traded notional.",
                {"transaction_cost_ratio": cost_ratio, "total_transaction_cost": agent_input.trade_statistics.total_transaction_cost},
            )
            weaknesses.append(finding)
            reason_codes.append(finding.code)

        if agent_input.trade_statistics.closed_trades < config.minimum_closed_trades:
            finding = CritiqueFinding(
                CritiqueReasonCode.LOW_TRADE_SAMPLE,
                "Too few closed trades are available for a robust trade-level conclusion.",
                {"closed_trades": agent_input.trade_statistics.closed_trades},
            )
            weaknesses.append(finding)
            reason_codes.append(finding.code)

        risk_rejections = self._risk_rejections(agent_input.agent_decision_history)
        if risk_rejections:
            finding = CritiqueFinding(
                CritiqueReasonCode.RISK_REJECTIONS,
                "Risk controls rejected one or more proposed entries.",
                {"risk_rejections": risk_rejections},
            )
            weaknesses.append(finding)
            reason_codes.append(finding.code)

        confidence = self._confidence(agent_input)
        return ExperimentCritique(
            experiment_id=agent_input.experiment_id,
            strengths=tuple(strengths),
            weaknesses=tuple(weaknesses),
            failure_modes=tuple(failure_modes),
            regime_observations=tuple(self._regime_observations(agent_input)),
            recommendations=tuple(recommendations),
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            confidence=confidence,
        )

    @staticmethod
    def _number(value: float | int | None) -> float:
        return 0.0 if value is None or pd.isna(value) else float(value)

    @staticmethod
    def _risk_rejections(agent_decisions: pd.DataFrame) -> int:
        if agent_decisions.empty or "risk_approved" not in agent_decisions:
            return 0
        return int((~agent_decisions["risk_approved"].astype(bool)).sum())

    def _regime_observations(self, agent_input: CriticAgentInput) -> list[RegimeObservationSummary]:
        if agent_input.regime_history.empty:
            return []
        regimes = agent_input.regime_history.copy()
        regimes["timestamp"] = pd.to_datetime(regimes["timestamp"])
        trade_times = pd.to_datetime(agent_input.agent_decision_history.get("timestamp", pd.Series(dtype=str)))
        decision_history = agent_input.agent_decision_history.copy()
        if not decision_history.empty:
            decision_history["timestamp"] = trade_times
        summaries: list[RegimeObservationSummary] = []
        for regime, group in regimes.groupby("regime", sort=True):
            timestamps = set(group["timestamp"])
            decisions = decision_history[decision_history["timestamp"].isin(timestamps)] if not decision_history.empty else decision_history
            executions = int((decisions["execution_action"] != "hold").sum()) if not decisions.empty else 0
            rejections = self._risk_rejections(decisions)
            summaries.append(
                RegimeObservationSummary(
                    regime=str(regime),
                    observations=int(len(group)),
                    trade_executions=executions,
                    risk_rejections=rejections,
                    summary=f"{len(group)} observations; {executions} non-hold agent actions; {rejections} risk rejections.",
                )
            )
        return summaries

    def _confidence(self, agent_input: CriticAgentInput) -> float:
        evidence_sources = 4
        if not agent_input.regime_history.empty:
            evidence_sources += 1
        if not agent_input.agent_decision_history.empty:
            evidence_sources += 1
        if agent_input.trade_statistics.closed_trades >= self.configuration.minimum_closed_trades:
            evidence_sources += 1
        return min(1.0, evidence_sources / 7)
