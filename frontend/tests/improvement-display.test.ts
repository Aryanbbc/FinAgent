import assert from "node:assert/strict";
import test from "node:test";
import type { Improvement } from "../lib/api";
import { promotionChecks, reasonExplanation } from "../lib/improvement-display";

const candidate: Improvement = {
  run_id: "CAND-0007",
  parent_version_id: "FinAgent-A0001",
  status: "REJECTED",
  reason_codes: ["EXCESSIVE_TURNOVER_REJECTED", "TRANSACTION_COSTS_ERASE_ADVANTAGE", "REJECTED"],
  parent_metrics: { sharpe_ratio: 0.5, total_return: 0.2 },
  candidate_metrics: { sharpe_ratio: 0.8, total_return: 0.1, maximum_drawdown: -0.05, turnover: 7, number_of_trades: 10 },
  window_pass_rate: 0.8,
  window_count: 13,
};

test("promotion display derives rule failures from real persisted reason codes", () => {
  const checks = promotionChecks(candidate);
  assert.equal(checks.find((item) => item.id === "turnover")?.state, "fail");
  assert.equal(checks.find((item) => item.id === "costs")?.state, "fail");
  assert.equal(checks.find((item) => item.id === "sharpe")?.state, "pass");
  assert.match(reasonExplanation("TRANSACTION_COSTS_ERASE_ADVANTAGE"), /transaction costs/i);
});
