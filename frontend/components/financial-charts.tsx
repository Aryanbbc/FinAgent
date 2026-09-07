"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CurvePoint, RegimeObservation } from "@/lib/api";

const tooltip = { background: "#101c2d", border: "1px solid #31415b", borderRadius: 8, color: "#e8eef8" };

export function EquityChart({ equity, benchmark }: { equity: CurvePoint[]; benchmark: CurvePoint[] }) {
  const values = equity.map((point, index) => ({ timestamp: point.timestamp.slice(0, 10), equity: point.equity, benchmark: benchmark[index]?.benchmark_equity }));
  return <div className="chart"><ResponsiveContainer width="100%" height={300}><LineChart data={values} margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8" /><YAxis stroke="#8090a8" width={70} tickFormatter={(value) => `$${Math.round(value / 1000)}k`} label={{ value: "Portfolio value", angle: -90, position: "insideLeft", fill: "#91a0b8", fontSize: 11 }} /><Tooltip contentStyle={tooltip} formatter={(value) => typeof value === "number" ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : value} /><Legend /><Line type="monotone" dataKey="equity" name="Strategy equity" stroke="#58d6aa" dot={false} strokeWidth={2} /><Line type="monotone" dataKey="benchmark" name="Buy & hold benchmark" stroke="#91a5ff" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer></div>;
}

export function DrawdownChart({ equity }: { equity: CurvePoint[] }) {
  let peak = 0;
  const values = equity.map((point) => { peak = Math.max(peak, point.equity ?? 0); return { timestamp: point.timestamp.slice(0, 10), drawdown: peak ? ((point.equity ?? peak) / peak - 1) * 100 : 0 }; });
  return <div className="chart"><ResponsiveContainer width="100%" height={230}><AreaChart data={values} margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8" /><YAxis stroke="#8090a8" width={58} tickFormatter={(value) => `${value}%`} label={{ value: "Drawdown", angle: -90, position: "insideLeft", fill: "#91a0b8", fontSize: 11 }} /><Tooltip contentStyle={tooltip} formatter={(value) => typeof value === "number" ? `${value.toFixed(2)}%` : value} /><Area type="monotone" dataKey="drawdown" stroke="#ff7e88" fill="#ff7e8844" name="Drawdown" /></AreaChart></ResponsiveContainer></div>;
}

const regimeValue: Record<string, number> = { stress: 3, high_volatility: 2, bear: 1, sideways: 0, bull: -1, low_volatility: -2 };

export function RegimeTimeline({ observations }: { observations: RegimeObservation[] }) {
  const values = observations.map((item) => ({ timestamp: item.timestamp.slice(0, 10), value: regimeValue[item.regime] ?? 0, regime: item.regime, confidence: item.confidence }));
  return <div className="chart"><ResponsiveContainer width="100%" height={230}><LineChart data={values} margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8" /><YAxis stroke="#8090a8" ticks={[-2,-1,0,1,2,3]} tickFormatter={(value) => ({ "-2": "Low vol", "-1": "Bull", "0": "Sideways", "1": "Bear", "2": "High vol", "3": "Stress" }[String(value)] ?? "")} width={70} /><Tooltip contentStyle={tooltip} formatter={(_value, _name, item) => [String(item.payload.regime).replaceAll("_", " "), "Regime"]} labelFormatter={(value) => `Date: ${value}`} /><Line type="stepAfter" dataKey="value" stroke="#efc66b" dot={false} strokeWidth={2} name="Regime" /></LineChart></ResponsiveContainer></div>;
}

export function SensitivityChart({ items }: { items: Record<string, unknown>[] }) {
  const values = items.slice(0, 20).map((item, index) => ({ label: `${String(item.parameter ?? "parameter")}: ${String(item.value ?? index + 1)}`, stability: Number(item.stability_score ?? 0) }));
  return <div className="chart"><ResponsiveContainer width="100%" height={240}><BarChart data={values} layout="vertical" margin={{ left: 30, right: 18 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis type="number" domain={[0, 1]} stroke="#8090a8" tickFormatter={(value) => Number(value).toFixed(1)} /><YAxis type="category" dataKey="label" width={115} stroke="#8090a8" tick={{ fontSize: 10 }} /><Tooltip contentStyle={tooltip} formatter={(value) => typeof value === "number" ? value.toFixed(3) : value} /><Bar dataKey="stability" name="Stability score" fill="#91a5ff" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></div>;
}

export function CandidateEvolutionChart({ items }: { items: { run_id: string; candidate_metrics: Record<string, number | null>; status: string; window_pass_rate: number }[] }) {
  const values = items.slice().reverse().map((item) => ({ candidate: item.run_id, sharpe: item.candidate_metrics.sharpe_ratio ?? 0, return: (item.candidate_metrics.total_return ?? 0) * 100, drawdown: (item.candidate_metrics.maximum_drawdown ?? 0) * 100, passRate: item.window_pass_rate * 100, status: item.status }));
  return <div className="chart"><ResponsiveContainer width="100%" height={260}><BarChart data={values} margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="candidate" stroke="#8090a8" tick={{ fontSize: 10 }} /><YAxis stroke="#8090a8" label={{ value: "Historical metric", angle: -90, position: "insideLeft", fill: "#91a0b8", fontSize: 11 }} /><Tooltip contentStyle={tooltip} /><Legend /><Bar dataKey="sharpe" name="OOS Sharpe" fill="#58d6aa" radius={[4, 4, 0, 0]} /><Bar dataKey="return" name="Return (%)" fill="#91a5ff" radius={[4, 4, 0, 0]} /><Bar dataKey="drawdown" name="Drawdown (%)" fill="#ff8490" radius={[4, 4, 0, 0]} /><Bar dataKey="passRate" name="Window pass rate (%)" fill="#efc66b" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer><p className="chart-caption">Window pass rate is shown as validation evidence; no separate candidate robustness score is stored.</p></div>;
}

export function MultiAssetChart({ items }: { items: Record<string, unknown>[] }) {
  const values = items.map((item) => ({ asset: String(item.asset ?? "Asset"), totalReturn: Number((item.metrics as Record<string, number> | undefined)?.total_return ?? 0) * 100 }));
  return <div className="chart"><ResponsiveContainer width="100%" height={240}><BarChart data={values} margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="asset" stroke="#8090a8" /><YAxis stroke="#8090a8" tickFormatter={(value) => `${value}%`} label={{ value: "Historical return", angle: -90, position: "insideLeft", fill: "#91a0b8", fontSize: 11 }} /><Tooltip contentStyle={tooltip} formatter={(value) => typeof value === "number" ? `${value.toFixed(2)}%` : value} /><Bar dataKey="totalReturn" name="Total return" fill="#58d6aa" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>;
}

export function WalkForwardChart({ items }: { items: Record<string, unknown>[] }) {
  const values = items.map((item, index) => ({ window: `${String(item.asset ?? "Asset")} ${index + 1}`, totalReturn: Number((item.metrics as Record<string, number> | undefined)?.total_return ?? 0) * 100 }));
  return <div className="chart"><ResponsiveContainer width="100%" height={240}><BarChart data={values} margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="window" stroke="#8090a8" tick={{ fontSize: 10 }} /><YAxis stroke="#8090a8" tickFormatter={(value) => `${value}%`} label={{ value: "Held-out return", angle: -90, position: "insideLeft", fill: "#91a0b8", fontSize: 11 }} /><Tooltip contentStyle={tooltip} formatter={(value) => typeof value === "number" ? `${value.toFixed(2)}%` : value} /><Bar dataKey="totalReturn" name="Walk-forward return" fill="#efc66b" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>;
}
