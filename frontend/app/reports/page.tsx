import { MarkdownReport } from "@/components/markdown-report";
import { DataState } from "@/components/data-state";
import { api, apiBase } from "@/lib/api";
import { load } from "@/lib/load";
import { ReportActions } from "@/components/report-actions";

export default async function Reports({ searchParams }: { searchParams: Promise<{ experimentId?: string }> }) {
  const params = await searchParams;
  const experiments = await load(api.experiments("?limit=100")); const id = params.experimentId ?? experiments.data?.items[0]?.experiment_id;
  const report = id ? await load(api.report(id)) : { data: null, error: null };
  return <><header className="page-head"><div><p className="eyebrow">Reproducible Artifact</p><h1>Reports</h1><p className="subtle">Rendered locally from persisted V0.6 research reports. A missing report is shown as an actionable local-data state, never a broken link.</p></div></header><form className="filters"><label className="filter-field">Experiment<select name="experimentId" defaultValue={id}>{experiments.data?.items.map(item => <option value={item.experiment_id} key={item.experiment_id}>{item.experiment_id} · {item.strategy} · {item.asset}</option>)}</select></label><button>View report</button></form><DataState error={experiments.error ?? report.error} empty={!report.data}>{report.data && <><nav className="section-nav" aria-label="Report sections"><a className="pill" href="#experiment-summary">Summary</a><a className="pill" href="#primary-metrics">Metrics</a><a className="pill" href="#research-validation">Validation</a></nav><ReportActions markdown={report.data.markdown} downloadUrl={`${apiBase}${report.data.download_url}`}/><MarkdownReport markdown={report.data.markdown}/></>}</DataState></>;
}
