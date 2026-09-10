import type { Improvement, MetricMap } from "@/lib/api";

export type GateCheck = {
  id: string;
  label: string;
  tooltip: string;
  state: "pass" | "fail" | "unknown";
  evidence: string;
};

const explanations: Record<string, string> = {
  EXCESSIVE_TURNOVER_REJECTED: "Candidate traded too aggressively and exceeded the allowed turnover limit.",
  TRANSACTION_COSTS_ERASE_ADVANTAGE: "The candidate’s apparent advantage disappeared after transaction costs.",
  OUT_OF_SAMPLE_SHARPE_NOT_IMPROVED: "Risk-adjusted performance did not improve enough on unseen data.",
  MAXIMUM_DRAWDOWN_EXCEEDED: "Candidate drawdown exceeded the maximum loss limit.",
  INCONSISTENT_OUT_OF_SAMPLE_RESULTS: "Too few walk-forward windows improved on the parent configuration.",
  INSUFFICIENT_TRADES: "Too few simulated trades were available for the promotion requirement.",
  INSUFFICIENT_SAMPLE: "There were not enough chronological walk-forward windows to evaluate this candidate.",
  INVALID_METRICS: "One or more required validation metrics were unavailable or invalid.",
  DUPLICATE_OUT_OF_SAMPLE_OUTCOME: "This configuration produced evidence identical to a candidate already evaluated.",
  NOT_SELECTED: "Another qualifying candidate ranked ahead of this candidate in the same controlled cycle.",
  ROBUSTNESS_SCORE_TOO_LOW: "The persisted robustness evidence was below the required threshold.",
  INSUFFICIENT_ASSET_COVERAGE: "The candidate did not meet the required multi-asset coverage.",
  UNSTABLE_SENSITIVITY_PROFILE: "Parameter sensitivity evidence was not stable enough for promotion.",
  LEAKAGE_CHECK_FAILED: "The required no-leakage validation did not pass.",
  CONFIDENCE_INTERVAL_UNACCEPTABLE: "Confidence-interval evidence did not meet the required standard.",
};

export function reasonExplanation(code: string): string {
  return explanations[code] ?? code.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase());
}

export function humanCode(code: string): string {
  return code.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function metric(metrics: MetricMap, key: string): number | null {
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function valueText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function checkState(reasons: string[], failureCode: string): "pass" | "fail" | "unknown" {
  if (reasons.includes(failureCode)) return "fail";
  if (reasons.includes("INVALID_METRICS") || reasons.includes("INSUFFICIENT_SAMPLE")) return "unknown";
  return "pass";
}

function numberText(value: number | null, digits = 2): string {
  return value === null ? "—" : value.toFixed(digits);
}

export function promotionChecks(candidate: Improvement): GateCheck[] {
  const candidateMetrics = candidate.candidate_metrics;
  const parentMetrics = candidate.parent_metrics;
  return [
    {
      id: "sharpe", label: "Sharpe improvement", tooltip: "OOS means out-of-sample: evidence measured on chronological data not used to fit the candidate.",
      state: checkState(candidate.reason_codes, "OUT_OF_SAMPLE_SHARPE_NOT_IMPROVED"),
      evidence: `Candidate ${numberText(metric(candidateMetrics, "sharpe_ratio"))} · parent ${numberText(metric(parentMetrics, "sharpe_ratio"))}`,
    },
    {
      id: "drawdown", label: "Maximum drawdown", tooltip: "Largest peak-to-trough loss during the held-out simulation.",
      state: checkState(candidate.reason_codes, "MAXIMUM_DRAWDOWN_EXCEEDED"),
      evidence: `Candidate ${numberText(metric(candidateMetrics, "maximum_drawdown") === null ? null : metric(candidateMetrics, "maximum_drawdown")! * 100)}%`,
    },
    {
      id: "pass-rate", label: "Window pass rate", tooltip: "Share of chronological walk-forward windows whose OOS Sharpe beat the parent.",
      state: checkState(candidate.reason_codes, "INCONSISTENT_OUT_OF_SAMPLE_RESULTS"),
      evidence: `${(candidate.window_pass_rate * 100).toFixed(0)}% of persisted windows`,
    },
    {
      id: "trades", label: "Minimum trades", tooltip: "A minimum simulated trade count prevents decisions from relying on too little evidence.",
      state: checkState(candidate.reason_codes, "INSUFFICIENT_TRADES"),
      evidence: `${numberText(metric(candidateMetrics, "number_of_trades"), 0)} simulated trades`,
    },
    {
      id: "turnover", label: "Maximum turnover", tooltip: "Turnover is gross traded notional relative to average portfolio equity. Lower values indicate less churn.",
      state: checkState(candidate.reason_codes, "EXCESSIVE_TURNOVER_REJECTED"),
      evidence: `Turnover ${numberText(metric(candidateMetrics, "turnover"))}`,
    },
    {
      id: "costs", label: "Transaction-cost advantage", tooltip: "A candidate must retain its return advantage after the configured simulated transaction costs.",
      state: checkState(candidate.reason_codes, "TRANSACTION_COSTS_ERASE_ADVANTAGE"),
      evidence: `Return ${numberText(metric(candidateMetrics, "total_return") === null ? null : metric(candidateMetrics, "total_return")! * 100)}% · parent ${numberText(metric(parentMetrics, "total_return") === null ? null : metric(parentMetrics, "total_return")! * 100)}%`,
    },
  ];
}
