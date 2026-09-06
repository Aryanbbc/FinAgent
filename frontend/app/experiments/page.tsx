import Link from "next/link";
import { DataState } from "@/components/data-state";
import { api } from "@/lib/api";
import { load } from "@/lib/load";
import { date, percent } from "@/lib/format";

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };
export default async function Experiments({ searchParams }: Props) {
  const params = await searchParams; const query = new URLSearchParams();
  for (const key of ["search", "strategy", "asset", "start_date", "end_date"]) { const value = params[key]; if (typeof value === "string" && value) query.set(key, value); }
  const result = await load(api.experiments(query.size ? `?${query}` : ""));
  return <><header className="page-head"><div><p className="eyebrow">Research Archive</p><h1>Experiments</h1><p className="subtle">Filter persisted historical simulations without modifying them.</p></div></header><form className="filters"><input name="search" placeholder="ID, strategy, or asset" defaultValue={typeof params.search === "string" ? params.search : ""}/><input name="strategy" placeholder="Strategy" defaultValue={typeof params.strategy === "string" ? params.strategy : ""}/><input name="asset" placeholder="Asset" defaultValue={typeof params.asset === "string" ? params.asset : ""}/><input name="start_date" type="date" defaultValue={typeof params.start_date === "string" ? params.start_date : ""}/><input name="end_date" type="date" defaultValue={typeof params.end_date === "string" ? params.end_date : ""}/><button>Apply filters</button></form><DataState error={result.error} empty={!result.data?.items.length}>{result.data && <section className="panel"><table><thead><tr><th>Experiment</th><th>Strategy</th><th>Asset</th><th>Period</th><th>Return</th><th>Sharpe</th><th>Drawdown</th></tr></thead><tbody>{result.data.items.map(item => <tr key={item.experiment_id}><td><Link href={`/experiments/${item.experiment_id}`}>{item.experiment_id}</Link></td><td>{item.strategy}</td><td>{item.asset}</td><td>{date(item.start_date)} – {date(item.end_date)}</td><td className={(item.total_return ?? 0) >= 0 ? "good" : "bad"}>{percent(item.total_return)}</td><td>{item.sharpe_ratio?.toFixed(2) ?? "—"}</td><td>{percent(item.maximum_drawdown)}</td></tr>)}</tbody></table><p className="subtle">{result.data.pagination.total} local experiment{result.data.pagination.total === 1 ? "" : "s"}</p></section>}</DataState></>;
}
