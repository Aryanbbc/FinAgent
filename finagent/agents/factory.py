"""Shared construction of the optional deterministic V0.3 agent decision system."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from finagent.agents.decision_system import AgentDecisionSystem
from finagent.agents.regime_agent import RegimeAgent
from finagent.agents.risk_agent import RiskAgent, RiskAgentConfig
from finagent.agents.strategy_agent import StrategyAgent, StrategyAgentConfig
from finagent.agents.technical_agent import TechnicalAgent, TechnicalAgentConfig
from finagent.regime.detector import RuleBasedRegimeDetector
from finagent.strategies.factory import create_strategy


def build_agent_decision_system(
    configuration: Mapping[str, Any], detector: RuleBasedRegimeDetector, logger: logging.Logger | None = None
) -> AgentDecisionSystem:
    """Build the fixed technical → regime → strategy → risk pipeline from configuration."""
    agent_config = configuration.get("agents", {})
    technical_config = TechnicalAgentConfig(**dict(agent_config.get("technical", {})))
    risk_config = RiskAgentConfig(**dict(agent_config.get("risk", {})))
    strategy_config = dict(agent_config.get("strategy", {}))
    available_strategy_config = dict(strategy_config.pop("available_strategies", {}))
    if not available_strategy_config:
        configured_strategy = configuration["strategy"]
        available_strategy_config = {configured_strategy["name"]: configured_strategy.get("parameters", {})}
    available_strategies = {
        name: create_strategy(name, parameters) for name, parameters in available_strategy_config.items()
    }
    strategy_agent_config = StrategyAgentConfig(
        regime_strategy_map=(
            dict(strategy_config.get("regime_strategy_map", {})) or StrategyAgentConfig().regime_strategy_map
        ),
        strategy_weights=dict(strategy_config.get("strategy_weights", {})),
    )
    return AgentDecisionSystem(
        technical_agent=TechnicalAgent(technical_config, logger=logger),
        regime_agent=RegimeAgent(detector, logger=logger),
        strategy_agent=StrategyAgent(available_strategies, strategy_agent_config, logger=logger),
        risk_agent=RiskAgent(risk_config, logger=logger),
        logger=logger,
    )
