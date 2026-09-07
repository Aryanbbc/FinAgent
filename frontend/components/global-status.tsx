"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, type DatasetSummary, type ExperimentSummary, type System, type Version } from "@/lib/api";

type Status = { api: "loading" | "ok" | "degraded" | "unavailable"; system?: System; datasets: DatasetSummary[]; experiments: ExperimentSummary[]; regime?: string; agentVersion?: string };

export function GlobalStatus() {
  const router = useRouter(); const pathname = usePathname(); const [status, setStatus] = useState<Status>({ api: "loading", datasets: [], experiments: [] }); const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api.health(), api.system(), api.datasets("?limit=25"), api.experiments("?limit=25"), api.versions()]).then(async ([health, system, datasets, experiments, versions]) => {
      const latest = experiments.items[0]; let regime: string | undefined;
      if (latest) { try { regime = (await api.experiment(latest.experiment_id)).regime.latest?.regime; } catch { /* A missing optional detail must not hide service status. */ } }
      if (active) setStatus({ api: health.status, system, datasets: datasets.items, experiments: experiments.items, regime, agentVersion: latestVersion(versions.items)?.version_id });
    }).catch(() => { if (active) setStatus({ api: "unavailable", datasets: [], experiments: [] }); });
    return () => { active = false; };
  }, []);
  const label = status.api === "loading" ? "Checking API" : status.api === "ok" ? "API online" : status.api === "degraded" ? "API degraded" : "API unavailable";
  return <section className={`global-status ${status.api}`} aria-live="polite">
    <div className="status-cluster"><strong className="topbar-brand">FINAGENT</strong>{status.system && <span className="topbar-version">V{status.system.finagent_version}</span>}<span className="status-divider"/><span className="status-dot"/><strong>{label}</strong><span className="status-divider"/>{status.system && <><span>DB <b>{status.system.database_backend}</b> · {status.system.database_status}</span><span className="status-divider"/><span>REGIME <b>{status.regime?.replaceAll("_", " ") ?? "—"}</b></span><span className="status-divider"/><span>AGENT <b>{status.agentVersion ?? "baseline"}</b></span></>}</div>
    <div className="global-selectors"><label><span>Asset</span><select aria-label="Global asset selector" value="" onChange={(event) => { if (event.target.value) router.push(`/data/${event.target.value}`); }}><option value="">Select asset</option>{status.datasets.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.symbol}</option>)}</select></label><label><span>Experiment</span><select aria-label="Global experiment selector" value="" onChange={(event) => { if (event.target.value) router.push(`/experiments/${event.target.value}`); }}><option value="">Select experiment</option>{status.experiments.map((item) => <option key={item.experiment_id} value={item.experiment_id}>{item.experiment_id}</option>)}</select></label><label className="global-range"><span>Range</span><input aria-label="Global date range from" type="date" value={from} onChange={(event) => setFrom(event.target.value)}/><input aria-label="Global date range to" type="date" value={to} onChange={(event) => setTo(event.target.value)}/><button type="button" title="Apply date range to this experiment view" disabled={!pathname.startsWith("/experiments/") || (!!from && !!to && from > to)} onClick={() => router.replace(`${pathname}?${new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) })}`)}>Apply</button></label></div>
  </section>;
}

function latestVersion(items: Version[]): Version | undefined { return items.at(-1); }
