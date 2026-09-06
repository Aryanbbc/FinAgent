import { MarkdownReport } from "@/components/markdown-report";
import { DataState } from "@/components/data-state";
import { api, apiBase } from "@/lib/api";
import { load } from "@/lib/load";

export default async function Reports({ searchParams }: { searchParams: Promise<{ experimentId?: string }> }) {
  const params = await searchParams;
  const experiments = await load(api.experiments("?limit=100")); const id = params.experimentId ?? experiments.data?.items[0]?.experiment_id;
  const report = id ? await load(api.report(id)) : { data: null, error: null };
  return <><header className="page-head"><div><p className="eyebrow">Reproducible Artifact</p><h1>Reports</h1><p className="subtle">Rendered locally from persisted V0.6 research reports.</p></div>{report.data && <a className="pill" href={`${apiBase}${report.data.download_url}`}>Download Markdown</a>}</header><form className="filters"><select name="experimentId" defaultValue={id}>{experiments.data?.items.map(item => <option value={item.experiment_id} key={item.experiment_id}>{item.experiment_id} · {item.strategy} · {item.asset}</option>)}</select><button>View report</button></form><DataState error={experiments.error ?? report.error} empty={!report.data}>{report.data && <MarkdownReport markdown={report.data.markdown}/>}</DataState></>;
}
