"""Stable Pydantic response and request models for the local V0.9 API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(APIModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    database_status: str = "ok"
    dataset_registry_status: str = "ok"
    latest_experiment_at: str | None = None
    latest_validation_at: str | None = None


class ErrorResponse(APIModel):
    error_code: str
    message: str
    details: dict[str, Any] | list[dict[str, Any]] | None = None
    timestamp: str
    request_id: str | None = None
    # Retained only as a V0.7/V0.8 compatibility bridge for existing local clients.
    detail: dict[str, str] | None = None


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
    pagination: PaginationMeta


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
    warnings: list[str] = Field(default_factory=list)


class SystemResponse(APIModel):
    finagent_version: str
    database_path: str
    database_exists: bool
    database_size_bytes: int
    git_revision: str | None = None
    experiment_count: int
    configuration_version_count: int
    latest_experiment_id: str | None = None
    dataset_count: int = 0
    latest_dataset_refresh: str | None = None
    data_providers: list[dict[str, Any]] = Field(default_factory=list)
    data_quality_warnings: int = 0
    database_status: str = "unknown"
    database_integrity: str | None = None
    latest_experiment_at: str | None = None
    latest_validation_at: str | None = None
    last_successful_run: str | None = None
    frontend_version: str | None = None
    enabled_modules: list[str] = Field(default_factory=list)
    demo_mode: bool = False


class DataProviderResponse(APIModel):
    provider: str
    historical_only: bool
    intervals: list[str]
    requires_credentials: bool


class DatasetSummary(APIModel):
    dataset_id: str
    version_id: str
    version_number: int
    provider: str
    symbol: str
    asset_class: str
    exchange: str | None = None
    interval: str
    start_date: str
    end_date: str
    row_count: int
    checksum: str
    created_at: str
    last_refreshed_at: str
    validation_status: str
    quality_score: float


class DatasetListResponse(APIModel):
    items: list[DatasetSummary]
    pagination: PaginationMeta


class DatasetDetail(DatasetSummary):
    cache_path: str
    metadata: dict[str, Any]
    validation: dict[str, Any]
    sample_rows: list[dict[str, Any]]
    versions: list[DatasetSummary]


class DataFetchRequest(APIModel):
    provider: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9_]+$")
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._^=-]+$")
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    interval: Literal["1d"] = "1d"
    force_refresh: bool = False
    source_path: str | None = Field(default=None, max_length=300)
    asset_class: str = Field(default="equity", max_length=40)
    missing_data_policy: Literal["reject", "forward_fill", "drop", "warn_only"] = "reject"


class DataFetchResponse(APIModel):
    dataset: DatasetSummary
    cache_hit: bool


class DataValidateRequest(APIModel):
    dataset_id: str = Field(min_length=6, max_length=120, pattern=r"^DATA-[A-Z0-9-]+$")
    missing_data_policy: Literal["reject", "forward_fill", "drop", "warn_only"] = "reject"


class DatasetCollectionResponse(APIModel):
    collection_id: str
    name: str
    description: str | None = None
    members: list[dict[str, str]]
    created_at: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CollectionsResponse(APIModel):
    items: list[DatasetCollectionResponse]
    pagination: PaginationMeta


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
