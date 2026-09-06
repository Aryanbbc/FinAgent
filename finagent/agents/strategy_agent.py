"""Rules-based strategy selection from technical, regime, and portfolio state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from finagent.agents.base import BaseAgent
from finagent.agents.models import (
    AgentAction,
    StrategyAgentInput,
    StrategyProposal,
    StrategyReasonCode,
    TrendState,
)
from finagent.regime.models import MarketRegime
from finagent.strategies.base import Strategy


@dataclass(frozen=True)
class StrategyAgentConfig:
    """Explicit mapping from V0.2 market regimes to baseline strategy names."""

    regime_strategy_map: dict[str, str] = field(
        default_factory=lambda: {
            MarketRegime.BULL.value: "momentum",
            MarketRegime.BEAR.value: "moving_average",
            MarketRegime.SIDEWAYS.value: "mean_reversion",
            MarketRegime.HIGH_VOLATILITY.value: "moving_average",
            MarketRegime.LOW_VOLATILITY.value: "mean_reversion",
            MarketRegime.STRESS.value: "moving_average",
        }
    )


class StrategyAgent(BaseAgent[StrategyAgentInput, StrategyProposal]):
    """Selects an existing baseline strategy; it never invents a new strategy."""

    name = "strategy_agent"

    def __init__(
        self,
        available_strategies: Mapping[str, Strategy],
        configuration: StrategyAgentConfig | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.configuration = configuration or StrategyAgentConfig()
        self.available_strategies = dict(available_strategies)

    def analyze(self, agent_input: StrategyAgentInput) -> StrategyProposal:
        selected_strategy, fallback = self._select_strategy(agent_input)
        reason_codes = [StrategyReasonCode.FALLBACK_STRATEGY if fallback else StrategyReasonCode.REGIME_STRATEGY_MAP]
        if agent_input.regime.regime == MarketRegime.STRESS:
            reason_codes.append(StrategyReasonCode.STRESS_REGIME_EXIT)
            return StrategyProposal(
                selected_strategy=selected_strategy,
                action=AgentAction.EXIT,
                confidence=max(agent_input.technical.confidence, agent_input.regime.confidence),
                requested_position_size=0.0,
                reason_codes=tuple(reason_codes),
            )

        signal = agent_input.available_strategies[selected_strategy].generate_signal(agent_input.market_state)
        action = AgentAction.from_signal(signal)
        reason_codes.append(
            {
                AgentAction.LONG: StrategyReasonCode.BASELINE_LONG_SIGNAL,
                AgentAction.EXIT: StrategyReasonCode.BASELINE_EXIT_SIGNAL,
                AgentAction.HOLD: StrategyReasonCode.BASELINE_HOLD_SIGNAL,
            }[action]
        )
        if action == AgentAction.LONG and agent_input.technical.trend == TrendState.BEARISH:
            action = AgentAction.HOLD
            reason_codes.append(StrategyReasonCode.TECHNICAL_CONFLICT)
        if action == AgentAction.LONG and agent_input.portfolio.position > 0:
            action = AgentAction.HOLD
            reason_codes.append(StrategyReasonCode.ALREADY_POSITIONED)
        return StrategyProposal(
            selected_strategy=selected_strategy,
            action=action,
            confidence=self._confidence(agent_input),
            requested_position_size=1.0 if action == AgentAction.LONG else 0.0,
            reason_codes=tuple(reason_codes),
        )

    def _select_strategy(self, agent_input: StrategyAgentInput) -> tuple[str, bool]:
        if not agent_input.available_strategies:
            raise ValueError("StrategyAgent requires at least one available baseline strategy")
        preferred = self.configuration.regime_strategy_map.get(agent_input.regime.regime.value)
        if preferred in agent_input.available_strategies:
            return str(preferred), False
        return sorted(agent_input.available_strategies)[0], True

    @staticmethod
    def _confidence(agent_input: StrategyAgentInput) -> float:
        if agent_input.regime.confidence == 0:
            return agent_input.technical.confidence * 0.5
        return min(1.0, (agent_input.technical.confidence + agent_input.regime.confidence) / 2)
