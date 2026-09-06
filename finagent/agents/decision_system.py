"""Causal orchestration of the V0.3 technical, regime, strategy, and risk agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from finagent.agents.models import (
    AgentDecision,
    PortfolioState,
    RegimeAgentInput,
    RiskAgentInput,
    StrategyAgentInput,
    TechnicalAgentInput,
)
from finagent.agents.regime_agent import RegimeAgent
from finagent.agents.risk_agent import RiskAgent
from finagent.agents.strategy_agent import StrategyAgent
from finagent.agents.technical_agent import TechnicalAgent


@dataclass
class AgentDecisionSystem:
    """Runs the fixed V0.3 decision flow without hidden state or future data."""

    technical_agent: TechnicalAgent
    regime_agent: RegimeAgent
    strategy_agent: StrategyAgent
    risk_agent: RiskAgent
    logger: logging.Logger | None = None

    def __post_init__(self) -> None:
        self.logger = self.logger or logging.getLogger("finagent.agents")

    def decide(self, market_state: pd.DataFrame, portfolio: PortfolioState) -> AgentDecision:
        """Produce a full decision chain from the supplied causal data prefix."""
        technical = self.technical_agent.run(TechnicalAgentInput(market_state))
        regime = self.regime_agent.run(RegimeAgentInput(market_state))
        proposal = self.strategy_agent.run(
            StrategyAgentInput(
                market_state=market_state,
                technical=technical,
                regime=regime,
                portfolio=portfolio,
                available_strategies=self.strategy_agent.available_strategies,
            )
        )
        risk = self.risk_agent.run(
            RiskAgentInput(
                proposal=proposal,
                portfolio=portfolio,
                volatility=technical.feature_values["rolling_volatility"],
                drawdown=portfolio.drawdown,
            )
        )
        decision = AgentDecision(portfolio.timestamp, technical, regime, proposal, risk)
        self.logger.debug(
            "event=AGENT_FLOW_COMPLETED timestamp=%s strategy=%s action=%s approved=%s risk_reason=%s",
            portfolio.timestamp.isoformat(),
            proposal.selected_strategy,
            decision.execution_action.value,
            risk.approved,
            risk.reason_code.value,
        )
        return decision
