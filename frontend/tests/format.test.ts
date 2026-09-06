import assert from "node:assert/strict";
import test from "node:test";
import { label, percent } from "../lib/format";

test("formats percentages and labels consistently", () => {
  assert.equal(percent(0.1234), "12.34%");
  assert.equal(percent(null), "—");
  assert.equal(label("high_volatility"), "High Volatility");
});
