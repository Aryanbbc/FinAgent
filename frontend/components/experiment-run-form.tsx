"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { api, publicMutationControlsEnabled, type DatasetSummary, type ExperimentRunInput } from "@/lib/api";

export function ExperimentRunForm({ datasets }: { datasets: DatasetSummary[] }) {
  const [status, setStatus] = useState<"idle" | "running" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [experimentId, setExperimentId] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const startDate = String(values.get("start_date") || ""); const endDate = String(values.get("end_date") || "");
    if (startDate && endDate && startDate > endDate) { setStatus("error"); setMessage("The end date must be on or after the start date."); return; }
    const number = (name: string) => { const value = String(values.get(name) ?? ""); return value ? Number(value) : undefined; };
    const input: ExperimentRunInput = {
      config_path: String(values.get("config_path")), dataset_id: String(values.get("dataset_id") || "") || undefined,
      strategy_name: String(values.get("strategy_name")) as ExperimentRunInput["strategy_name"], agents_enabled: values.get("agents_enabled") === "on",
      starting_capital: number("starting_capital"), percentage_fee: number("percentage_fee"), fixed_fee: number("fixed_fee"),
      position_fraction: number("position_fraction"), risk_max_position_size: number("risk_max_position_size"),
      risk_max_drawdown: number("risk_max_drawdown"), risk_max_volatility: number("risk_max_volatility"),
      start_date: startDate || undefined, end_date: endDate || undefined,
    };
    if (Object.values(input).some((value) => typeof value === "number" && Number.isNaN(value))) { setStatus("error"); setMessage("Numeric controls must contain valid numbers."); return; }
    setStatus("running"); setMessage(""); setExperimentId(null);
    try {
      const result = await api.run("experiments", input) as { experiment_id?: string; metadata?: { trade_count?: number } };
      setExperimentId(result.experiment_id ?? null); setStatus("success"); setMessage(`Historical experiment completed${result.metadata?.trade_count !== undefined ? ` with ${result.metadata.trade_count} simulated trades` : ""}.`);
    } catch (error) { setStatus("error"); setMessage(error instanceof Error ? error.message : "The historical experiment could not be completed."); }
  }
  return <section className="panel run-form"><div className="panel-title-row"><div><h2>Run controlled historical experiment</h2><p className="subtle">Only bounded configuration values are exposed. This form cannot enable live or paper trading.</p></div></div>{!publicMutationControlsEnabled ? <p className="notice">This public deployment is read-only. Historical runs require the server-side administrator API key and cannot be initiated from the browser.</p> : <><form onSubmit={submit} className="run-controls"><label>Configuration<select name="config_path" defaultValue="config/experiments.yaml"><option value="config/experiments.yaml">Standard experiment</option><option value="config/demo.yaml">Bundled demo</option><option value="config/final_experiment.yaml">Release reference</option></select></label><label>Dataset<select name="dataset_id"><option value="">Configuration default</option>{datasets.map((item) => <option value={item.dataset_id} key={item.dataset_id}>{item.symbol} · {item.dataset_id}</option>)}</select></label><label>Baseline strategy<select name="strategy_name" defaultValue="momentum"><option value="momentum">Momentum</option><option value="moving_average">Moving average</option><option value="mean_reversion">Mean reversion</option></select></label><label>Starting capital<input name="starting_capital" type="number" min="1" step="1000" defaultValue="100000" required/></label><label>Transaction fee<input name="percentage_fee" type="number" min="0" max="0.1" step="0.0001" defaultValue="0.001" required/></label><label>Fixed fee<input name="fixed_fee" type="number" min="0" step="0.01" defaultValue="0" required/></label><label>Position fraction<input name="position_fraction" type="number" min="0.01" max="1" step="0.05" defaultValue="1" required/></label><label>From<input name="start_date" type="date"/></label><label>To<input name="end_date" type="date"/></label><label className="check-field"><input name="agents_enabled" type="checkbox" defaultChecked/> Enable deterministic agents</label><details className="advanced-controls"><summary>Risk settings</summary><div><label>Maximum position<input name="risk_max_position_size" type="number" min="0.01" max="1" step="0.05" defaultValue="1"/></label><label>Maximum drawdown<input name="risk_max_drawdown" type="number" min="0.01" max="0.99" step="0.01" defaultValue="0.2"/></label><label>Maximum volatility<input name="risk_max_volatility" type="number" min="0.01" max="5" step="0.05" defaultValue="0.5"/></label></div></details><button disabled={status === "running"}>{status === "running" ? "Running historical simulation…" : "Run experiment"}</button></form>{status !== "idle" && <div className={`request-state ${status}`} aria-live="polite"><span>{status === "running" ? "Working" : status === "success" ? "Completed" : "Unable to run"}</span><p>{message}</p>{experimentId && <Link className="button-link" href={`/experiments/${experimentId}`}>Open {experimentId}</Link>}{status === "error" && <button type="button" onClick={() => setStatus("idle")}>Edit and retry</button>}</div>}</>}</section>;
}
