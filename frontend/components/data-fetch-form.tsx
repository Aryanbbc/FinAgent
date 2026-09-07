"use client";

import { FormEvent, useState } from "react";
import { api, ApiError, DataFetchInput, DataProvider } from "@/lib/api";

export function DataFetchForm({ providers }: { providers: DataProvider[] }) {
  const [provider, setProvider] = useState(providers.some((item) => item.provider === "auto") ? "auto" : (providers[0]?.provider ?? "yahoo_finance"));
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [lastInput, setLastInput] = useState<DataFetchInput | null>(null);

  async function fetchDataset(input: DataFetchInput) {
    setStatus("loading"); setMessage(""); setLastInput(input);
    try {
      const result = await api.fetchData(input);
      const source = result.fallback_used
        ? `${result.requested_provider} → ${result.actual_provider} fallback`
        : result.actual_provider;
      setStatus("success");
      setMessage(`${result.dataset.dataset_id} · ${result.dataset.row_count} rows · quality ${result.dataset.quality_score.toFixed(3)} · source ${source}${result.cache_hit ? " (cache hit)" : ""}`);
    } catch (error) {
      setStatus("error");
      if (error instanceof ApiError && error.code === "RATE_LIMIT") {
        setMessage("Yahoo Finance is rate-limiting this request. Retry shortly, or select Auto to allow the Stooq historical-data fallback.");
      } else if (error instanceof ApiError && error.code === "ALL_PROVIDERS_FAILED") {
        setMessage("Yahoo Finance and the fallback provider are temporarily unavailable. No dataset was created; please retry shortly.");
      } else {
        setMessage(error instanceof Error ? error.message : "Unable to fetch historical data.");
      }
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const start = String(values.get("start")); const end = String(values.get("end"));
    if (start > end) { setStatus("error"); setMessage("The end date must be on or after the start date."); return; }
    await fetchDataset({ provider, symbol: String(values.get("symbol")).trim().toUpperCase(), start_date: start, end_date: end, interval: "1d", force_refresh: values.get("refresh") === "on", source_path: values.get("source_path") ? String(values.get("source_path")) : undefined, missing_data_policy: "reject" });
  }
  return <section className="panel"><h2>Fetch historical data</h2><p className="subtle">Daily research data only. Auto tries Yahoo Finance first and uses Stooq only after a retryable provider failure; the saved dataset records the actual source.</p><form className="filters" onSubmit={submit}><select aria-label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)}>{providers.map(item => <option key={item.provider} value={item.provider}>{item.provider === "auto" ? "Auto (Yahoo Finance → Stooq)" : item.provider}</option>)}</select><input name="symbol" placeholder="Symbol search (e.g. AAPL)" required/><input name="start" type="date" required/><input name="end" type="date" required/><input name="source_path" placeholder="CSV path for local_csv"/><label className="pill"><input name="refresh" type="checkbox"/> Force refresh</label><button disabled={status === "loading"}>{status === "loading" ? "Fetching historical data…" : "Fetch dataset"}</button></form>{status === "loading" && <div className="skeleton-list compact"><i/><i/></div>}{status !== "idle" && status !== "loading" && <div className={`request-state ${status}`}><span>{status === "success" ? "Dataset ready" : "Fetch unavailable"}</span><p>{message}</p>{status === "error" && <button type="button" disabled={!lastInput} onClick={() => lastInput && fetchDataset(lastInput)}>Retry fetch</button>}</div>}</section>;
}
