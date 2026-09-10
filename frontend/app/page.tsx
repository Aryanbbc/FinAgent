import { DataState } from "@/components/data-state";
import { DashboardWorkspace } from "@/components/dashboard-workspace";
import { api } from "@/lib/api";
import { load } from "@/lib/load";

export default async function Dashboard({ searchParams }: { searchParams: Promise<{ asset?: string; experiment?: string }> }) {
  const context = await searchParams;
  const asset = context.asset?.trim().toUpperCase();
  const experimentQuery = new URLSearchParams({ limit: "100", ...(asset ? { asset } : {}) });
  const validationQuery = new URLSearchParams({ limit: "1", ...(asset ? { asset } : {}) });
  const [experiments, system, improvements, validations] = await Promise.all([load(api.experiments(`?${experimentQuery}`)), load(api.system()), load(api.improvements("?limit=1")), load(api.validations(`?${validationQuery}`))]);
  const latest = experiments.data?.items.find((item) => item.experiment_id === context.experiment) ?? experiments.data?.items[0];
  const [detail, market, regimes, trades, decisions, critique] = latest ? await Promise.all([load(api.experiment(latest.experiment_id)), load(api.experimentMarketData(latest.experiment_id)), load(api.regimes(latest.experiment_id)), load(api.trades(latest.experiment_id)), load(api.decisions(latest.experiment_id, "?limit=1&offset=0")), load(api.critique(latest.experiment_id))]) : [{ data: null, error: null }, { data: null, error: null }, { data: null, error: null }, { data: null, error: null }, { data: null, error: null }, { data: null, error: null }];
  const promotion = improvements.data?.items[0]; const validation = validations.data?.items[0];
  return <><header className="terminal-page-head"><div><p className="eyebrow">Research command center</p><h1>Quant research terminal</h1><p className="subtle">Historical simulation evidence only. This workspace never submits trading orders.</p></div><span className="terminal-page-meta">Latest persisted experiment</span></header><DataState error={experiments.error ?? detail.error ?? system.error} empty={!latest}>{latest && detail.data && <DashboardWorkspace latest={latest} experiment={detail.data} market={market.data} regimes={regimes.data?.items ?? []} trades={trades.data?.items ?? []} decisions={decisions.data?.items ?? []} critique={critique.data} system={system.data} promotion={promotion} validation={validation}/>}</DataState></>;
}
