import assert from "node:assert/strict";
import test from "node:test";
import { currency, date, label, percent } from "../lib/format";

test("formats percentages and labels consistently", () => {
  assert.equal(percent(0.1234), "12.34%");
  assert.equal(percent(null), "—");
  assert.equal(label("high_volatility"), "High Volatility");
  assert.equal(currency(1234), "$1,234");
  assert.match(date("2024-01-02T00:00:00Z"), /Jan/);
});
