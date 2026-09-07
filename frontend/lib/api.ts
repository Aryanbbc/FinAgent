/* Centralized, typed client for the local FinAgent FastAPI contract. */

const configuredApiBase = process.env.NEXT_PUBLIC_FINAGENT_API_URL?.replace(/\/$/, "");
// Local development remains convenient; production must provide the public API URL at build time.
export const apiBase = configuredApiBase ?? (process.env.NODE_ENV === "production" ? "" : "http://127.0.0.1:8000");
// Browser bundles never receive the administrator key.  Hosted deployments
// therefore remain intentionally read-only; administrators use the protected
// backend API from a server-side/local tool with the header documented in
// docs/SECURITY.md.
export const publicMutationControlsEnabled = process.env.NODE_ENV !== "production";

export type MetricMap = Record<string, number | null>;
export type Pagination = { limit: number; offset: number; total: number };
export type ApiFailure = { error_code: string; message: string; details?: unknown; timestamp?: string; request_id?: string };
export type ExperimentSummary = { experiment_id: string; created_at: string; strategy: string; asset: string; start_date: string; end_date: string; total_return: number | null; sharpe_ratio: number | null; maximum_drawdown: number | null; number_of_trades: number | null };
export type Experiment = ExperimentSummary & { dataset: string; starting_capital: number; random_seed: number | null; metrics: MetricMap; benchmark_metrics: MetricMap; regime: { enabled?: boolean; latest?: { regime: string; confidence: number }; distribution?: Record<string, number> }; agents: { enabled?: boolean; latest?: AgentDecision }; final_portfolio: Record<string, number | null>; equity_curve: CurvePoint[]; benchmark_curve: CurvePoint[]; manifest: Record<string, unknown> | null };
export type CurvePoint = { timestamp: string; equity?: number; benchmark_equity?: number };
export type Trade = { timestamp: string; side: string; price: number; quantity: number; transaction_cost: number; portfolio_value: number; realized_pnl: number | null; trade_return: number | null };
export type RegimeObservation = { timestamp: string; regime: string; confidence: number; rolling_return: number | null; rolling_volatility: number | null; moving_average_slope: number | null; momentum: number | null; drawdown: number | null };
export type AgentDecision = { timestamp: string; technical: Record<string, string | number>; regime: { regime: string; confidence: number }; proposal: { selected_strategy: string; action: string; confidence: number; requested_position_size: number; reason_codes: string[] }; risk: { approved: boolean; adjusted_position_size: number; reason_code: string }; execution_action: string };
export type Critique = { experiment_id: string; confidence: number; strengths: Evidence[]; weaknesses: Evidence[]; failure_modes: Evidence[]; regime_observations: Record<string, unknown>[]; recommendations: Evidence[]; reason_codes: string[] };
export type Evidence = { code: string; summary: string; evidence?: Record<string, unknown> };
export type Version = { version_id: string; parent_version_id: string | null; candidate_id: string | null; created_at: string; status: string; reason_codes: string[]; validation_metrics: MetricMap | null };
export type Improvement = { run_id: string; parent_version_id: string; status: string; reason_codes: string[]; parent_metrics: MetricMap; candidate_metrics: MetricMap; window_pass_rate: number; parameter_changes?: Record<string, unknown>[]; windows?: Record<string, unknown>[] };
export type ValidationSummary = { validation_id: string; experiment_id: string; robustness_score: number; leakage_passed: boolean; asset_count: number; window_count: number };
export type Validation = { validation_id: string; experiment_id: string; aggregate_metrics: MetricMap; robustness: { score: number; components: Record<string, number>; weights: Record<string, number> }; leakage: { passed: boolean; checks: Record<string, boolean>; errors: string[] }; confidence_intervals: Record<string, unknown>[]; asset_results: Record<string, unknown>[]; windows: Record<string, unknown>[]; sensitivity: Record<string, unknown>[]; ablations: Record<string, unknown>[]; benchmarks: Record<string, unknown>[] };
export type System = { finagent_version: string; database_path: string; database_exists: boolean; database_size_bytes: number; database_backend: "sqlite" | "postgresql"; database_connectivity: boolean; git_revision: string | null; experiment_count: number; configuration_version_count: number; latest_experiment_id: string | null; dataset_count: number; latest_dataset_refresh: string | null; data_providers: DataProvider[]; data_quality_warnings: number; database_status: string; database_integrity: string | null; latest_experiment_at: string | null; latest_validation_at: string | null; last_successful_run: string | null; frontend_version: string | null; enabled_modules: string[]; demo_mode: boolean };
export type DataProvider = { provider: string; historical_only: boolean; intervals: string[]; requires_credentials: boolean; available: boolean };
export type DatasetSummary = { dataset_id: string; version_id: string; version_number: number; provider: string; symbol: string; asset_class: string; exchange: string | null; interval: string; start_date: string; end_date: string; row_count: number; checksum: string; created_at: string; last_refreshed_at: string; validation_status: string; quality_score: number };
export type Dataset = DatasetSummary & { cache_path: string; metadata: Record<string, unknown>; validation: { status: string; issues: { code: string; severity: string; message: string; count: number }[]; quality: { score: number; components: Record<string, number>; suspicious_gap_count: number }; policy: string }; sample_rows: OhlcvRow[]; versions: DatasetSummary[] };
export type OhlcvRow = { timestamp: string; open: number; high: number; low: number; close: number; volume: number };
export type OhlcvSeries = { dataset_id: string | null; version_id: string | null; items: OhlcvRow[]; downsampled: boolean };
export type ActivityEvent = { timestamp: string; event_type: string; source: string; artifact_id: string | null; summary: string; metadata: Record<string, unknown> };
export type LiveFeedStatus = "CONNECTING" | "PRE_MARKET" | "LIVE" | "AFTER_HOURS" | "MARKET_CLOSED" | "DELAYED" | "RECONNECTING" | "RATE_LIMITED" | "OFFLINE";
export type LiveProviderHealth = "CONNECTING" | "OK" | "RECONNECTING" | "RATE_LIMITED" | "OFFLINE";
export type LiveBar = OhlcvRow & { symbol: string; provider: string };
export type LiveFeedState = { symbol: string; enabled: boolean; status: LiveFeedStatus; provider_health: LiveProviderHealth; market_state: "PRE_MARKET" | "LIVE" | "AFTER_HOURS" | "MARKET_CLOSED"; provider: string; feed_mode: "polling"; interval: "1min" | "5min" | "15min"; last_updated: string | null; last_successful_update: string | null; last_market_bar_timestamp: string | null; last_successful_provider_poll: string | null; message: string | null; bars_buffered: number };
export type LiveSignal = { symbol: string; timestamp: string; price: number; provider: string; technical: Record<string, unknown>; regime: { timestamp: string; regime: string; confidence: number; features: Record<string, number | null> }; strategy: { selected_strategy: string; action: string; confidence: number; requested_position_size: number; reason_codes: string[] }; action: "BUY" | "HOLD" | "EXIT"; confidence: number; risk: { approved: boolean; adjusted_position_size: number; reason_code: string }; reason_codes: string[] };
export type LiveSnapshot = LiveFeedState & { latest: LiveBar | null; current_regime: LiveSignal["regime"] | null; latest_signal: LiveSignal | null };
export type LiveEvent = { timestamp: string; event_type: string; provider: string; feed_status: LiveFeedStatus; summary: string; metadata: Record<string, unknown> };
export type DataFetchInput = { provider: string; symbol: string; start_date: string; end_date: string; interval: "1d"; force_refresh: boolean; source_path?: string; asset_class?: string; missing_data_policy?: "reject" | "forward_fill" | "drop" | "warn_only" };
export type DataFetchResult = { dataset: DatasetSummary; cache_hit: boolean; requested_provider: string; actual_provider: string; fallback_used: boolean; attempts: { provider: string | null; attempt: number; status: number | null; reason: string; retryable: boolean }[] };
export type ExperimentRunInput = {
  config_path: string; dataset_id?: string; strategy_name?: "moving_average" | "momentum" | "mean_reversion";
  agents_enabled?: boolean; starting_capital?: number; percentage_fee?: number; fixed_fee?: number;
  position_fraction?: number; risk_max_position_size?: number; risk_max_drawdown?: number;
  risk_max_volatility?: number; start_date?: string; end_date?: string;
};

