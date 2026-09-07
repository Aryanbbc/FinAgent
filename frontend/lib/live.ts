"use client";

import type { LiveFeedStatus, LiveProviderHealth, LiveSignal, RegimeObservation } from "@/lib/api";

export function liveStatusLabel(status: LiveFeedStatus) {
  return ({
    CONNECTING: "Connecting to bounded market feed",
    PRE_MARKET: "U.S. equity pre-market session",
    LIVE: "Recent market feed active",
    AFTER_HOURS: "U.S. equity after-hours session",
    MARKET_CLOSED: "U.S. equity market is closed",
    DELAYED: "Recent data is delayed",
    RECONNECTING: "Reconnecting with bounded backoff",
    RATE_LIMITED: "Provider rate limit reached",
    OFFLINE: "Live monitoring offline",
  } as const)[status];
}

export function liveStatusTone(status: LiveFeedStatus) {
  if (status === "LIVE") return "positive";
  if (status === "CONNECTING" || status === "RECONNECTING" || status === "DELAYED" || status === "PRE_MARKET" || status === "AFTER_HOURS" || status === "MARKET_CLOSED") return "notice";
  return "negative";
}

export function liveProviderHealthTone(health: LiveProviderHealth) {
  if (health === "OK") return "positive";
  if (health === "CONNECTING" || health === "RECONNECTING") return "notice";
  return "negative";
}

export function liveRegimeHistory(signals: LiveSignal[]): RegimeObservation[] {
  return [...signals].sort((left, right) => left.timestamp.localeCompare(right.timestamp)).map((signal) => ({
    timestamp: signal.regime.timestamp,
    regime: signal.regime.regime,
    confidence: signal.regime.confidence,
    rolling_return: signal.regime.features.rolling_return ?? null,
    rolling_volatility: signal.regime.features.rolling_volatility ?? null,
    moving_average_slope: signal.regime.features.moving_average_slope ?? null,
    momentum: signal.regime.features.momentum ?? null,
    drawdown: signal.regime.features.drawdown ?? null,
  }));
}

export function liveActionTone(action: LiveSignal["action"]) {
  return action === "BUY" ? "positive" : action === "EXIT" ? "negative" : "neutral";
}
