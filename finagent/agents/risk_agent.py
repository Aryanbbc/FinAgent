"""Deterministic risk gate between a strategy proposal and simulated execution."""

from __future__ import annotations

from dataclasses import dataclass

from finagent.agents.base import BaseAgent
from finagent.agents.models import AgentAction, RiskAgentInput, RiskDecision, RiskReasonCode


@dataclass(frozen=True)
class RiskAgentConfig:
    max_position_size: float = 1.0
    max_drawdown: float = 0.20
    max_volatility: float = 0.50
    reduced_volatility_threshold: float = 0.30
    reduced_position_size: float = 0.50
    minimum_confidence: float = 0.15

    def __post_init__(self) -> None:
        if not 0 < self.max_position_size <= 1 or not 0 < self.reduced_position_size <= 1:
            raise ValueError("Position-size limits must be in (0, 1]")
        if self.max_drawdown <= 0 or self.max_volatility <= 0:
            raise ValueError("Maximum drawdown and volatility limits must be positive")
        if not 0 <= self.minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")


class RiskAgent(BaseAgent[RiskAgentInput, RiskDecision]):
    """Approves, rejects, or reduces a long-only strategy proposal deterministically."""

    name = "risk_agent"

    def __init__(self, configuration: RiskAgentConfig | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.configuration = configuration or RiskAgentConfig()

    def analyze(self, agent_input: RiskAgentInput) -> RiskDecision:
        proposal = agent_input.proposal
        if proposal.action == AgentAction.EXIT:
            return RiskDecision(True, 0.0, RiskReasonCode.EXIT_ALLOWED)
        if proposal.action == AgentAction.HOLD:
            return RiskDecision(True, 0.0, RiskReasonCode.HOLD_NO_ORDER)
        if proposal.confidence < self.configuration.minimum_confidence:
            return RiskDecision(False, 0.0, RiskReasonCode.MIN_CONFIDENCE)
        if agent_input.drawdown <= -self.configuration.max_drawdown:
            return RiskDecision(False, 0.0, RiskReasonCode.MAX_DRAWDOWN_LIMIT)
        if agent_input.volatility is not None and agent_input.volatility >= self.configuration.max_volatility:
            return RiskDecision(False, 0.0, RiskReasonCode.MAX_VOLATILITY_LIMIT)
        if agent_input.portfolio.cash <= 0:
            return RiskDecision(False, 0.0, RiskReasonCode.NO_CASH)

        adjusted_size = min(proposal.requested_position_size, self.configuration.max_position_size)
        reason_code = RiskReasonCode.APPROVED
        if agent_input.volatility is not None and agent_input.volatility >= self.configuration.reduced_volatility_threshold:
            adjusted_size = min(adjusted_size, self.configuration.reduced_position_size)
            reason_code = RiskReasonCode.VOLATILITY_SIZE_REDUCED
        elif adjusted_size < proposal.requested_position_size:
            reason_code = RiskReasonCode.POSITION_SIZE_CAPPED
        return RiskDecision(True, adjusted_size, reason_code)
