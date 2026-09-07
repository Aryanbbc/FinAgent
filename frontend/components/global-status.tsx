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
    <span className="status-dot" /> <strong>{label}</strong>
    {status.system && <><span>{status.system.database_backend} · {status.system.database_status}</span><span>V{status.system.finagent_version}</span><span>dataset {status.datasets[0]?.symbol ?? "—"}</span><span>latest {status.experiments[0]?.experiment_id ?? "—"}</span><span>regime {status.regime?.replaceAll("_", " ") ?? "—"}</span><span>agent {status.agentVersion ?? "baseline"}</span></>}
    <div className="global-selectors"><label>Asset<select aria-label="Global asset selector" value="" onChange={(event) => { if (event.target.value) router.push(`/data/${event.target.value}`); }}><option value="">Assets</option>{status.datasets.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.symbol}</option>)}</select></label><label>Experiment<select aria-label="Global experiment selector" value="" onChange={(event) => { if (event.target.value) router.push(`/experiments/${event.target.value}`); }}><option value="">Experiments</option>{status.experiments.map((item) => <option key={item.experiment_id} value={item.experiment_id}>{item.experiment_id}</option>)}</select></label><label>Range<input aria-label="Global date range from" type="date" value={from} onChange={(event) => setFrom(event.target.value)}/><input aria-label="Global date range to" type="date" value={to} onChange={(event) => setTo(event.target.value)}/><button type="button" title="Apply date range to this experiment view" disabled={!pathname.startsWith("/experiments/") || (!!from && !!to && from > to)} onClick={() => router.replace(`${pathname}?${new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) })}`)}>Apply</button></label></div>
  </section>;
}

function latestVersion(items: Version[]): Version | undefined { return items.at(-1); }
