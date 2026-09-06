"use client";

import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { OhlcvRow } from "@/lib/api";

export function DatasetCharts({ rows }: { rows: OhlcvRow[] }) {
  const data = rows.map(row => ({ ...row, timestamp: row.timestamp.slice(0, 10) }));
  return <div className="chart"><ResponsiveContainer width="100%" height={300}><ComposedChart data={data}><CartesianGrid strokeDasharray="3 3" stroke="#263348"/><XAxis dataKey="timestamp" minTickGap={38} stroke="#8090a8"/><YAxis yAxisId="price" stroke="#8090a8"/><YAxis yAxisId="volume" orientation="right" stroke="#8090a8"/><Tooltip contentStyle={{ background: "#111b2a", border: "1px solid #31415b", borderRadius: 8 }}/><Bar yAxisId="volume" dataKey="volume" fill="#7d95ff66" name="Volume"/><Line yAxisId="price" type="monotone" dataKey="close" stroke="#58d6aa" dot={false} strokeWidth={2} name="Close"/></ComposedChart></ResponsiveContainer></div>;
}
