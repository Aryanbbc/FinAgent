"use client";

import { useReducer, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { dashboardContextUrl } from "@/lib/dashboard-context";
import { historicalRunReducer, initialHistoricalRunState } from "@/lib/historical-execution";

export function DashboardRunExperimentAction({ asset, datasetId }: { asset: string; datasetId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [run, dispatch] = useReducer(historicalRunReducer, initialHistoricalRunState);
  const inFlight = useRef(false);

  async function runExperiment() {
    if (inFlight.current) return;
    inFlight.current = true;
    dispatch({ type: "start" });
    try {
      const result = await api.runHistoricalExperiment(datasetId);
      dispatch({ type: "success", experimentId: result.experiment_id, message: `Historical experiment completed. Loading the persisted ${asset} research record…` });
      router.replace(dashboardContextUrl(searchParams.toString(), asset, result.experiment_id));
      router.refresh();
    } catch (error) {
      dispatch({ type: "failure", message: error instanceof Error ? error.message : "The historical experiment could not be completed." });
    } finally {
      inFlight.current = false;
    }
  }

  return <><button type="button" className="button-link" disabled={run.status === "running"} onClick={() => void runExperiment()}>{run.status === "running" ? `Running ${asset} experiment…` : "Run first experiment"}</button>{run.status !== "idle" && <div className={`request-state ${run.status}`} role={run.status === "error" ? "alert" : undefined} aria-live="polite"><span>{run.status === "running" ? "Running" : run.status === "success" ? "Completed" : "Unable to run"}</span><p>{run.message}</p>{run.status === "error" && <button type="button" onClick={() => dispatch({ type: "reset" })}>Retry</button>}</div>}</>;
}
