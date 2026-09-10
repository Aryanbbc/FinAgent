import assert from "node:assert/strict";
import test from "node:test";
import { dashboardContextUrl, experimentForAsset } from "../lib/dashboard-context";

const experiments = [
  { experiment_id: "EXP-000001", asset: "MSFT", created_at: "2024-01-01", strategy: "momentum", start_date: "2024-01-01", end_date: "2024-02-01", total_return: null, sharpe_ratio: null, maximum_drawdown: null, number_of_trades: null },
  { experiment_id: "EXP-000002", asset: "AAPL", created_at: "2024-01-02", strategy: "moving_average", start_date: "2024-01-01", end_date: "2024-02-01", total_return: null, sharpe_ratio: null, maximum_drawdown: null, number_of_trades: null },
];

test("dashboard asset context keeps only a compatible selected experiment", () => {
  assert.equal(experimentForAsset(experiments, "AAPL", "EXP-000001")?.experiment_id, "EXP-000002");
  assert.equal(experimentForAsset(experiments, "AAPL", "EXP-000002")?.experiment_id, "EXP-000002");
});

test("dashboard asset context stays on the dashboard and preserves other filters", () => {
  const path = dashboardContextUrl("from=2024-01-01&experiment=EXP-000001", "AAPL", "EXP-000002");
  const query = new URL(path, "http://localhost").searchParams;
  assert.equal(new URL(path, "http://localhost").pathname, "/");
  assert.equal(query.get("asset"), "AAPL");
  assert.equal(query.get("experiment"), "EXP-000002");
  assert.equal(query.get("from"), "2024-01-01");
});
