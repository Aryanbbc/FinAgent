import Link from "next/link";
import { DataState } from "@/components/data-state";
import { DrawdownChart, EquityChart, RegimeTimeline } from "@/components/financial-charts";
import { MetricCard } from "@/components/metric-card";
import { api } from "@/lib/api";
import { load } from "@/lib/load";
import { label, percent } from "@/lib/format";

export default async function Dashboard() {
  const [experiments, system, improvements, validations] = await Promise.all([
    load(api.experiments("?limit=1")), load(api.system()), load(api.improvements()), load(api.validations()),
  ]);
  const latest = experiments.data?.items[0];
  const detail = latest ? await load(api.experiment(latest.experiment_id)) : { data: null, error: null };
  const regimes = latest ? await load(api.regimes(latest.experiment_id)) : { data: null, error: null };
  const promotion = improvements.data?.items[0];
  const validation = validations.data?.items[0];

  return <>
    <header className="page-head">
      <div><p className="eyebrow">Research Command Center</p><h1>Dashboard</h1><p className="subtle">Local historical results, data health, decision records, and validation evidence. Nothing here executes trades.</p></div>
      {latest && <Link className="pill" href={`/experiments/${latest.experiment_id}`}>Open latest experiment</Link>}
    </header>
    <DataState error={experiments.error ?? detail.error ?? system.error ?? regimes.error} empty={!latest}>
      {latest && detail.data && <>
        <div className="metric-grid">
          <MetricCard label="Total return" value={percent(latest.total_return)} tone={(latest.total_return ?? 0) >= 0 ? "positive" : "negative"}/>
          <MetricCard label="Sharpe ratio" value={latest.sharpe_ratio?.toFixed(2) ?? "—"}/>
          <MetricCard label="Sortino ratio" value={detail.data.metrics.sortino_ratio?.toFixed(2) ?? "—"}/>
          <MetricCard label="Maximum drawdown" value={percent(latest.maximum_drawdown)} tone="negative"/>
          <MetricCard label="Volatility" value={percent(detail.data.metrics.annualized_volatility)}/>
          <MetricCard label="Turnover" value={detail.data.metrics.turnover?.toFixed(2) ?? "—"}/>
          <MetricCard label="Registered datasets" value={String(system.data?.dataset_count ?? 0)}/>
          <MetricCard label="Data-quality warnings" value={String(system.data?.data_quality_warnings ?? 0)} tone={(system.data?.data_quality_warnings ?? 0) ? "negative" : "positive"}/>
        </div>
        <div className="split">
          <section className="panel"><h2>Equity vs benchmark</h2><EquityChart equity={detail.data.equity_curve} benchmark={detail.data.benchmark_curve}/></section>
          <section className="panel"><h2>Latest research state</h2><ul className="list">
            <li><strong>{label(detail.data.regime.latest?.regime ?? "unavailable")}</strong><br/><small>Current causal market regime</small></li>
            <li><strong>{detail.data.agents.latest?.proposal.selected_strategy ?? latest.strategy} / {detail.data.agents.latest?.execution_action ?? "—"}</strong><br/><small>Latest agent strategy and execution action</small></li>
            <li><strong className={promotion?.status === "PROMOTED" ? "good" : "bad"}>{promotion?.status ?? "No candidate"}</strong><br/><small>Latest promotion/rejection decision</small></li>
            <li><strong>{validation?.robustness_score.toFixed(3) ?? "—"}</strong><br/><small>Latest robustness score · API {system.data ? "healthy" : "unavailable"}</small></li>
          </ul></section>
        </div>
        <div className="split">
          <section className="panel"><h2>Drawdown curve</h2><DrawdownChart equity={detail.data.equity_curve}/></section>
          <section className="panel"><h2>Regime timeline</h2>{regimes.data ? <RegimeTimeline observations={regimes.data.items}/> : <p className="subtle">No regime observations recorded.</p>}</section>
        </div>
      </>}
    </DataState>
  </>;
}
