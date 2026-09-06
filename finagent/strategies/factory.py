"""Configuration-driven construction of registered V0.1 strategies."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from finagent.strategies.base import Strategy
from finagent.strategies.mean_reversion import MeanReversionStrategy
from finagent.strategies.momentum import MomentumStrategy
from finagent.strategies.moving_average import MovingAverageCrossoverStrategy


def create_strategy(name: str, parameters: Mapping[str, Any] | None = None) -> Strategy:
    """Return a baseline strategy by its stable configuration name."""
    strategy_parameters = dict(parameters or {})
    registry: dict[str, type[Strategy]] = {
        "moving_average": MovingAverageCrossoverStrategy,
        "momentum": MomentumStrategy,
        "mean_reversion": MeanReversionStrategy,
    }
    try:
        return registry[name](**strategy_parameters)  # type: ignore[call-arg]
    except KeyError as error:
        choices = ", ".join(sorted(registry))
        raise ValueError(f"Unknown strategy '{name}'. Available strategies: {choices}") from error