export class ApiError extends Error {
  constructor(public status: number, message: string, public code = "REQUEST_FAILED", public details?: unknown, public requestId?: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as Partial<ApiFailure> & { detail?: { message?: string } | string };
    const legacy = typeof body.detail === "object" ? body.detail?.message : body.detail;
    throw new ApiError(response.status, body.message ?? legacy ?? `Request failed (${response.status})`, body.error_code ?? "REQUEST_FAILED", body.details, body.request_id);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: "ok" | "degraded"; version: string; database_status: string; database_backend: "sqlite" | "postgresql"; database_connectivity: boolean; dataset_registry_status: string; latest_experiment_at: string | null; latest_validation_at: string | null }>("/api/health"),
  experiments: (query = "") => request<{ items: ExperimentSummary[]; pagination: Pagination }>(`/api/experiments${query}`),
  experiment: (id: string) => request<Experiment>(`/api/experiments/${id}`),
  trades: (id: string) => request<{ experiment_id: string; items: Trade[] }>(`/api/experiments/${id}/trades`),
  regimes: (id: string) => request<{ experiment_id: string; distribution: Record<string, number>; items: RegimeObservation[]; best_strategies: Record<string, { experiment_id: string; strategy: string; regime_return: number }[]>; worst_strategies: Record<string, { experiment_id: string; strategy: string; regime_return: number }[]>; strategy_performance: { regime: string; observations: number; compounded_return: number }[] }>(`/api/experiments/${id}/regimes`),
  experimentMarketData: (id: string, query = "") => request<OhlcvSeries>(`/api/experiments/${id}/market-data${query}`),
  activity: (query = "") => request<{ items: ActivityEvent[]; pagination: Pagination }>(`/api/experiments/activity/recent${query}`),
  decisions: (id: string, query = "") => request<{ experiment_id: string; items: AgentDecision[]; pagination: Pagination }>(`/api/experiments/${id}/agent-decisions${query}`),
  critique: (id: string) => request<Critique>(`/api/experiments/${id}/critique`),
  versions: () => request<{ items: Version[] }>("/api/versions"),
  improvements: (query = "") => request<{ items: Improvement[]; pagination: Pagination }>(`/api/improvements${query}`),
  improvement: (id: string) => request<Improvement>(`/api/improvements/${id}`),
  validations: (query = "") => request<{ items: ValidationSummary[]; pagination: Pagination }>(`/api/validation${query}`),
  validation: (id: string) => request<Validation>(`/api/validation/${id}`),
  report: (id: string) => request<{ experiment_id: string; markdown: string; download_url: string }>(`/api/reports/${id}`),
  configuration: () => request<{ safe_defaults: Record<string, unknown>; capabilities: Record<string, boolean>; warnings: string[] }>("/api/config"),
  system: () => request<System>("/api/system"),
  dataProviders: () => request<DataProvider[]>("/api/data/providers"),
  datasets: (query = "") => request<{ items: DatasetSummary[]; pagination: Pagination }>(`/api/data/datasets${query}`),
  dataset: (id: string) => request<Dataset>(`/api/data/datasets/${id}`),
  datasetOhlcv: (id: string, query = "") => request<OhlcvSeries>(`/api/data/datasets/${id}/ohlcv${query}`),
  fetchData: (input: DataFetchInput) => request<DataFetchResult>("/api/data/fetch", { method: "POST", body: JSON.stringify(input) }),
  validateData: (dataset_id: string, missing_data_policy = "reject") => request<DatasetSummary>("/api/data/validate", { method: "POST", body: JSON.stringify({ dataset_id, missing_data_policy }) }),
  dataCollections: (query = "") => request<{ items: { collection_id: string; name: string; description: string | null; members: { dataset_id: string; version_id: string; symbol: string; adjustment_mode: string }[]; created_at: string | null; warnings: string[] }[]; pagination: Pagination }>(`/api/data/collections${query}`),
  liveStatus: () => request<{ enabled: boolean; provider: string; feed_mode: "polling"; poll_seconds: number; interval: "1min" | "5min" | "15min"; symbols: LiveFeedState[]; execution: "disabled" }>("/api/live/status"),
  liveSymbols: () => request<{ items: { symbol: string; provider: string; interval: string }[] }>("/api/live/symbols"),
  liveSnapshot: (symbol: string) => request<LiveSnapshot>(`/api/live/snapshot/${encodeURIComponent(symbol)}`),
  liveHistory: (symbol: string) => request<{ symbol: string; items: LiveBar[] }>(`/api/live/history/${encodeURIComponent(symbol)}`),
  liveSignals: (symbol: string, query = "?limit=50") => request<{ symbol: string; items: LiveSignal[] }>(`/api/live/signals/${encodeURIComponent(symbol)}${query}`),
  liveEvents: (symbol: string, query = "?limit=100") => request<{ symbol: string; items: LiveEvent[] }>(`/api/live/events/${encodeURIComponent(symbol)}${query}`),
  run: (workflow: "experiments" | "improvements" | "validation", input: string | ExperimentRunInput, dataset_id?: string) => {
    const payload = typeof input === "string" ? { config_path: input, ...(dataset_id ? { dataset_id } : {}) } : input;
    return request(`/api/${workflow}/run`, { method: "POST", body: JSON.stringify(payload) });
  },
};
