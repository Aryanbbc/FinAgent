"use client";

import { useCallback, useEffect, useState } from "react";
import { MarketChart } from "@/components/market-chart";
import { RegimeStrip } from "@/components/terminal-charts";
import type { LiveBar, LiveEvent, LiveFeedState, LiveSignal, LiveSnapshot } from "@/lib/api";
import { api } from "@/lib/api";
import { dateTime, label, percent } from "@/lib/format";
import { liveActionTone, liveRegimeHistory, liveStatusLabel, liveStatusTone } from "@/lib/live";

type Props = {
  initialSymbols: { symbol: string; provider: string; interval: string }[];
  initialState: LiveFeedState | null;
  initialSnapshot: LiveSnapshot | null;
  initialHistory: LiveBar[];
  initialSignals: LiveSignal[];
  initialEvents: LiveEvent[];
  pollSeconds: number;
  error: string | null;
};

export function LiveWorkspace({ initialSymbols, initialState, initialSnapshot, initialHistory, initialSignals, initialEvents, pollSeconds, error: initialError }: Props) {
  const [symbol, setSymbol] = useState(initialSnapshot?.symbol ?? initialState?.symbol ?? initialSymbols[0]?.symbol ?? "AAPL");
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(initialSnapshot);
  const [signals, setSignals] = useState<LiveSignal[]>(initialSignals);
  const [events, setEvents] = useState<LiveEvent[]>(initialEvents);
  const [error, setError] = useState<string | null>(initialError);
  const [refreshing, setRefreshing] = useState(false);
  const enabled = snapshot?.enabled ?? initialState?.enabled ?? false;

  // Retain the bounded API history separately so the current candle can update
  // without the chart constructing a browser-side provider connection.
  const [history, setHistory] = useState<LiveBar[]>(initialHistory);
  const refreshWithHistory = useCallback(async () => {
    if (!enabled) return;
    setRefreshing(true);
    try {
      const [nextSnapshot, nextHistory, nextSignals, nextEvents] = await Promise.all([
        api.liveSnapshot(symbol), api.liveHistory(symbol), api.liveSignals(symbol), api.liveEvents(symbol),
      ]);
      setSnapshot(nextSnapshot); setHistory(nextHistory.items); setSignals(nextSignals.items); setEvents(nextEvents.items); setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Live market intelligence is unavailable.");
    } finally { setRefreshing(false); }
  }, [enabled, symbol]);

  useEffect(() => {
    void refreshWithHistory();
    if (!enabled) return undefined;
    const timer = window.setInterval(() => { void refreshWithHistory(); }, Math.max(15, pollSeconds) * 1000);
    return () => window.clearInterval(timer);
  }, [refreshWithHistory, enabled, pollSeconds]);

  const feed = snapshot ?? initialState;
  if (!feed?.enabled) return <section className="terminal-panel live-disabled"><span className="terminal-overline">Live market intelligence</span><h1>Live monitoring is disabled</h1><p>Set <code>LIVE_MARKET_ENABLED=true</code> on the backend to enable bounded recent-market polling. This feature produces research signals only and never submits an order.</p><p className="subtle">{feed?.message ?? "The historical research workspace remains unchanged and available."}</p></section>;
  const latest = snapshot?.latest;
  const decision = snapshot?.latest_signal;
  const regimeHistory = liveRegimeHistory(signals);
  return <div className="live-workspace">
    <header className="terminal-page-head live-page-head"><div><p className="eyebrow">Live market intelligence</p><h1>Live research terminal</h1><p className="subtle">Live market intelligence only — no order execution.</p></div><div className={`live-feed-status ${liveStatusTone(feed.status)}`}><strong>{feed.status}</strong><span>{liveStatusLabel(feed.status)}</span></div></header>

    <section className="live-control-strip">
      <label>Symbol<select aria-label="Live symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)}>{initialSymbols.map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol}</option>)}</select></label>
      <LiveMetric label="Provider" value={feed.provider}/><LiveMetric label="Feed" value={feed.feed_mode}/><LiveMetric label="Interval" value={feed.interval}/><LiveMetric label="Last update" value={dateTime(feed.last_successful_update)}/><LiveMetric label="Buffered" value={`${feed.bars_buffered} bars`}/>
      <button onClick={() => void refreshWithHistory()} disabled={refreshing}>{refreshing ? "Updating…" : "Refresh"}</button>
    </section>
    {error && <section className="request-state error"><span>Live update unavailable</span><p>{error}</p><button onClick={() => void refreshWithHistory()}>Retry update</button></section>}
    {feed.message && feed.status !== "LIVE" && <section className={`live-feed-message ${liveStatusTone(feed.status)}`}>{feed.message}</section>}

    <div className="terminal-stage live-stage">
      <section className="terminal-panel market-primary"><div className="terminal-panel-head"><div><span className="terminal-overline">Recent Twelve Data OHLCV · bounded polling</span><h2>{symbol} <span>{latest ? `$${latest.close.toFixed(2)}` : "Awaiting feed"}</span></h2></div><div className="terminal-meta"><span>{latest?.timestamp ? dateTime(latest.timestamp) : "—"}</span><span>{signals.length} persisted signals</span></div></div>
        <MarketChart rows={history} signals={signals} live strategy={decision?.strategy.selected_strategy ?? "research"}/>
        <div className="regime-rail"><div><span className="terminal-overline">Live causal regime strip</span><strong>{label(snapshot?.current_regime?.regime ?? "unavailable")}</strong></div><RegimeStrip items={regimeHistory}/></div>
      </section>
      <aside className="terminal-right-rail"><section className="rail-section agent-terminal"><div className="terminal-panel-head"><div><span className="terminal-overline">Latest structured research state</span><h2>Agent terminal</h2></div></div>
        <LiveAgentRow label="Technical" state={label(String(decision?.technical.trend ?? "unavailable"))} detail={`momentum ${label(String(decision?.technical.momentum ?? "—"))} · volatility ${label(String(decision?.technical.volatility ?? "—"))} · RSI ${label(String(decision?.technical.rsi ?? "—"))}`} confidence={Number(decision?.technical.confidence)}/>
        <LiveAgentRow label="Regime" state={label(snapshot?.current_regime?.regime ?? "unavailable")} detail="Rule-based causal detector" confidence={snapshot?.current_regime?.confidence}/>
        <LiveAgentRow label="Strategy" state={decision ? `${decision.strategy.selected_strategy} · ${decision.action}` : "unavailable"} detail={decision?.reason_codes.join(" · ") ?? "No signal yet"} confidence={decision?.confidence}/>
        <LiveAgentRow label="Risk" state={decision ? (decision.risk.approved ? "APPROVED" : "REJECTED") : "unavailable"} detail={decision?.risk.reason_code ?? "No decision yet"} confidence={undefined} tone={decision?.risk.approved ? "positive" : "negative"}/>
      </section><section className="rail-section research-snapshot"><span className="terminal-overline">Live safety boundary</span><div className="snapshot-grid"><LiveMetric label="Execution" value="DISABLED"/><LiveMetric label="Last price" value={latest ? `$${latest.close.toFixed(2)}` : "—"}/><LiveMetric label="Signal" value={decision?.action ?? "—"}/><LiveMetric label="Provider" value={feed.provider}/></div></section></aside>
    </div>

    <div className="live-bottom-grid"><section className="terminal-panel"><div className="terminal-panel-head"><div><span className="terminal-overline">Live activity</span><h2>Bounded feed events</h2></div></div><div className="live-events">{events.length ? events.map((event) => <div key={`${event.timestamp}-${event.event_type}`}><time>{dateTime(event.timestamp)}</time><strong>{event.event_type}</strong><span>{event.summary}</span></div>) : <p className="subtle">No live feed events have been recorded yet.</p>}</div></section><section className="terminal-panel"><div className="terminal-panel-head"><div><span className="terminal-overline">Recent signals</span><h2>Research signal history</h2></div></div><div className="table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Price</th><th>Regime</th><th>Risk</th></tr></thead><tbody>{signals.length ? signals.map((signal) => <tr key={signal.timestamp}><td>{dateTime(signal.timestamp)}</td><td className={liveActionTone(signal.action)}>{signal.action}</td><td>{signal.price.toFixed(2)}</td><td>{signal.regime.regime}</td><td>{signal.risk.reason_code}</td></tr>) : <tr><td colSpan={5} className="subtle">No completed live-bar signal yet.</td></tr>}</tbody></table></div></section></div>
  </div>;
}

function LiveMetric({ label: metricLabel, value }: { label: string; value: string }) { return <div className="live-metric"><span>{metricLabel}</span><strong>{value}</strong></div>; }
function LiveAgentRow({ label: rowLabel, state, detail, confidence, tone = "neutral" }: { label: string; state: string; detail: string; confidence?: number; tone?: "neutral" | "positive" | "negative" }) { return <div className={`agent-terminal-row ${tone}`}><span>{rowLabel}</span><strong>{state}</strong><em>{confidence === undefined || Number.isNaN(confidence) ? "—" : percent(confidence)}</em><small>{detail}</small></div>; }
