"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const tooltip = { background: "#0b1524", border: "1px solid #31415b", borderRadius: 8, color: "#e8eef8" };
type Item = Record<string, unknown>;
const metrics = ["sharpe_ratio", "maximum_drawdown", "total_return"] as const;

export function SensitivityExplorer({ items }: { items: Item[] }) {
  const parameters = [...new Set(items.map((item) => String(item.parameter)))]; const [parameter, setParameter] = useState(parameters[0] ?? ""); const [metric, setMetric] = useState<(typeof metrics)[number]>("sharpe_ratio");
  const data = useMemo(() => items.filter((item) => String(item.parameter) === parameter).map((item) => ({ value: String(item.value), metric: Number((item.metrics as Record<string, unknown> | undefined)?.[metric] ?? 0), stability: Number(item.stability_score ?? 0) })), [items, parameter, metric]);
  if (!items.length) return <p className="subtle">No sensitivity points were configured.</p>;
  return <div><div className="feed-controls"><label>Parameter<select value={parameter} onChange={(event) => setParameter(event.target.value)}>{parameters.map((item) => <option key={item}>{item}</option>)}</select></label><label>Metric<select value={metric} onChange={(event) => setMetric(event.target.value as typeof metric)}>{metrics.map((item) => <option value={item} key={item}>{item.replaceAll("_", " ")}</option>)}</select></label></div><ResponsiveContainer width="100%" height={255}><LineChart data={data}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="value" stroke="#8090a8"/><YAxis stroke="#8090a8"/><Tooltip contentStyle={tooltip}/><Legend/><Line type="monotone" dataKey="metric" name={metric.replaceAll("_", " ")} stroke="#58d6aa" strokeWidth={2}/><Line type="monotone" dataKey="stability" name="Stability score" stroke="#91a5ff" strokeWidth={2}/></LineChart></ResponsiveContainer></div>;
}

export function MultiAssetExplorer({ items }: { items: Item[] }) {
  const assets = [...new Set(items.map((item) => String(item.asset)))]; const [asset, setAsset] = useState("all"); const [metric, setMetric] = useState<(typeof metrics)[number]>("total_return");
  const values = items.filter((item) => asset === "all" || String(item.asset) === asset).map((item) => ({ asset: String(item.asset), value: Number((item.metrics as Record<string, unknown> | undefined)?.[metric] ?? 0) * (metric === "sharpe_ratio" ? 1 : 100) }));
  return <div><div className="feed-controls"><label>Asset<select value={asset} onChange={(event) => setAsset(event.target.value)}><option value="all">All assets</option>{assets.map((item) => <option key={item}>{item}</option>)}</select></label><label>Metric<select value={metric} onChange={(event) => setMetric(event.target.value as typeof metric)}>{metrics.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select></label></div><ResponsiveContainer width="100%" height={255}><BarChart data={values}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="asset" stroke="#8090a8"/><YAxis stroke="#8090a8" tickFormatter={(value) => metric === "sharpe_ratio" ? value : `${value}%`}/><Tooltip contentStyle={tooltip}/><Bar dataKey="value" name={metric.replaceAll("_", " ")} fill="#58d6aa" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer></div>;
}

export function WalkForwardMatrix({ items }: { items: Item[] }) {
  const [selected, setSelected] = useState(0); const current = items[selected];
  if (!items.length) return <p className="subtle">No walk-forward windows were persisted.</p>;
  return <div><div className="window-grid">{items.map((item, index) => <button type="button" className={selected === index ? "selected" : ""} onClick={() => setSelected(index)} key={index}><strong>{String(item.asset)} · W{String(item.window_index ?? index + 1)}</strong><span>Train {String(item.train_start).slice(0,10)} → {String(item.train_end).slice(0,10)}</span><span>Test {String(item.test_start).slice(0,10)} → {String(item.test_end).slice(0,10)}</span></button>)}</div>{current && <div className="selected-window"><strong>Selected held-out window</strong><span>Sharpe {Number((current.metrics as Record<string, number>).sharpe_ratio).toFixed(2)} · Return {(Number((current.metrics as Record<string, number>).total_return) * 100).toFixed(2)}% · Drawdown {(Number((current.metrics as Record<string, number>).maximum_drawdown) * 100).toFixed(2)}%</span></div>}</div>;
}
