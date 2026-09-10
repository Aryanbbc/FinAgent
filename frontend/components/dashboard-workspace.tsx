"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ActivityLog } from "@/components/activity-log";
import { DrawdownChart, EquityChart } from "@/components/financial-charts";
import { MarketChart } from "@/components/market-chart";
import { RegimeStrip } from "@/components/terminal-charts";
import type { AgentDecision, Critique, Experiment, ExperimentSummary, Improvement, OhlcvSeries, RegimeObservation, System, Trade, ValidationSummary } from "@/lib/api";
import { currency, dateTime, label, percent } from "@/lib/format";

type Props = {
  latest: ExperimentSummary;
  experiment: Experiment;
  market: OhlcvSeries | null;
  regimes: RegimeObservation[];
  trades: Trade[];
  decisions: AgentDecision[];
  critique: Critique | null;
  system: System | null;
  promotion?: Improvement;
  validation?: ValidationSummary;
};

function terminalTone(value: number | null | undefined) { return (value ?? 0) >= 0 ? "positive" : "negative"; }

export function DashboardWorkspace({ latest, experiment, market, regimes, trades, decisions, critique, system, promotion, validation }: Props) {
  const [highlightTimestamp, setHighlightTimestamp] = useState<string | null>(null);
  const decision = decisions.at(-1) ?? experiment.agents.latest;
  const costs = useMemo(() => trades.reduce((sum, item) => sum + item.transaction_cost, 0), [trades]);
  const metrics = [
    ["Total return", percent(latest.total_return), terminalTone(latest.total_return)],
    ["Annualized", percent(experiment.metrics.annualized_return), terminalTone(experiment.metrics.annualized_return)],
    ["Sharpe", latest.sharpe_ratio?.toFixed(2) ?? "—", "neutral"],
    ["Sortino", experiment.metrics.sortino_ratio?.toFixed(2) ?? "—", "neutral"],
    ["Max drawdown", percent(latest.maximum_drawdown), "negative"],
    ["Volatility", percent(experiment.metrics.annualized_volatility), "neutral"],
    ["Turnover", experiment.metrics.turnover?.toFixed(2) ?? "—", "neutral"],
    ["Robustness", validation?.robustness_score.toFixed(3) ?? "—", "neutral"],
  ];

  return <div className="terminal-dashboard">
    <section className="terminal-kpi-strip" aria-label="Latest experiment key performance indicators">
      {metrics.map(([name, value, tone]) => <div className={`terminal-kpi ${tone}`} key={name}><span>{name}</span><strong>{value}</strong></div>)}
    </section>

    <div className="terminal-stage">
      <section className="terminal-panel market-primary">
        <div className="terminal-panel-head"><div><span className="terminal-overline">Market replay · persisted historical OHLCV</span><h2>{latest.asset} <span>{latest.strategy}</span></h2></div><div className="terminal-meta"><span>{latest.experiment_id}</span><span>{trades.length} simulated trades</span><span>{dateTime(latest.created_at)}</span></div></div>
        <MarketChart rows={market?.items ?? []} trades={trades} decisions={decisions} experimentId={latest.experiment_id} strategy={latest.strategy} highlightTimestamp={highlightTimestamp}/>
        <div className="regime-rail"><div><span className="terminal-overline">Causal regime strip</span><strong>{label(regimes.at(-1)?.regime ?? "unavailable")}</strong></div><RegimeStrip items={regimes}/></div>
      </section>

      <aside className="terminal-right-rail">
        <section className="rail-section agent-terminal"><div className="terminal-panel-head"><div><span className="terminal-overline">Latest decision stack</span><h2>Agent terminal</h2></div><Link href="/agents" className="terminal-link">Open</Link></div>
          <AgentRow label="Technical" state={label(String(decision?.technical.trend ?? "unavailable"))} confidence={Number(decision?.technical.confidence)} detail={`mom ${label(String(decision?.technical.momentum ?? "—"))} · vol ${label(String(decision?.technical.volatility ?? "—"))} · RSI ${label(String(decision?.technical.rsi ?? "—"))}`}/>
          <AgentRow label="Regime" state={label(decision?.regime.regime ?? regimes.at(-1)?.regime ?? "unavailable")} confidence={decision?.regime.confidence ?? regimes.at(-1)?.confidence} detail="rule-based causal detector"/>
          <AgentRow label="Strategy" state={`${decision?.proposal.selected_strategy ?? latest.strategy} · ${label(decision?.proposal.action ?? "—")}`} confidence={decision?.proposal.confidence} detail={decision?.proposal.reason_codes.join(" · ") ?? "No persisted proposal"}/>
          <AgentRow label="Risk" state={decision ? (decision.risk.approved ? "APPROVED" : "REJECTED") : "UNAVAILABLE"} confidence={undefined} detail={decision ? `${percent(decision.risk.adjusted_position_size)} · ${decision.risk.reason_code}` : "No persisted risk decision"} tone={decision?.risk.approved ? "positive" : "negative"}/>
        </section>
        <section className="rail-section research-snapshot"><span className="terminal-overline">Research state</span><div className="snapshot-grid"><Snapshot label="Current regime" value={label(regimes.at(-1)?.regime ?? "unavailable")} /><Snapshot label="Risk decision" value={decision?.risk.approved ? "Approved" : decision ? "Rejected" : "—"} tone={decision?.risk.approved ? "positive" : "negative"}/><Snapshot label="Critic" value={critique ? `${percent(critique.confidence)} confidence` : "No critique"}/><Snapshot label="Costs" value={currency(costs)} /><Snapshot label="Candidate" value={promotion?.status ?? "None"} tone={promotion?.status === "PROMOTED" ? "positive" : "neutral"}/><Snapshot label="Database" value={`${system?.database_backend ?? "—"} · ${system?.database_status ?? "—"}`} /></div></section>
      </aside>
    </div>

    <div className="terminal-analytics-grid">
      <section className="terminal-panel"><div className="terminal-panel-head"><div><span className="terminal-overline">Portfolio performance</span><h2>Equity vs benchmark</h2></div><span className="terminal-meta">same starting capital</span></div><EquityChart equity={experiment.equity_curve} benchmark={experiment.benchmark_curve}/></section>
      <section className="terminal-panel"><div className="terminal-panel-head"><div><span className="terminal-overline">Risk trace</span><h2>Drawdown</h2></div><span className="terminal-meta">peak-to-trough</span></div><DrawdownChart equity={experiment.equity_curve}/></section>
    </div>

    <ActivityLog compact experimentId={latest.experiment_id} onHighlight={setHighlightTimestamp}/>

    <div className="terminal-summary-grid">
      <section className="terminal-panel"><span className="terminal-overline">Experiment summary</span><div className="summary-line"><Link href={`/experiments/${latest.experiment_id}`}>{latest.experiment_id}</Link><span>{latest.strategy} · {latest.asset}</span><span>{experiment.start_date} → {experiment.end_date}</span></div><p className="subtle">Historical simulation only. Chart markers and agent records are persisted research evidence, not executable orders.</p></section>
      <section className="terminal-panel"><span className="terminal-overline">Latest critique</span><div className="summary-line"><strong>{critique?.reason_codes[0] ?? "No deterministic critique"}</strong><span>{critique?.strengths[0]?.summary ?? "Run a completed experiment to generate post-experiment evidence."}</span></div></section>
      <section className="terminal-panel"><span className="terminal-overline">Validation status</span><div className="summary-line"><strong>{validation ? `${validation.robustness_score.toFixed(3)} robustness` : "Not validated"}</strong><span>{validation ? `${validation.window_count} walk-forward windows · ${validation.asset_count} assets` : "No persisted validation record"}</span></div></section>
    </div>
  </div>;
}

function AgentRow({ label: rowLabel, state, confidence, detail, tone = "neutral" }: { label: string; state: string; confidence?: number; detail: string; tone?: "neutral" | "positive" | "negative" }) {
  return <div className={`agent-terminal-row ${tone}`}><span>{rowLabel}</span><strong>{state}</strong>{confidence !== undefined && !Number.isNaN(confidence) ? <em>{percent(confidence)}</em> : <em>—</em>}<small>{detail}</small></div>;
}

function Snapshot({ label: itemLabel, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "positive" | "negative" }) {
  return <div className={tone}><span>{itemLabel}</span><strong>{value}</strong></div>;
}
