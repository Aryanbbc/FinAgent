import { DataState } from "@/components/data-state";
import { ImprovementTerminal } from "@/components/improvement-terminal";
import { api } from "@/lib/api";
import { load } from "@/lib/load";

type Props = { searchParams: Promise<{ asset?: string; experiment?: string }> };

export default async function Improvements({ searchParams }: Props) {
  const query = await searchParams;
  const requestedAsset = query.asset?.trim().toUpperCase();
  const [improvements, versions, context, experiments] = await Promise.all([
    load(api.improvements("?limit=100")),
    load(api.versions()),
    load(api.improvementContext()),
    load(api.experiments("?limit=100")),
  ]);
  const availableExperiments = experiments.data?.items ?? [];
  const requestedExperiment = availableExperiments.find((item) => item.experiment_id === query.experiment && (!requestedAsset || item.asset === requestedAsset));
  // An explicit asset may select its newest matching experiment.  With no
  // explicit context we intentionally do not fall back to a legacy EXAMPLE row.
  const selectedExperiment = requestedExperiment ?? (requestedAsset ? availableExperiments.find((item) => item.asset === requestedAsset) ?? null : null);
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
