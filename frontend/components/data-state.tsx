import Link from "next/link";
import type { ReactNode } from "react";

export function DataState({ error, empty, emptyState, children }: { error?: string | null; empty?: boolean; emptyState?: ReactNode; children?: ReactNode }) {
  if (error) return <section className="state error"><h2>Research data unavailable</h2><p>{error}</p><p>The API, selected dataset, or historical artifact may be unavailable. No research record was changed.</p><Link className="button-link" href="/system">Check system status</Link></section>;
  if (empty && emptyState) return <>{emptyState}</>;
  if (empty) return <section className="state"><h2>No records yet</h2><p>Start with a historical dataset, then run a deterministic simulation.</p><div className="state-actions"><Link className="button-link" href="/data">Fetch dataset</Link><Link className="button-link" href="/experiments">Run first experiment</Link></div></section>;
  return <>{children}</>;
}
