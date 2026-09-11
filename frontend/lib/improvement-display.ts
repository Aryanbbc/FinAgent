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

export type CandidateChangeRow = { label: string; previous: string; proposed: string };
export type CandidateChangeGroup = { label: string; rows: CandidateChangeRow[] };

type ParameterChange = { parameter?: unknown; previous_value?: unknown; proposed_value?: unknown };

const parameterLabels: Record<string, string> = {
  minimum_holding_period_bars: "Holding Period",
  reentry_cooldown_bars: "Re-entry Cooldown",
  maximum_position_size: "Max Position Size",
  maximum_volatility: "Max Volatility",
  risk_confidence_threshold: "Risk Confidence",
  moving_average_fast_window: "Moving Average Fast Window",
  moving_average_slow_window: "Moving Average Slow Window",
  momentum_window: "Momentum Window",
  mean_reversion_window: "Mean Reversion Window",
  mean_reversion_threshold: "Mean Reversion Threshold",
  momentum_entry_threshold: "Momentum Entry Threshold",
  momentum_exit_threshold: "Momentum Exit Threshold",
  strategy_weights: "Strategy Weights",
  regime_strategy_mappings: "Regime Mapping",
  execution_controls: "Execution Controls",
};

const riskParameters = new Set([
  "maximum_position_size",
  "maximum_volatility",
  "risk_confidence_threshold",
]);

const strategyParameters = new Set([
  "moving_average_fast_window",
  "moving_average_slow_window",
  "momentum_window",
  "mean_reversion_window",
  "mean_reversion_threshold",
  "momentum_entry_threshold",
  "momentum_exit_threshold",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sameValue(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (isRecord(left) && isRecord(right)) {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return leftKeys.length === rightKeys.length && leftKeys.every((key) => key in right && sameValue(left[key], right[key]));
  }
  if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((item, index) => sameValue(item, right[index]));
  return false;
}

function compactNumber(value: number) {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
}

function leafLabel(parameter: string) {
  return parameterLabels[parameter] ?? humanCode(parameter.replaceAll(".", "_"));
}

function groupLabel(parameter: string) {
  if (parameter === "execution_controls") return "Execution Controls";
  if (parameter === "strategy_weights") return "Strategy Weights";
  if (parameter === "regime_strategy_mappings") return "Regime Mapping";
  if (riskParameters.has(parameter)) return "Risk";
  if (strategyParameters.has(parameter)) return "Strategy Parameters";
  return "Other Changes";
}

function isPercentage(parameter: string, group?: string) {
  return group === "strategy_weights" || ["maximum_position_size", "maximum_volatility"].includes(parameter);
}

function isBars(parameter: string) {
  return parameter.endsWith("_window") || parameter.endsWith("_period_bars") || parameter.endsWith("_cooldown_bars");
}

function formattedValue(value: unknown, parameter: string, group?: string): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Enabled" : "Disabled";
  if (typeof value === "number") {
    if (isPercentage(parameter, group)) return `${compactNumber(value * 100)}%`;
    return `${compactNumber(value)}${isBars(parameter) ? " bars" : ""}`;
  }
  if (typeof value === "string") return humanCode(value);
  if (Array.isArray(value)) return value.map((item) => formattedValue(item, parameter, group)).join(", ");
  // A supported parameter mapping is flattened before this formatter. This
  // fallback avoids emitting serialized objects for unexpected legacy data.
  return "Structured value";
}

function emptyValueDefault(group: string, parameter: string): unknown {
  if (group === "execution_controls" && ["minimum_holding_period_bars", "reentry_cooldown_bars"].includes(parameter)) return 0;
  if (group === "strategy_weights") return 0;
  return undefined;
}

function flattenedRows(
  group: string,
  previous: unknown,
  proposed: unknown,
): CandidateChangeRow[] {
  const before = isRecord(previous) ? previous : {};
  const after = isRecord(proposed) ? proposed : {};
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
  return keys.flatMap((key) => {
    const oldValue = key in before ? before[key] : emptyValueDefault(group, key);
    const newValue = key in after ? after[key] : undefined;
    if (isRecord(oldValue) || isRecord(newValue)) return flattenedRows(group, oldValue, newValue);
    if (sameValue(oldValue, newValue)) return [];
    return [{ label: leafLabel(key), previous: formattedValue(oldValue, key, group), proposed: formattedValue(newValue, key, group) }];
  });
}

/** Convert persisted candidate deltas into compact, non-debug UI rows. */
export function candidateChangeGroups(changes: ParameterChange[] | undefined): CandidateChangeGroup[] {
  const groups: CandidateChangeGroup[] = [];
  const byLabel = new Map<string, CandidateChangeGroup>();
  for (const change of changes ?? []) {
    const parameter = typeof change.parameter === "string" ? change.parameter : "unknown_parameter";
    const previous = change.previous_value;
    const proposed = change.proposed_value;
    const structured = isRecord(previous) || isRecord(proposed);
    const rows = structured
      ? flattenedRows(parameter, previous, proposed)
      : sameValue(previous, proposed)
        ? []
        : [{ label: leafLabel(parameter), previous: formattedValue(previous, parameter), proposed: formattedValue(proposed, parameter) }];
    if (!rows.length) continue;
    const label = groupLabel(parameter);
    const existing = byLabel.get(label);
    if (existing) existing.rows.push(...rows);
    else {
      const group = { label, rows };
      groups.push(group);
      byLabel.set(label, group);
    }
  }
  return groups;
}

export function candidateChangeSummary(changes: ParameterChange[] | undefined): string {
  return candidateChangeGroups(changes)
    .flatMap((group) => group.rows.map((row) => `${group.label} · ${row.label}: ${row.previous} → ${row.proposed}`))
    .join("; ");
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
