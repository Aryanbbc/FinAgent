"use client";

import { useMemo, useState } from "react";
import type { AgentDecision, Experiment, OhlcvSeries, RegimeObservation, Trade } from "@/lib/api";
import { AgentDecisionTimeline } from "@/components/agent-decision-timeline";
import { MarketChart } from "@/components/market-chart";
import { RegimeStrip, TerminalDrawdownChart, TerminalEquityChart } from "@/components/terminal-charts";
import { dateTime, percent } from "@/lib/format";
import { drawdownDuration, drawdownSeries } from "@/lib/terminal";

type Props = { experiment: Experiment; market: OhlcvSeries | null; trades: Trade[]; regimes: RegimeObservation[]; decisions: AgentDecision[]; startDate?: string; endDate?: string };

export function ExperimentTerminal({ experiment, market, trades, regimes, decisions, startDate, endDate }: Props) {
  const [range, setRange] = useState<{ startIndex?: number; endIndex?: number }>({});
  const [selectedTimestamp, setSelectedTimestamp] = useState<string | null>(null);
  const inRange = (timestamp: string) => (!startDate || timestamp.slice(0, 10) >= startDate) && (!endDate || timestamp.slice(0, 10) <= endDate);
  const visible = useMemo(() => ({
    equity: experiment.equity_curve.filter((item) => inRange(item.timestamp)), benchmark: experiment.benchmark_curve.filter((item) => inRange(item.timestamp)),
    trades: trades.filter((item) => inRange(item.timestamp)), regimes: regimes.filter((item) => inRange(item.timestamp)), decisions: decisions.filter((item) => inRange(item.timestamp)),
  }), [experiment, trades, regimes, decisions, startDate, endDate]);
  const drawdowns = drawdownSeries(visible.equity);
  const currentDrawdown = drawdowns.at(-1)?.drawdown ?? 0;
  const longest = drawdownDuration(visible.equity);
  return <>
    <section className="panel terminal-panel"><div className="panel-title-row"><div><h2>Historical market tape</h2><p className="subtle">Persisted OHLCV with executed simulated trade markers only.</p></div>{market?.downsampled && <span className="pill">Visual sample capped at {market.items.length} bars</span>}</div><MarketChart rows={market?.items ?? []} trades={visible.trades} decisions={visible.decisions} experimentId={experiment.experiment_id} strategy={experiment.strategy} highlightTimestamp={selectedTimestamp}/></section>
    <section className="panel terminal-panel"><div className="panel-title-row"><div><h2>Regime overlay</h2><p className="subtle">Lower timeline strip; hover each bar for the causal detector’s supporting feature values.</p></div><span className="pill">{visible.regimes.length} observations</span></div><RegimeStrip items={visible.regimes}/></section>
    <div className="split terminal-split"><section className="panel"><div className="panel-title-row"><div><h2>Equity curve</h2><p className="subtle">FinAgent versus the persisted buy-and-hold benchmark. Brush to zoom the shared period.</p></div><button type="button" className="text-button" onClick={() => setRange({})}>Reset zoom</button></div><TerminalEquityChart equity={visible.equity} benchmark={visible.benchmark} range={range} onRangeChange={setRange}/></section><section className="panel"><div className="panel-title-row"><div><h2>Drawdown</h2><p className="subtle">Current {percent(currentDrawdown)} · max {percent(experiment.maximum_drawdown)} · longest {longest} bars.</p></div></div><TerminalDrawdownChart equity={visible.equity} range={range} onRangeChange={setRange}/></section></div>
    <section className="panel terminal-panel"><div className="panel-title-row"><div><h2>Agent decision timeline</h2><p className="subtle">Structured records only. Select an event to focus its historical timestamp on the market chart.</p></div>{selectedTimestamp && <span className="pill">Focused {dateTime(selectedTimestamp)}</span>}</div><AgentDecisionTimeline items={visible.decisions} onSelect={setSelectedTimestamp}/></section>
  </>;
}
