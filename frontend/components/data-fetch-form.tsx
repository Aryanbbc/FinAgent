"use client";

import { FormEvent, useState } from "react";
import { api, DataProvider, DatasetSummary } from "@/lib/api";

export function DataFetchForm({ providers }: { providers: DataProvider[] }) {
  const [provider, setProvider] = useState(providers[0]?.provider ?? "yahoo_finance");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setStatus("loading"); setMessage("");
    const values = new FormData(event.currentTarget);
    try {
      const result = await api.fetchData({ provider, symbol: String(values.get("symbol")), start_date: String(values.get("start")), end_date: String(values.get("end")), interval: "1d", force_refresh: values.get("refresh") === "on", source_path: values.get("source_path") ? String(values.get("source_path")) : undefined, missing_data_policy: "reject" });
      setStatus("success"); setMessage(`${result.dataset.dataset_id} · ${result.dataset.row_count} rows · quality ${result.dataset.quality_score.toFixed(3)}${result.cache_hit ? " (cache hit)" : ""}`);
    } catch (error) { setStatus("error"); setMessage(error instanceof Error ? error.message : "Unable to fetch historical data."); }
  }
  return <section className="panel"><h2>Fetch historical data</h2><p className="subtle">Daily research data only. Yahoo Finance is public and may impose availability/rate limits.</p><form className="filters" onSubmit={submit}><select aria-label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)}>{providers.map(item => <option key={item.provider} value={item.provider}>{item.provider}</option>)}</select><input name="symbol" placeholder="Symbol (e.g. AAPL)" required/><input name="start" type="date" required/><input name="end" type="date" required/><input name="source_path" placeholder="CSV path for local_csv"/><label className="pill"><input name="refresh" type="checkbox"/> Force refresh</label><button disabled={status === "loading"}>{status === "loading" ? "Fetching…" : "Fetch dataset"}</button></form>{status !== "idle" && <p className={status === "error" ? "bad" : status === "success" ? "good" : "subtle"}>{message}</p>}</section>;
}
