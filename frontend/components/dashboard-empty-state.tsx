import Link from "next/link";
import type { DatasetSummary } from "@/lib/api";

/** An intentional research state, distinct from a failed API request. */
export function DashboardDatasetReadyState({ asset, dataset }: { asset: string; dataset: DatasetSummary }) {
  return <section className="state" aria-label="Dataset ready, experiment required">
    <h2>{asset} dataset is ready</h2>
    <p>Run the first experiment to populate research results.</p>
    <p className="subtle">{dataset.dataset_id} · {dataset.row_count.toLocaleString()} daily OHLCV rows · {dataset.start_date} to {dataset.end_date}</p>
    <div className="state-actions">
      <Link className="button-link" href={`/data/${dataset.dataset_id}`}>View dataset</Link>
      <Link className="button-link" href="/experiments">Run first experiment</Link>
    </div>
  </section>;
}
