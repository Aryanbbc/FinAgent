"use client";

import { Bar, BarChart, Brush, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CurvePoint, RegimeObservation } from "@/lib/api";
import { drawdownSeries } from "@/lib/terminal";

const tooltip = { background: "#0b1524", border: "1px solid #31415b", borderRadius: 8, color: "#e8eef8" };
type Range = { startIndex?: number; endIndex?: number };
type ChartRangeProps = { range: Range; onRangeChange: (range: Range) => void };

export function TerminalEquityChart({ equity, benchmark, range, onRangeChange }: { equity: CurvePoint[]; benchmark: CurvePoint[] } & ChartRangeProps) {
  const values = equity.map((point, index) => ({ timestamp: point.timestamp.slice(0, 10), FinAgent: point.equity, "Buy-and-Hold": benchmark[index]?.benchmark_equity }));
  return <ResponsiveContainer width="100%" height={300}><LineChart data={values} syncId="terminal-curves" margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8"/><YAxis stroke="#8090a8" width={72} tickFormatter={(value) => `$${Math.round(value / 1000)}k`}/><Tooltip contentStyle={tooltip} formatter={(value) => typeof value === "number" ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : value}/><Legend/><Line type="monotone" dataKey="FinAgent" stroke="#58d6aa" dot={false} strokeWidth={2}/><Line type="monotone" dataKey="Buy-and-Hold" stroke="#91a5ff" dot={false} strokeWidth={2}/><Brush dataKey="timestamp" height={24} stroke="#7184a4" startIndex={range.startIndex} endIndex={range.endIndex} onChange={onRangeChange}/></LineChart></ResponsiveContainer>;
}

export function TerminalDrawdownChart({ equity, range, onRangeChange }: { equity: CurvePoint[] } & ChartRangeProps) {
  const values = drawdownSeries(equity).map((point) => ({ timestamp: point.timestamp.slice(0, 10), drawdown: point.drawdown * 100 }));
  return <ResponsiveContainer width="100%" height={245}><LineChart data={values} syncId="terminal-curves" margin={{ left: 8, right: 18, top: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8"/><YAxis stroke="#8090a8" width={58} tickFormatter={(value) => `${value}%`}/><Tooltip contentStyle={tooltip} formatter={(value) => typeof value === "number" ? `${value.toFixed(2)}%` : value}/><Line type="monotone" dataKey="drawdown" stroke="#ff8490" dot={false} strokeWidth={2}/><Brush dataKey="timestamp" height={22} stroke="#7184a4" startIndex={range.startIndex} endIndex={range.endIndex} onChange={onRangeChange}/></LineChart></ResponsiveContainer>;
}

const regimeValue: Record<string, number> = { stress: 5, high_volatility: 4, bear: 3, sideways: 2, bull: 1, low_volatility: 0 };
function RegimeTooltip({ active, payload, label }: { active?: boolean; payload?: { payload?: Record<string, unknown> }[]; label?: string }) {
  const item = payload?.[0]?.payload;
  if (!active || !item) return null;
  const features = ["rolling_return", "rolling_volatility", "moving_average_slope", "momentum", "drawdown"];
  return <div className="regime-tooltip"><strong>{String(item.regime).replaceAll("_", " ")}</strong><span>{label} · {(Number(item.confidence) * 100).toFixed(0)}% confidence</span>{features.map((key) => <small key={key}>{key.replaceAll("_", " ")}: {item[key] === null || item[key] === undefined ? "—" : Number(item[key]).toFixed(4)}</small>)}</div>;
}
export function RegimeStrip({ items }: { items: RegimeObservation[] }) {
  const values = items.map((item) => ({ timestamp: item.timestamp.slice(0, 10), regime: item.regime, confidence: item.confidence, value: regimeValue[item.regime] ?? 2, rolling_return: item.rolling_return, rolling_volatility: item.rolling_volatility, moving_average_slope: item.moving_average_slope, momentum: item.momentum, drawdown: item.drawdown }));
  return <ResponsiveContainer width="100%" height={155}><BarChart data={values} margin={{ left: 8, right: 18, top: 8 }}><XAxis dataKey="timestamp" minTickGap={42} stroke="#8090a8"/><YAxis hide domain={[0, 5]}/><Tooltip content={<RegimeTooltip/>}/><Bar dataKey="value" name="Regime" fill="#efc66b" radius={[2, 2, 0, 0]}/></BarChart></ResponsiveContainer>;
}
