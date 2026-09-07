import type { ActivityEvent, CurvePoint, Experiment, RegimeObservation } from "@/lib/api";

export type DrawdownPoint = { timestamp: string; drawdown: number };
export type ComparisonRow = {
  experimentId: string; strategy: string; asset: string; totalReturn: number | null; annualizedReturn: number | null;
  sharpe: number | null; sortino: number | null; maximumDrawdown: number | null; volatility: number | null;
  turnover: number | null; transactionCosts: number | null; robustness: number | null;
};

export function drawdownSeries(equity: CurvePoint[]): DrawdownPoint[] {
  let peak = 0;
  return equity.map((point) => {
    const value = point.equity ?? 0;
    peak = Math.max(peak, value);
    return { timestamp: point.timestamp, drawdown: peak ? value / peak - 1 : 0 };
  });
}

export function drawdownDuration(equity: CurvePoint[]): number {
  let peak = -Infinity; let current = 0; let longest = 0;
  for (const point of equity) {
    const value = point.equity ?? 0;
    if (value >= peak) { peak = value; current = 0; } else { current += 1; longest = Math.max(longest, current); }
  }
  return longest;
}

export function comparisonRows(experiments: Experiment[]): ComparisonRow[] {
  return experiments.map((item) => ({
    experimentId: item.experiment_id, strategy: item.strategy, asset: item.asset, totalReturn: item.metrics.total_return ?? item.total_return,
    annualizedReturn: item.metrics.annualized_return ?? null, sharpe: item.metrics.sharpe_ratio ?? item.sharpe_ratio,
    sortino: item.metrics.sortino_ratio ?? null, maximumDrawdown: item.metrics.maximum_drawdown ?? item.maximum_drawdown,
    volatility: item.metrics.annualized_volatility ?? null, turnover: item.metrics.turnover ?? null,
    transactionCosts: item.metrics.total_transaction_cost ?? null,
    robustness: typeof item.metrics.robustness_score === "number" ? item.metrics.robustness_score : null,
  }));
}

export function mergeEquityCurves(experiments: Experiment[]) {
  const byDate = new Map<string, Record<string, number | string>>();
  for (const experiment of experiments) {
    for (const point of experiment.equity_curve) {
      const timestamp = point.timestamp.slice(0, 10);
      const row = byDate.get(timestamp) ?? { timestamp };
      row[experiment.experiment_id] = point.equity ?? 0;
      byDate.set(timestamp, row);
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)));
}

export function regimeStatistics(items: RegimeObservation[]) {
  const groups = new Map<string, number[]>();
  for (const item of items) {
    if (item.rolling_return === null) continue;
    const values = groups.get(item.regime) ?? [];
    values.push(item.rolling_return); groups.set(item.regime, values);
  }
  return [...groups.entries()].map(([regime, values]) => {
    const averageReturn = values.reduce((sum, value) => sum + value, 0) / values.length;
    const mean = averageReturn;
    const variance = values.length > 1 ? values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1) : 0;
    const sharpe = variance > 0 ? mean / Math.sqrt(variance) * Math.sqrt(252) : null;
    return { regime, observations: values.length, averageReturn, sharpe };
  });
}

export function filterActivity(events: ActivityEvent[], filters: { eventType?: string; source?: string; search?: string }) {
  const search = filters.search?.trim().toLowerCase();
  return events.filter((event) => (!filters.eventType || event.event_type === filters.eventType)
    && (!filters.source || event.source === filters.source)
    && (!search || `${event.event_type} ${event.source} ${event.artifact_id ?? ""} ${event.summary}`.toLowerCase().includes(search)));
}
