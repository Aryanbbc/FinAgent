/* Centralized, typed client for the local FinAgent FastAPI contract. */

export const apiBase = process.env.NEXT_PUBLIC_FINAGENT_API_URL ?? "http://127.0.0.1:8000";

export type MetricMap = Record<string, number | null>;
export type Pagination = { limit: number; offset: number; total: number };
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
export type System = { finagent_version: string; database_path: string; database_exists: boolean; database_size_bytes: number; git_revision: string | null; experiment_count: number; configuration_version_count: number; latest_experiment_id: string | null };

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, cache: "no-store" });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new ApiError(response.status, body.detail?.message ?? body.detail ?? `Request failed (${response.status})`); }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),
  experiments: (query = "") => request<{ items: ExperimentSummary[]; pagination: Pagination }>(`/api/experiments${query}`),
  experiment: (id: string) => request<Experiment>(`/api/experiments/${id}`),
  trades: (id: string) => request<{ experiment_id: string; items: Trade[] }>(`/api/experiments/${id}/trades`),
  regimes: (id: string) => request<{ experiment_id: string; distribution: Record<string, number>; items: RegimeObservation[]; best_strategies: Record<string, { experiment_id: string; strategy: string; regime_return: number }[]> }>(`/api/experiments/${id}/regimes`),
  decisions: (id: string) => request<{ experiment_id: string; items: AgentDecision[] }>(`/api/experiments/${id}/agent-decisions`),
  critique: (id: string) => request<Critique>(`/api/experiments/${id}/critique`),
  versions: () => request<{ items: Version[] }>("/api/versions"),
  improvements: () => request<{ items: Improvement[]; pagination: Pagination }>("/api/improvements"),
  improvement: (id: string) => request<Improvement>(`/api/improvements/${id}`),
  validations: () => request<{ items: ValidationSummary[]; pagination: Pagination }>("/api/validation"),
  validation: (id: string) => request<Validation>(`/api/validation/${id}`),
  report: (id: string) => request<{ experiment_id: string; markdown: string; download_url: string }>(`/api/reports/${id}`),
  configuration: () => request<{ safe_defaults: Record<string, unknown>; capabilities: Record<string, boolean> }>("/api/config"),
  system: () => request<System>("/api/system"),
  run: (workflow: "experiments" | "improvements" | "validation", config_path: string) => request(`/api/${workflow}/run`, { method: "POST", body: JSON.stringify({ config_path }) }),
};
