"use client";

import Link from "next/link";
import { FormEvent, useReducer, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type DatasetSummary } from "@/lib/api";
import { historicalRunReducer, initialHistoricalRunState } from "@/lib/historical-execution";

/** Public UI input is intentionally limited to a persisted dataset ID. */
export function ExperimentRunForm({ datasets }: { datasets: DatasetSummary[] }) {
  const router = useRouter();
  const [datasetId, setDatasetId] = useState(datasets[0]?.dataset_id ?? "");
  const [run, dispatch] = useReducer(historicalRunReducer, initialHistoricalRunState);
  const inFlight = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!datasetId) { dispatch({ type: "failure", message: "Choose a registered dataset before starting an experiment." }); return; }
    if (inFlight.current) return;
    inFlight.current = true;
    dispatch({ type: "start" });
    try {
      const result = await api.runHistoricalExperiment(datasetId);
      dispatch({ type: "success", experimentId: result.experiment_id, message: "Historical experiment completed and persisted." });
      router.refresh();
    } catch (error) {
      dispatch({ type: "failure", message: error instanceof Error ? error.message : "The historical experiment could not be completed." });
    } finally {
      inFlight.current = false;
    }
  }

  return <section className="panel run-form"><div className="panel-title-row"><div><h2>Run controlled historical experiment</h2><p className="subtle">The server applies FinAgent’s standard deterministic configuration to the selected registry dataset. This cannot enable live or paper trading.</p></div></div><form onSubmit={submit} className="run-controls"><label>Dataset<select name="dataset_id" aria-label="Dataset for historical experiment" value={datasetId} onChange={(event) => setDatasetId(event.target.value)} required disabled={run.status === "running"}><option value="" disabled>Select a registered dataset</option>{datasets.map((item) => <option value={item.dataset_id} key={item.dataset_id}>{item.symbol} · {item.dataset_id} · {item.row_count.toLocaleString()} rows</option>)}</select></label><button disabled={!datasetId || run.status === "running"}>{run.status === "running" ? "Running historical simulation…" : "Run historical experiment"}</button></form>{run.status !== "idle" && <div className={`request-state ${run.status}`} role={run.status === "error" ? "alert" : undefined} aria-live="polite"><span>{run.status === "running" ? "Working" : run.status === "success" ? "Completed" : "Unable to run"}</span><p>{run.message}</p>{run.experimentId && <Link className="button-link" href={`/experiments/${run.experimentId}`}>Open {run.experimentId}</Link>}{run.status === "error" && <button type="button" onClick={() => dispatch({ type: "reset" })}>Retry</button>}</div>}</section>;
}
