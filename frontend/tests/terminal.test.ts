import assert from "node:assert/strict";
import test from "node:test";
import { comparisonRows, drawdownDuration, drawdownSeries, filterActivity, regimeStatistics } from "../lib/terminal";

test("terminal adapters preserve chronology and calculate drawdown duration", () => {
  const series = drawdownSeries([
    { timestamp: "2024-01-01T00:00:00Z", equity: 100 }, { timestamp: "2024-01-02T00:00:00Z", equity: 90 },
    { timestamp: "2024-01-03T00:00:00Z", equity: 80 }, { timestamp: "2024-01-04T00:00:00Z", equity: 105 },
  ]);
  assert.ok(Math.abs(series[2].drawdown + 0.2) < 1e-12);
  assert.equal(drawdownDuration([{ timestamp: "2024-01-01", equity: 100 }, { timestamp: "2024-01-02", equity: 90 }, { timestamp: "2024-01-03", equity: 80 }, { timestamp: "2024-01-04", equity: 105 }]), 2);
});

test("comparison and activity filters use persisted fields only", () => {
  const rows = comparisonRows([{ experiment_id: "EXP-1", created_at: "2024-01-01", strategy: "momentum", asset: "AAA", start_date: "2024-01-01", end_date: "2024-01-02", total_return: .1, sharpe_ratio: 1.2, maximum_drawdown: -.1, number_of_trades: 1, metrics: { total_return: .1, annualized_return: .2, sharpe_ratio: 1.2, sortino_ratio: 1.3, maximum_drawdown: -.1, annualized_volatility: .2, turnover: .3 }, benchmark_metrics: {}, dataset: "data.csv", starting_capital: 100, random_seed: null, regime: {}, agents: {}, final_portfolio: {}, equity_curve: [], benchmark_curve: [], manifest: null }]);
  assert.equal(rows[0].annualizedReturn, .2);
  const events = filterActivity([{ timestamp: "2024-01-01", event_type: "RISK_REJECTED", source: "risk_agent", artifact_id: "EXP-1", summary: "Risk proposal rejected", metadata: {} }], { source: "risk_agent", search: "rejected" });
  assert.equal(events.length, 1);
});

test("regime statistics group persisted causal features", () => {
  const stats = regimeStatistics([{ timestamp: "2024-01-01", regime: "bull", confidence: .8, rolling_return: .01, rolling_volatility: null, moving_average_slope: null, momentum: null, drawdown: null }, { timestamp: "2024-01-02", regime: "bull", confidence: .8, rolling_return: .02, rolling_volatility: null, moving_average_slope: null, momentum: null, drawdown: null }]);
  assert.equal(stats[0].regime, "bull"); assert.equal(stats[0].observations, 2);
});
