import { DataState } from "@/components/data-state";
import { ImprovementTerminal } from "@/components/improvement-terminal";
import { api } from "@/lib/api";
import { improvementContextUrl, resolveImprovementExperiment } from "@/lib/improvement-execution";
import { load } from "@/lib/load";
import { redirect } from "next/navigation";

type Params = Record<string, string | string[] | undefined>;
type Props = { searchParams: Promise<Params> };

function value(params: Params, key: string) {
  const item = params[key];
  return typeof item === "string" ? item : Array.isArray(item) ? item[0] : undefined;
}

function queryString(params: Params) {
  const query = new URLSearchParams();
  for (const [key, item] of Object.entries(params)) {
    const itemValue = typeof item === "string" ? item : Array.isArray(item) ? item[0] : undefined;
    if (itemValue) query.set(key, itemValue);
  }
  return query.toString();
}

export default async function Improvements({ searchParams }: Props) {
  const query = await searchParams;
  const requestedAsset = value(query, "asset")?.trim().toUpperCase();
  const requestedExperimentId = value(query, "experiment")?.trim().toUpperCase();
  const [improvements, versions, context, experiments] = await Promise.all([
    load(api.improvements("?limit=100")),
    load(api.versions()),
    load(api.improvementContext()),
    load(api.experiments("?limit=100")),
  ]);
  const availableExperiments = experiments.data?.items ?? [];
  const selectedExperiment = resolveImprovementExperiment(availableExperiments, requestedAsset, requestedExperimentId);
  // Direct visits and sidebar navigation become an auditable selection URL.
  // The resolver only supplies AAPL as the policy default, never EXAMPLE.
  if (selectedExperiment && (requestedAsset !== selectedExperiment.asset.toUpperCase() || requestedExperimentId !== selectedExperiment.experiment_id)) {
    redirect(improvementContextUrl(queryString(query), selectedExperiment.asset, selectedExperiment.experiment_id));
  }
  return <>
    <header className="terminal-page-head">
      <div>
        <p className="eyebrow">V0.5 Controlled Evolution</p>
        <h1>Self-Improvement Terminal</h1>
        <p className="subtle">Deterministic post-experiment learning: critique evidence guides a bounded candidate set, then only chronological out-of-sample evidence may create a new version.</p>
      </div>
      <span className="terminal-page-meta">Critic → candidates → walk-forward → gate</span>
    </header>
    <DataState error={improvements.error ?? versions.error ?? context.error ?? experiments.error} empty={false}>
      <ImprovementTerminal improvements={improvements.data?.items ?? []} versions={versions.data?.items ?? []} selectedExperiment={selectedExperiment} experiments={availableExperiments} context={context.data ?? { current_version: null, parent_version_id: null, parent_experiment_id: null, parent_critique: null, candidates_generated: 0, candidates_evaluated: 0, candidates_promoted: 0, candidates_rejected: 0, latest_candidate_status: null, gate_thresholds_persisted: false, cycle_boundaries_persisted: false }}/>
    </DataState>
  </>;
}
