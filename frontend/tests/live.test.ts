import assert from "node:assert/strict";
import test from "node:test";
import { liveActionTone, liveProviderHealthTone, liveRegimeHistory, liveStatusLabel, liveStatusTone } from "../lib/live";
import type { LiveSignal } from "../lib/api";

const signal = (timestamp: string, regime: string, action: LiveSignal["action"]): LiveSignal => ({
  symbol: "AAPL", timestamp, price: 101.25, provider: "twelve_data",
  technical: { trend: "bullish" },
  regime: { timestamp, regime, confidence: 0.8, features: { rolling_return: 0.01, rolling_volatility: 0.15, moving_average_slope: 0.02, momentum: 0.01, drawdown: -0.01 } },
  strategy: { selected_strategy: "momentum", action, confidence: 0.7, requested_position_size: 0.5, reason_codes: ["TREND_CONFIRMED"] },
  action, confidence: 0.7, risk: { approved: true, adjusted_position_size: 0.5, reason_code: "POSITION_ALLOWED" }, reason_codes: ["TREND_CONFIRMED", "POSITION_ALLOWED"],
});

test("live UI adapters expose explicit feed states and signal tones", () => {
  assert.equal(liveStatusLabel("RATE_LIMITED"), "Provider rate limit reached");
  assert.equal(liveStatusLabel("MARKET_CLOSED"), "U.S. equity market is closed");
  assert.equal(liveStatusTone("LIVE"), "positive");
  assert.equal(liveStatusTone("PRE_MARKET"), "notice");
  assert.equal(liveStatusTone("MARKET_CLOSED"), "notice");
  assert.equal(liveStatusTone("RECONNECTING"), "notice");
  assert.equal(liveStatusTone("OFFLINE"), "negative");
  assert.equal(liveProviderHealthTone("OK"), "positive");
  assert.equal(liveProviderHealthTone("RATE_LIMITED"), "negative");
  assert.equal(liveActionTone("BUY"), "positive");
  assert.equal(liveActionTone("EXIT"), "negative");
});

test("live UI regime adapter keeps persisted signal chronology", () => {
  const history = liveRegimeHistory([
    signal("2026-01-02T14:31:00+00:00", "bear", "HOLD"),
    signal("2026-01-02T14:30:00+00:00", "bull", "BUY"),
  ]);

  assert.deepEqual(history.map((item) => item.regime), ["bull", "bear"]);
  assert.equal(history[0].rolling_return, 0.01);
});
