import { DataState } from "@/components/data-state";
import { ImprovementTerminal } from "@/components/improvement-terminal";
import { api } from "@/lib/api";
import { load } from "@/lib/load";

export default async function Improvements() {
  const [improvements, versions, context] = await Promise.all([
    load(api.improvements("?limit=100")),
    load(api.versions()),
    load(api.improvementContext()),
  ]);
  return <>
    <header className="terminal-page-head">
      <div>
        <p className="eyebrow">V0.5 Controlled Evolution</p>
        <h1>Self-Improvement Terminal</h1>
        <p className="subtle">Deterministic post-experiment learning: critique evidence guides a bounded candidate set, then only chronological out-of-sample evidence may create a new version.</p>
      </div>
      <span className="terminal-page-meta">Critic → candidates → walk-forward → gate</span>
    </header>
    <DataState error={improvements.error ?? versions.error ?? context.error} empty={false}>
      <ImprovementTerminal improvements={improvements.data?.items ?? []} versions={versions.data?.items ?? []} context={context.data ?? { current_version: null, parent_version_id: null, parent_experiment_id: null, parent_critique: null, candidates_generated: 0, candidates_evaluated: 0, candidates_promoted: 0, candidates_rejected: 0, latest_candidate_status: null, gate_thresholds_persisted: false, cycle_boundaries_persisted: false }}/>
    </DataState>
  </>;
}
