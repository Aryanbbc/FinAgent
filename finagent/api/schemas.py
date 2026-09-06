"""Stable Pydantic response and request models for the local V0.7 API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(APIModel):
    status: Literal["ok"]
    service: str
    version: str


class PaginationMeta(APIModel):
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


class ExperimentSummary(APIModel):
    experiment_id: str
    created_at: str
    strategy: str
    asset: str
    start_date: str
    end_date: str
    total_return: float | None = None
    sharpe_ratio: float | None = None
    maximum_drawdown: float | None = None
    number_of_trades: int | None = None


class ExperimentDetail(ExperimentSummary):
    dataset: str
    starting_capital: float
    random_seed: int | None = None
    metrics: dict[str, float | int | None]
    benchmark_metrics: dict[str, float | int | None]
    regime: dict[str, Any]
    agents: dict[str, Any]
    final_portfolio: dict[str, float | int | None]
    equity_curve: list[dict[str, Any]]
    benchmark_curve: list[dict[str, Any]]
    manifest: dict[str, Any] | None = None


class ExperimentListResponse(APIModel):
    items: list[ExperimentSummary]
    pagination: PaginationMeta


class Trade(APIModel):
    timestamp: str
    side: str
    price: float
    quantity: float
    transaction_cost: float
    portfolio_value: float
    realized_pnl: float | None = None
    trade_return: float | None = None


class TradesResponse(APIModel):
    experiment_id: str
    items: list[Trade]


class RegimeObservation(APIModel):
    timestamp: str
    regime: str
    confidence: float
    rolling_return: float | None = None
    rolling_volatility: float | None = None
    moving_average_slope: float | None = None
    momentum: float | None = None
    drawdown: float | None = None


class RegimesResponse(APIModel):
    experiment_id: str
    distribution: dict[str, int]
    items: list[RegimeObservation]
    best_strategies: dict[str, list[dict[str, Any]]]


class AgentDecision(APIModel):
    timestamp: str
    technical: dict[str, Any]
    regime: dict[str, Any]
    proposal: dict[str, Any]
    risk: dict[str, Any]
    execution_action: str


class AgentDecisionsResponse(APIModel):
    experiment_id: str
    items: list[AgentDecision]


class CritiqueResponse(APIModel):
    experiment_id: str
    confidence: float
    strengths: list[dict[str, Any]]
    weaknesses: list[dict[str, Any]]
    failure_modes: list[dict[str, Any]]
    regime_observations: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    reason_codes: list[str]


class ConfigurationVersion(APIModel):
    version_id: str
    parent_version_id: str | None = None
    candidate_id: str | None = None
    created_at: str
    status: str
    reason_codes: list[str]
    validation_metrics: dict[str, float | int | None] | None = None


class VersionsResponse(APIModel):
    items: list[ConfigurationVersion]


class Improvement(APIModel):
    run_id: str
    parent_version_id: str
    status: str
    reason_codes: list[str]
    parent_metrics: dict[str, float | int | None]
    candidate_metrics: dict[str, float | int | None]
    window_pass_rate: float
    parameter_changes: list[dict[str, Any]] = Field(default_factory=list)


class ImprovementsResponse(APIModel):
    items: list[Improvement]
    pagination: PaginationMeta


class ImprovementDetail(Improvement):
    windows: list[dict[str, Any]]


class ValidationSummary(APIModel):
    validation_id: str
    experiment_id: str
    robustness_score: float
    leakage_passed: bool
    asset_count: int
    window_count: int


class ValidationListResponse(APIModel):
    items: list[ValidationSummary]
    pagination: PaginationMeta


class ValidationDetail(APIModel):
    validation_id: str
    experiment_id: str
    aggregate_metrics: dict[str, float | int | None]
    robustness: dict[str, Any]
    leakage: dict[str, Any]
    confidence_intervals: list[dict[str, Any]]
    asset_results: list[dict[str, Any]]
    windows: list[dict[str, Any]]
    sensitivity: list[dict[str, Any]]
    ablations: list[dict[str, Any]]
    benchmarks: list[dict[str, Any]]


class ReportResponse(APIModel):
    experiment_id: str
    markdown: str
    download_url: str


class ConfigResponse(APIModel):
    safe_defaults: dict[str, Any]
    capabilities: dict[str, bool]


class SystemResponse(APIModel):
    finagent_version: str
    database_path: str
    database_exists: bool
    database_size_bytes: int
    git_revision: str | None = None
    experiment_count: int
    configuration_version_count: int
    latest_experiment_id: str | None = None


class RunRequest(APIModel):
    config_path: str = Field(
        ...,
        min_length=12,
        max_length=160,
        pattern=r"^config/[A-Za-z0-9_./-]+\.ya?ml$",
    )


class ExecutionResponse(APIModel):
    workflow: Literal["experiment", "improvement", "validation"]
    status: Literal["completed", "disabled"]
    experiment_id: str | None = None
    run_id: str | None = None
    validation_id: str | None = None
    metadata: dict[str, Any]
    mode: Literal["local_historical_simulation"] = "local_historical_simulation"
