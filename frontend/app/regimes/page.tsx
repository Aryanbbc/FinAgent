import { DataState } from "@/components/data-state";
import { api } from "@/lib/api";
import { load } from "@/lib/load";
import { label, percent } from "@/lib/format";

export default async function Regimes() {
  const experiments = await load(api.experiments("?limit=1")); const id = experiments.data?.items[0]?.experiment_id;
  const regimes = id ? await load(api.regimes(id)) : { data: null, error: null };
  return <><header className="page-head"><div><p className="eyebrow">V0.2 Causal Detection</p><h1>Market Regimes</h1><p className="subtle">Rolling returns, volatility, trend slope, momentum, and drawdown observed only at or before each timestamp.</p></div></header><DataState error={experiments.error ?? regimes.error} empty={!regimes.data?.items.length}>{regimes.data && <><div className="metric-grid">{Object.entries(regimes.data.distribution).map(([regime,count]) => <section className="metric-card" key={regime}><p>{label(regime)}</p><strong>{count}</strong><small>observations</small></section>)}</div><div className="split"><section className="panel"><h2>Regime history</h2><table><thead><tr><th>Date</th><th>Regime</th><th>Confidence</th><th>Volatility</th><th>Drawdown</th></tr></thead><tbody>{regimes.data.items.slice(-18).reverse().map(item => <tr key={item.timestamp}><td>{item.timestamp.slice(0,10)}</td><td>{label(item.regime)}</td><td>{percent(item.confidence)}</td><td>{percent(item.rolling_volatility)}</td><td>{percent(item.drawdown)}</td></tr>)}</tbody></table></section><section className="panel"><h2>Memory: best strategy by regime</h2>{Object.entries(regimes.data.best_strategies).map(([regime, entries]) => <div key={regime}><h3>{label(regime)}</h3>{entries.length ? <ul className="list">{entries.map(entry => <li key={entry.experiment_id}><strong>{entry.strategy}</strong><br/><small>{percent(entry.regime_return)} · {entry.experiment_id}</small></li>)}</ul> : <p className="subtle">No memory record yet.</p>}</div>)}</section></div></>}</DataState></>;
}
