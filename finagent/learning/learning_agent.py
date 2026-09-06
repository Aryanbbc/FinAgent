"""Rules-based LearningAgent that proposes bounded V0.5 configuration candidates."""

from __future__ import annotations

import logging

from finagent.learning.candidate_generator import APPROVED_PARAMETERS, CandidateGenerator
from finagent.learning.models import CandidateProposal, CandidateReasonCode, LearningAgentInput


class LearningAgent:
    """Converts V0.4 memory and critic evidence into deterministic candidate proposals."""

    name = "learning_agent"

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("finagent.learning")

    def propose(self, agent_input: LearningAgentInput, candidate_start: int = 1) -> tuple[CandidateProposal, ...]:
        selected = self._select_parameters(agent_input)
        generator = CandidateGenerator(mode=agent_input.search_mode, max_candidates=agent_input.max_candidates)
        candidates = generator.generate(agent_input, selected, candidate_start)
        self.logger.info(
            "event=LEARNING_CANDIDATES_GENERATED parent_version=%s count=%s parameters=%s",
            agent_input.current_version_id,
            len(candidates),
            ",".join(selected),
        )
        return candidates

    @staticmethod
    def _select_parameters(agent_input: LearningAgentInput) -> tuple[str, ...]:
        reason_codes = set(agent_input.critique.get("reason_codes", []))
        selected: list[str] = []
        if {CandidateReasonCode.HIGH_DRAWDOWN.value, CandidateReasonCode.EXCESSIVE_TURNOVER.value} & reason_codes:
            if CandidateReasonCode.HIGH_DRAWDOWN.value in reason_codes:
                selected.extend(["maximum_position_size", "risk_confidence_threshold", "maximum_volatility"])
            if CandidateReasonCode.EXCESSIVE_TURNOVER.value in reason_codes:
                selected.extend(["momentum_window", "mean_reversion_window"])
        if "UNDERPERFORMS_BENCHMARK" in reason_codes or not selected:
            selected.extend(
                [
                    "moving_average_fast_window",
                    "moving_average_slow_window",
                    "momentum_window",
                    "mean_reversion_window",
                    "mean_reversion_threshold",
                    "strategy_weights",
                    "regime_strategy_mappings",
                ]
            )
        return tuple(parameter for parameter in dict.fromkeys(selected) if parameter in APPROVED_PARAMETERS and parameter in agent_input.boundaries)
