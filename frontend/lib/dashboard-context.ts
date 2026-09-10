import type { ExperimentSummary } from "@/lib/api";

function sameAsset(left: string, right: string) {
  return left.trim().toUpperCase() === right.trim().toUpperCase();
}

/** Select the requested experiment only when it belongs to the asset context. */
export function experimentForAsset(
  experiments: ExperimentSummary[],
  asset: string | null | undefined,
  experimentId: string | null | undefined,
): ExperimentSummary | undefined {
  const matching = asset ? experiments.filter((item) => sameAsset(item.asset, asset)) : experiments;
  return matching.find((item) => item.experiment_id === experimentId) ?? matching[0];
}

/** Preserve dashboard filters while replacing its asset/experiment context. */
export function dashboardContextUrl(
  currentSearch: string,
  asset: string,
  experimentId: string | undefined,
): string {
  const params = new URLSearchParams(currentSearch);
  params.set("asset", asset);
  if (experimentId) params.set("experiment", experimentId);
  else params.delete("experiment");
  return `/?${params.toString()}`;
}
