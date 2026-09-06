"use client";

import { Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CurvePoint, RegimeObservation } from "@/lib/api";

export function EquityChart({ equity, benchmark }: { equity: CurvePoint[]; benchmark: CurvePoint[] }) {
  const values = equity.map((point, index) => ({ timestamp: point.timestamp.slice(0, 10), equity: point.equity, benchmark: benchmark[index]?.benchmark_equity }));
  return <div className="chart"><ResponsiveContainer width="100%" height={300}><LineChart data={values}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8" /><YAxis stroke="#8090a8" tickFormatter={(value) => `$${Math.round(value / 1000)}k`} /><Tooltip contentStyle={{ background: "#111b2a", border: "1px solid #31415b", borderRadius: 8 }} formatter={(value) => typeof value === "number" ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : value} /><Legend /><Line type="monotone" dataKey="equity" stroke="#58d6aa" dot={false} strokeWidth={2} /><Line type="monotone" dataKey="benchmark" stroke="#7d95ff" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer></div>;
}

export function DrawdownChart({ equity }: { equity: CurvePoint[] }) {
  let peak = 0;
  const values = equity.map((point) => { peak = Math.max(peak, point.equity ?? 0); return { timestamp: point.timestamp.slice(0, 10), drawdown: peak ? ((point.equity ?? peak) / peak - 1) * 100 : 0 }; });
  return <div className="chart"><ResponsiveContainer width="100%" height={210}><AreaChart data={values}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8" /><YAxis stroke="#8090a8" tickFormatter={(value) => `${value}%`} /><Tooltip contentStyle={{ background: "#111b2a", border: "1px solid #31415b", borderRadius: 8 }} formatter={(value) => typeof value === "number" ? `${value.toFixed(2)}%` : value} /><Area type="monotone" dataKey="drawdown" stroke="#ff7e88" fill="#ff7e8844" name="Drawdown" /></AreaChart></ResponsiveContainer></div>;
}

const regimeValue: Record<string, number> = { stress: 3, high_volatility: 2, bear: 1, sideways: 0, bull: -1, low_volatility: -2 };

export function RegimeTimeline({ observations }: { observations: RegimeObservation[] }) {
  const values = observations.map((item) => ({ timestamp: item.timestamp.slice(0, 10), value: regimeValue[item.regime] ?? 0, regime: item.regime, confidence: item.confidence }));
  return <div className="chart"><ResponsiveContainer width="100%" height={210}><LineChart data={values}><CartesianGrid strokeDasharray="3 3" stroke="#263348" /><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8" /><YAxis stroke="#8090a8" ticks={[-2,-1,0,1,2,3]} tickFormatter={(value) => ({ "-2": "Low vol", "-1": "Bull", "0": "Sideways", "1": "Bear", "2": "High vol", "3": "Stress" }[String(value)] ?? "")} width={70} /><Tooltip contentStyle={{ background: "#111b2a", border: "1px solid #31415b", borderRadius: 8 }} formatter={(value, _name, item) => [String(item.payload.regime).replaceAll("_", " "), "Regime"]} labelFormatter={(value) => `Date: ${value}`} /><Line type="stepAfter" dataKey="value" stroke="#efc66b" dot={false} strokeWidth={2} name="Regime" /></LineChart></ResponsiveContainer></div>;
}
