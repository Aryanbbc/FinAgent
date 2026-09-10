"use client";

import { FormEvent, useState } from "react";
import { api, ApiError, DataFetchInput, DataProvider, publicMutationControlsEnabled } from "@/lib/api";

const providerLabel = (value: string) => ({
  auto: "Auto (Twelve Data → Yahoo Finance → Stooq → Local CSV)",
  twelve_data: "Twelve Data",
  yahoo_finance: "Yahoo Finance",
  stooq: "Stooq",
  local_csv: "Local CSV",
}[value] ?? value);

export function DataFetchForm({ providers }: { providers: DataProvider[] }) {
  const [provider, setProvider] = useState(providers.some((item) => item.provider === "auto") ? "auto" : (providers[0]?.provider ?? "yahoo_finance"));
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [lastInput, setLastInput] = useState<DataFetchInput | null>(null);

  async function fetchDataset(input: DataFetchInput) {
    setStatus("loading"); setMessage(""); setLastInput(input);
    try {
      const result = await api.fetchData(input);
      setStatus("success");
      setMessage(`${result.dataset.dataset_id} · ${result.dataset.row_count} rows · quality ${result.dataset.quality_score.toFixed(3)} · requested ${providerLabel(result.requested_provider)} · actual ${providerLabel(result.actual_provider)}${result.fallback_used ? " (fallback used)" : ""}${result.cache_hit ? " (cache hit)" : ""}`);
    } catch (error) {
      setStatus("error");
      if (error instanceof ApiError && error.code === "RATE_LIMIT") {
        setMessage("The selected historical-data provider is rate-limiting this request. Retry shortly, or select Auto to use the configured fallback chain.");
      } else if (error instanceof ApiError && error.code === "ALL_PROVIDERS_FAILED") {
        setMessage("All configured providers were unavailable for this request. No dataset was created; retry shortly or select a configured provider directly.");
      } else if (error instanceof ApiError && error.code === "PROVIDER_NOT_CONFIGURED") {
        setMessage("Twelve Data is not configured on the backend. Set TWELVE_DATA_API_KEY in the backend environment, or choose Auto.");
      } else {
        setMessage(error instanceof Error ? error.message : "Unable to fetch historical data.");
      }
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const start = String(values.get("start")); const end = String(values.get("end"));
    if (start >= end) { setStatus("error"); setMessage("The end date must be later than the start date."); return; }
    await fetchDataset({ provider, symbol: String(values.get("symbol")).trim().toUpperCase(), start_date: start, end_date: end, interval: "1d", force_refresh: values.get("refresh") === "on", source_path: values.get("source_path") ? String(values.get("source_path")) : undefined, missing_data_policy: "reject" });
  }
  return <section className="panel"><h2>Fetch historical data</h2><p className="subtle">Daily research data only. Auto prefers configured Twelve Data, then tries Yahoo Finance, Stooq, and a supplied local CSV after retryable failures. Every saved dataset records both requested and actual provider provenance.</p>{!publicMutationControlsEnabled ? <p className="notice">This public deployment is read-only. Dataset ingestion requires the server-side administrator API key; see the security documentation for the authenticated API workflow.</p> : <><form className="filters" onSubmit={submit}><select aria-label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)}>{providers.map(item => <option key={item.provider} value={item.provider} disabled={item.provider !== "auto" && !item.available}>{providerLabel(item.provider)}{item.requires_credentials && !item.available ? " (backend key required)" : ""}</option>)}</select><input name="symbol" placeholder="Symbol search (e.g. AAPL)" required/><input name="start" type="date" required/><input name="end" type="date" required/><input name="source_path" placeholder="CSV path under data/raw/"/><label className="pill"><input name="refresh" type="checkbox"/> Force refresh</label><button disabled={status === "loading"}>{status === "loading" ? "Fetching historical data…" : "Fetch dataset"}</button></form>{status === "loading" && <div className="skeleton-list compact"><i/><i/></div>}{status !== "idle" && status !== "loading" && <div className={`request-state ${status}`}><span>{status === "success" ? "Dataset ready" : "Fetch unavailable"}</span><p>{message}</p>{status === "error" && <button type="button" disabled={!lastInput} onClick={() => lastInput && fetchDataset(lastInput)}>Retry fetch</button>}</div>}</>}</section>;
}
