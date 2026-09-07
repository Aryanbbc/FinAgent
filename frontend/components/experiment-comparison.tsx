"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Experiment, type ExperimentSummary } from "@/lib/api";
import { percent } from "@/lib/format";
import { comparisonRows, drawdownSeries, mergeEquityCurves } from "@/lib/terminal";

const colors = ["#58d6aa", "#91a5ff", "#efc66b", "#ff8490"];
const tooltip = { background: "#0b1524", border: "1px solid #31415b", borderRadius: 8, color: "#e8eef8" };

export function ExperimentComparison({ items }: { items: ExperimentSummary[] }) {
  const [selected, setSelected] = useState<string[]>([]); const [details, setDetails] = useState<Experiment[]>([]); const [error, setError] = useState<string | null>(null);
  useEffect(() => { let active = true; if (selected.length < 2) { setDetails([]); return; } setError(null); Promise.all(selected.map((id) => api.experiment(id))).then((result) => { if (active) setDetails(result); }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Comparison data is unavailable."); }); return () => { active = false; }; }, [selected]);
  const rows = useMemo(() => comparisonRows(details), [details]); const equity = useMemo(() => mergeEquityCurves(details), [details]);
  const drawdowns = useMemo(() => {
    const values = new Map<string, Record<string, string | number>>();
    details.forEach((item) => drawdownSeries(item.equity_curve).forEach((point) => { const date = point.timestamp.slice(0, 10); const row = values.get(date) ?? { timestamp: date }; row[item.experiment_id] = point.drawdown * 100; values.set(date, row); }));
    return [...values.values()].sort((a,b) => String(a.timestamp).localeCompare(String(b.timestamp)));
  }, [details]);
  function toggle(id: string) { setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 4 ? [...current, id] : current); }
  return <section className="panel comparison-panel"><div className="panel-title-row"><div><h2>Experiment comparison</h2><p className="subtle">Select two to four persisted simulations. Curves and metrics are read-only comparisons.</p></div><span className="pill">{selected.length}/4 selected</span></div><div className="comparison-select">{items.map((item) => <label key={item.experiment_id}><input type="checkbox" checked={selected.includes(item.experiment_id)} onChange={() => toggle(item.experiment_id)}/><span>{item.experiment_id}<small>{item.strategy} · {item.asset}</small></span></label>)}</div>{error && <p className="bad">{error}</p>}{details.length >= 2 && <><div className="table-wrap"><table><thead><tr><th>Experiment</th><th>Return</th><th>Annualized</th><th>Sharpe</th><th>Sortino</th><th>Drawdown</th><th>Volatility</th><th>Turnover</th><th>Costs</th><th>Robustness</th></tr></thead><tbody>{rows.map((item) => <tr key={item.experimentId}><td>{item.experimentId}<br/><small>{item.strategy}</small></td><td>{percent(item.totalReturn)}</td><td>{percent(item.annualizedReturn)}</td><td>{item.sharpe?.toFixed(2) ?? "—"}</td><td>{item.sortino?.toFixed(2) ?? "—"}</td><td>{percent(item.maximumDrawdown)}</td><td>{percent(item.volatility)}</td><td>{item.turnover?.toFixed(2) ?? "—"}</td><td>{item.transactionCosts?.toFixed(2) ?? "—"}</td><td>{item.robustness?.toFixed(3) ?? "—"}</td></tr>)}</tbody></table></div><div className="split"><section><h3>Equity overlay</h3><ResponsiveContainer width="100%" height={245}><LineChart data={equity}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8"/><YAxis stroke="#8090a8" width={62}/><Tooltip contentStyle={tooltip}/><Legend/>{details.map((item, index) => <Line key={item.experiment_id} type="monotone" dataKey={item.experiment_id} stroke={colors[index]} dot={false} strokeWidth={2}/>)}</LineChart></ResponsiveContainer></section><section><h3>Drawdown comparison</h3><ResponsiveContainer width="100%" height={245}><LineChart data={drawdowns}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8"/><YAxis stroke="#8090a8" width={58} tickFormatter={(value) => `${value}%`}/><Tooltip contentStyle={tooltip}/><Legend/>{details.map((item, index) => <Line key={item.experiment_id} type="monotone" dataKey={item.experiment_id} stroke={colors[index]} dot={false} strokeWidth={2}/>)}</LineChart></ResponsiveContainer></section></div></>}</section>;
}
