from __future__ import annotations

import logging

import pandas as pd

from finagent.agents.decision_system import AgentDecisionSystem
from finagent.agents.models import (
    AgentAction,
    MomentumState,
    PortfolioState,
    RegimeAgentInput,
    RiskAgentInput,
    RsiState,
    StrategyAgentInput,
    StrategyProposal,
    StrategyReasonCode,
    TechnicalAgentInput,
    TechnicalAssessment,
    TrendState,
    VolatilityState,
)
from finagent.agents.regime_agent import RegimeAgent
from finagent.agents.risk_agent import RiskAgent, RiskAgentConfig
from finagent.agents.strategy_agent import StrategyAgent
from finagent.agents.technical_agent import TechnicalAgent
from finagent.backtesting.engine import BacktestEngine
from finagent.features.pipeline import FeaturePipeline
from finagent.regime.detector import RuleBasedRegimeDetector, RuleBasedRegimeDetectorConfig
from finagent.regime.models import MarketRegime, RegimeFeatureValues, RegimeObservation
from finagent.strategies.momentum import MomentumStrategy


def _market_data(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC"),
            "open": closes,
            "high": [close + 1 for close in closes],
            "low": [close - 1 for close in closes],
            "close": closes,
            "volume": [1000] * len(closes),
        }
    )


def _portfolio_state() -> PortfolioState:
    return PortfolioState(
        timestamp=pd.Timestamp("2024-01-03", tz="UTC"),
        cash=1000.0,
        holdings=0.0,
        equity=1000.0,
        position=0,
        entry_price=None,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        drawdown=0.0,
    )


def _technical_assessment() -> TechnicalAssessment:
    return TechnicalAssessment(
        timestamp=pd.Timestamp("2024-01-03", tz="UTC"),
        trend=TrendState.BULLISH,
        momentum=MomentumState.POSITIVE,
        volatility=VolatilityState.MODERATE,
        rsi=RsiState.NEUTRAL,
        signal_strength=0.8,
        confidence=0.8,
        feature_values={"rolling_volatility": 0.2},
    )


def _regime(regime: MarketRegime = MarketRegime.BULL) -> RegimeObservation:
    return RegimeObservation(
        timestamp=pd.Timestamp("2024-01-03", tz="UTC"),
        regime=regime,
        confidence=0.8,
        features=RegimeFeatureValues(0.05, 0.2, 0.01, 0.03, 0.0),
    )


def test_technical_agent_interprets_current_causal_feature_values_and_logs(caplog) -> None:
    featured_data = FeaturePipeline().generate(
        _market_data([100.0, 101.0, 102.0, 104.0, 106.0]),
        {"sma": {"window": 3}, "momentum": {"window": 2}, "rolling_volatility": {"window": 3}, "rsi": {"window": 3}},
    )
    caplog.set_level(logging.DEBUG, logger="finagent.agents")
    assessment = TechnicalAgent().run(TechnicalAgentInput(featured_data))
    assert assessment.trend == TrendState.BULLISH
    assert assessment.momentum == MomentumState.POSITIVE
    assert assessment.rsi == RsiState.OVERBOUGHT
    assert assessment.feature_values["rolling_volatility"] is not None
    assert "event=AGENT_DECISION agent=technical_agent" in caplog.text


def test_regime_agent_delegates_to_existing_detector() -> None:
    market_data = _market_data([100.0, 101.0, 102.0, 103.0])
    detector = RuleBasedRegimeDetector(
        RuleBasedRegimeDetectorConfig(
            return_window=2,
            volatility_window=2,
            moving_average_window=2,
            moving_average_slope_window=1,
            momentum_window=1,
            drawdown_window=3,
        )
    )
    assert RegimeAgent(detector).run(RegimeAgentInput(market_data)) == detector.detect(market_data)


def test_strategy_agent_selects_momentum_for_bull_regime_and_emits_reason_codes() -> None:
    market_data = _market_data([100.0, 100.0, 110.0])
    strategy_agent = StrategyAgent({"momentum": MomentumStrategy(lookback_window=2, entry_threshold=0.02)})
    proposal = strategy_agent.run(
        StrategyAgentInput(
            market_state=market_data,
            technical=_technical_assessment(),
            regime=_regime(),
            portfolio=_portfolio_state(),
            available_strategies=strategy_agent.available_strategies,
        )
    )
    assert proposal.selected_strategy == "momentum"
    assert proposal.action == AgentAction.LONG
    assert StrategyReasonCode.REGIME_STRATEGY_MAP in proposal.reason_codes
    assert StrategyReasonCode.BASELINE_LONG_SIGNAL in proposal.reason_codes


def test_risk_agent_rejects_drawdown_and_reduces_high_volatility_position() -> None:
    proposal = StrategyProposal("momentum", AgentAction.LONG, 0.9, 1.0, (StrategyReasonCode.BASELINE_LONG_SIGNAL,))
    agent = RiskAgent(RiskAgentConfig(max_drawdown=0.10, reduced_volatility_threshold=0.30, reduced_position_size=0.5))
    drawdown_state = _portfolio_state()
    rejected = agent.run(RiskAgentInput(proposal, drawdown_state, volatility=0.1, drawdown=-0.11))
    reduced = agent.run(RiskAgentInput(proposal, _portfolio_state(), volatility=0.35, drawdown=0.0))
    assert rejected.approved is False
    assert rejected.reason_code.value == "MAX_DRAWDOWN_LIMIT"
    assert reduced.approved is True
    assert reduced.adjusted_position_size == 0.5
    assert reduced.reason_code.value == "VOLATILITY_SIZE_REDUCED"


def test_agent_decision_system_integrates_with_backtester_and_keeps_per_bar_audit_history() -> None:
    market_data = FeaturePipeline().generate(
        _market_data([100.0, 100.0, 102.0, 104.0, 106.0, 108.0]),
        {"sma": {"window": 3}, "momentum": {"window": 2}, "rolling_volatility": {"window": 3}, "rsi": {"window": 3}},
    )
    detector = RuleBasedRegimeDetector(
        RuleBasedRegimeDetectorConfig(
            return_window=2,
            volatility_window=2,
            moving_average_window=2,
            moving_average_slope_window=1,
            momentum_window=1,
            drawdown_window=3,
        )
    )
    strategies = {"momentum": MomentumStrategy(lookback_window=2, entry_threshold=0.01)}
    system = AgentDecisionSystem(
        technical_agent=TechnicalAgent(),
        regime_agent=RegimeAgent(detector),
        strategy_agent=StrategyAgent(strategies),
        risk_agent=RiskAgent(),
    )
    result = BacktestEngine(strategies["momentum"], 1000.0, agent_decision_system=system).run(market_data)
    assert len(result.agent_decisions) == len(market_data)
    assert set(result.agent_decisions["execution_action"]).issubset({"long", "hold", "exit"})
    assert {"selected_strategy", "risk_reason_code", "technical_trend"}.issubset(result.agent_decisions.columns)
