"use client";

import { useEffect, useState } from "react";
import { api, System } from "@/lib/api";
import { dateTime } from "@/lib/format";

type Status = { api: "loading" | "ok" | "degraded" | "unavailable"; system?: System };

export function GlobalStatus() {
  const [status, setStatus] = useState<Status>({ api: "loading" });
  useEffect(() => {
    let active = true;
    Promise.all([api.health(), api.system()]).then(([health, system]) => {
      if (active) setStatus({ api: health.status, system });
    }).catch(() => { if (active) setStatus({ api: "unavailable" }); });
    return () => { active = false; };
  }, []);
  const label = status.api === "loading" ? "Checking local API" : status.api === "ok" ? "API online" : status.api === "degraded" ? "API degraded" : "API unavailable";
  return <section className={`global-status ${status.api}`} aria-live="polite">
    <span className="status-dot" /> <strong>{label}</strong>
    {status.system && <span>{status.system.database_backend} {status.system.database_status} · {status.system.dataset_count} datasets · latest run {dateTime(status.system.last_successful_run)}</span>}
  </section>;
}
