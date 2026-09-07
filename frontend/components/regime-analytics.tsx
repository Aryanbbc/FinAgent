"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RegimeObservation } from "@/lib/api";
import { regimeStatistics } from "@/lib/terminal";

const tooltip = { background: "#0b1524", border: "1px solid #31415b", borderRadius: 8, color: "#e8eef8" };

export function RegimeAnalytics({ distribution, observations }: { distribution: Record<string, number>; observations: RegimeObservation[] }) {
  const distributionRows = Object.entries(distribution).map(([regime, count]) => ({ regime: regime.replaceAll("_", " "), count }));
  const stats = regimeStatistics(observations).map((item) => ({ ...item, regime: item.regime.replaceAll("_", " "), averageReturn: item.averageReturn * 100 }));
  return <div className="regime-analytics"><section><h3>Distribution</h3><ResponsiveContainer width="100%" height={230}><BarChart data={distributionRows}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="regime" stroke="#8090a8" tick={{ fontSize: 11 }}/><YAxis stroke="#8090a8"/><Tooltip contentStyle={tooltip}/><Bar dataKey="count" name="Observations" fill="#efc66b" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer></section><section><h3>Feature return / Sharpe by regime</h3><ResponsiveContainer width="100%" height={230}><BarChart data={stats}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="regime" stroke="#8090a8" tick={{ fontSize: 11 }}/><YAxis yAxisId="return" stroke="#8090a8" tickFormatter={(value) => `${value}%`}/><YAxis yAxisId="sharpe" orientation="right" stroke="#8090a8"/><Tooltip contentStyle={tooltip}/><Legend/><Bar yAxisId="return" dataKey="averageReturn" name="Average rolling return (%)" fill="#58d6aa" radius={[4,4,0,0]}/><Bar yAxisId="sharpe" dataKey="sharpe" name="Feature Sharpe" fill="#91a5ff" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer></section></div>;
}
