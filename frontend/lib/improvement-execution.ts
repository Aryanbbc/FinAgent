import type { ExperimentSummary, HistoricalImprovementRun } from "@/lib/api";

export type ImprovementRunState = { status: "idle" | "running" | "success" | "error"; message: string; result: HistoricalImprovementRun | null };

export const initialImprovementRunState: ImprovementRunState = { status: "idle", message: "", result: null };

export type ImprovementRunEvent =
  | { type: "start" }
  | { type: "success"; result: HistoricalImprovementRun; message: string }
  | { type: "failure"; message: string }
  | { type: "reset" };

export function improvementRunReducer(state: ImprovementRunState, event: ImprovementRunEvent): ImprovementRunState {
  if (event.type === "start") return state.status === "running" ? state : { status: "running", message: "", result: null };
  if (event.type === "success") return { status: "success", message: event.message, result: event.result };
  if (event.type === "failure") return { status: "error", message: event.message, result: null };
  return initialImprovementRunState;
}

/** The public improvement bridge currently has one declared AAPL policy. */
export function canRunImprovement(experiment: ExperimentSummary | null | undefined): experiment is ExperimentSummary {
  return experiment?.asset.toUpperCase() === "AAPL";
}

export function improvementResultMessage(result: HistoricalImprovementRun) {
  if (result.status === "disabled") return "The configured improvement workflow is disabled.";
  if (result.metadata.promoted_version) return `New version promoted: ${result.metadata.promoted_version}.`;
  if (result.metadata.candidate_count === 0) return "No new candidates generated. Existing candidate configurations have already been evaluated.";
  return `No candidate promoted. ${result.metadata.rejected_count} candidate${result.metadata.rejected_count === 1 ? " was" : "s were"} rejected by the existing promotion gate.`;
}

/** Preserve page context; no implicit fallback to another asset is permitted. */
export function improvementContextUrl(currentSearch: string, asset: string, experimentId: string) {
  const params = new URLSearchParams(currentSearch);
  params.set("asset", asset);
  params.set("experiment", experimentId);
  return `/improvements?${params.toString()}`;
}
