"""Agent wrapper around the existing V0.2 rule-based regime detector."""

from __future__ import annotations

from finagent.agents.base import BaseAgent
from finagent.agents.models import RegimeAgentInput
from finagent.regime.detector import RuleBasedRegimeDetector
from finagent.regime.models import RegimeObservation


class RegimeAgent(BaseAgent[RegimeAgentInput, RegimeObservation]):
    """Delegates classification to V0.2 without duplicating regime rules."""

    name = "regime_agent"

    def __init__(self, detector: RuleBasedRegimeDetector, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.detector = detector

    def analyze(self, agent_input: RegimeAgentInput) -> RegimeObservation:
        return self.detector.detect(agent_input.market_state)
