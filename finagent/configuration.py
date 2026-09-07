"""Typed, conservative validation for FinAgent research configurations.

The runtime still accepts the established YAML shape.  This module validates the
small set of fields that can make a historical simulation unsafe or surprising,
while retaining compatibility with V0.1--V0.8 optional sections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ConfigurationValidationError(ValueError):
    """Raised when a research configuration cannot be safely executed."""


class _ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset: str = Field(min_length=1, max_length=64)
    dataset: str | None = None
    dataset_id: str | None = None
    starting_capital: float = Field(gt=0, le=1_000_000_000)
    random_seed: int | None = None

    @model_validator(mode="after")
    def validate_dataset_source(self) -> "_ExperimentConfig":
        if not self.dataset_id and not self.dataset:
            raise ValueError("either experiment.dataset or experiment.dataset_id is required")
        return self


class _StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class _TransactionCosts(BaseModel):
    model_config = ConfigDict(extra="allow")

    percentage_fee: float = Field(default=0.0, ge=0, le=0.1)
    fixed_fee: float = Field(default=0.0, ge=0, le=100_000)


class _BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    annualization_factor: int = Field(default=252, ge=1, le=366)
    position_fraction: float = Field(default=1.0, ge=0, le=1)
    transaction_costs: _TransactionCosts = Field(default_factory=_TransactionCosts)


class _SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    live_trading_enabled: bool = False


class _TypedConfiguration(BaseModel):
    model_config = ConfigDict(extra="allow")

    application: _SafetyConfig = Field(default_factory=_SafetyConfig)
    experiment: _ExperimentConfig
    strategy: _StrategyConfig
    backtest: _BacktestConfig = Field(default_factory=_BacktestConfig)
    agents: dict[str, Any] = Field(default_factory=dict)
    critic: dict[str, Any] = Field(default_factory=dict)
    learning: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ConfigurationValidationResult:
    """Validated configuration diagnostics returned to API and CLI callers."""

    warnings: tuple[str, ...] = ()


def validate_research_configuration(configuration: dict[str, Any]) -> ConfigurationValidationResult:
    """Validate critical fields and return explicit non-blocking diagnostics.

    The function deliberately rejects any configuration that requests live
    execution.  All remaining V0.1--V0.8 extension keys are allowed and passed
    through untouched to the existing deterministic workflows.
    """

    try:
        typed = _TypedConfiguration.model_validate(configuration)
    except ValidationError as error:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
        )
        raise ConfigurationValidationError(messages) from error

    if typed.application.live_trading_enabled:
        raise ConfigurationValidationError("application.live_trading_enabled must remain false for local research")

    # Apply resource bounds to YAML workflows as well as the smaller API
    # override surface.  Configuration is not a vehicle for arbitrary scale.
    for section_name, section in (("learning", typed.learning), ("validation", typed.validation)):
        if not isinstance(section, dict):
            continue
        search = section.get("search", {})
        if isinstance(search, dict) and int(search.get("max_candidates", 5)) > 5:
            raise ConfigurationValidationError(f"{section_name}.search.max_candidates must not exceed 5")
        walk_forward = section.get("walk_forward", {})
        if isinstance(walk_forward, dict):
            for key, maximum in (("train_size", 10_000), ("test_size", 5_000), ("step_size", 5_000), ("min_windows", 100)):
                if key in walk_forward and int(walk_forward[key]) > maximum:
                    raise ConfigurationValidationError(f"{section_name}.walk_forward.{key} must not exceed {maximum}")
        bootstrap = section.get("bootstrap", {})
        if isinstance(bootstrap, dict) and int(bootstrap.get("samples", 1_000)) > 10_000:
            raise ConfigurationValidationError(f"{section_name}.bootstrap.samples must not exceed 10000")

    warnings: list[str] = []
    if typed.backtest.position_fraction == 0:
        warnings.append("position_fraction is zero; the experiment will not open positions")
    if typed.backtest.transaction_costs.percentage_fee >= 0.05:
        warnings.append("percentage transaction fee is unusually high (5% or more)")
    if typed.backtest.annualization_factor not in {252, 365}:
        warnings.append("annualization_factor differs from common daily-data conventions")
    if bool(typed.learning.get("enabled", False)) and not bool(typed.critic.get("enabled", False)):
        warnings.append("learning is enabled but critic evidence is not enabled in this source configuration")
    return ConfigurationValidationResult(tuple(warnings))
