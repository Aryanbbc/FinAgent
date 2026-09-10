import Link from "next/link";
import { DataState } from "@/components/data-state";
import { DatasetCharts } from "@/components/dataset-charts";
import { DatasetMarketPanel } from "@/components/dataset-market-panel";
import { api, type Dataset } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { load } from "@/lib/load";

function metadataText(metadata: Record<string, unknown>, key: string, fallback = "—"): string {
  const value = metadata[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

function requestedRange(metadata: Record<string, unknown>): string {
  const range = metadata.requested_date_range;
  if (!range || typeof range !== "object" || Array.isArray(range)) return "Not recorded";
  const { start_date: startDate, end_date: endDate } = range as Record<string, unknown>;
  return typeof startDate === "string" && typeof endDate === "string" ? `${startDate} – ${endDate}` : "Not recorded";
}

function metadataValue(value: string): string {
  return value === "—" || value === "Not recorded" ? value : label(value);
}

function DatasetMetadataCard({ dataset }: { dataset: Dataset }) {
  const metadata = dataset.metadata;
  const actualProvider = metadataText(metadata, "actual_provider", dataset.provider);
  const requestedProvider = metadataText(metadata, "requested_provider", "Not recorded");
  const fetchTimestamp = metadataText(metadata, "fetch_timestamp", dataset.last_refreshed_at);
  const fields = [
    ["Symbol", dataset.symbol],
    ["Exchange", metadataText(metadata, "exchange", dataset.exchange ?? "—")],
    ["Currency", metadataText(metadata, "currency")],
    ["Asset class", metadataText(metadata, "asset_class", dataset.asset_class)],
    ["Timezone", metadataText(metadata, "timezone")],
    ["Actual provider", metadataValue(actualProvider)],
    ["Requested provider", metadataValue(requestedProvider)],
    ["Interval", metadataText(metadata, "requested_interval", dataset.interval)],
    ["Requested date range", requestedRange(metadata)],
    ["Actual data range", `${dataset.start_date} – ${dataset.end_date}`],
    ["Row count", dataset.row_count.toLocaleString("en-US")],
    ["Quality score", `${dataset.quality_score.toFixed(3)} · ${label(dataset.validation_status)}`],
    ["Fetch timestamp", dateTime(fetchTimestamp)],
  ] as const;

  return <section className="panel metadata-panel">
    <div className="panel-title-row">
      <div>
        <p className="terminal-overline">Dataset record</p>
        <h2>Metadata and provenance</h2>
      </div>
      <span className={`metadata-status ${dataset.validation_status}`}>{label(dataset.validation_status)}</span>
    </div>
    <dl className="metadata-grid">
      {fields.map(([name, value]) => <div key={name} className="metadata-field"><dt>{name}</dt><dd>{value}</dd></div>)}
    </dl>
    <details className="metadata-debug">
      <summary>View raw metadata</summary>
      <pre>{JSON.stringify(metadata, null, 2)}</pre>
    </details>
  </section>;
}

export default async function DatasetPage({ params }: { params: Promise<{ datasetId: string }> }) {
  const { datasetId } = await params;
  const result = await load(api.dataset(datasetId));
  const item = result.data;

  return <>
    <header className="page-head">
      <div>
        <p className="eyebrow">Dataset Detail</p>
        <h1>{datasetId}</h1>
        <p className="subtle">Immutable cache revision, quality diagnostics, provider metadata, and normalized daily OHLCV sample.</p>
      </div>
      <Link className="pill" href="/data">Back to data</Link>
    </header>
    <DataState error={result.error} empty={!item}>
      {item && <>
        <div className="metric-grid">
          <section className="metric-card"><p>Provider / symbol</p><strong>{item.provider} · {item.symbol}</strong></section>
          <section className="metric-card"><p>Quality score <span className="help" title="Transparent score from completeness, chronology, OHLC validity, gaps, and timezone checks.">i</span></p><strong className={item.validation_status === "valid" ? "good" : "notice"}>{item.quality_score.toFixed(3)}</strong></section>
          <section className="metric-card"><p>Rows / interval</p><strong>{item.row_count} · {item.interval}</strong></section>
          <section className="metric-card"><p>Adjustment mode</p><strong>{String(item.metadata.adjustment_mode ?? "unknown")}</strong></section>
        </div>
        <section className="panel"><h2>Interactive historical price preview</h2><DatasetMarketPanel datasetId={datasetId}/></section>
        <section className="panel"><h2>Close and volume sample</h2><DatasetCharts rows={item.sample_rows}/></section>
        <div className="split">
          <section className="panel">
            <h2>Validation and quality</h2>
            <p className={item.validation.status === "valid" ? "good" : item.validation.status === "warning" ? "notice" : "bad"}>{item.validation.status}</p>
            <ul className="list">
              {Object.entries(item.validation.quality.components).map(([name, value]) => <li key={name}><strong>{name.replaceAll("_", " ")}</strong><br/><small>{value.toFixed(3)}</small></li>)}
            </ul>
            {item.validation.issues.map(issue => <p key={issue.code} className={issue.severity === "error" ? "bad" : "notice"}>{issue.code}: {issue.message} ({issue.count})</p>)}
          </section>
          <DatasetMetadataCard dataset={item}/>
        </div>
        <section className="panel">
          <h2>Version history</h2>
          <div className="table-wrap"><table><thead><tr><th>Version</th><th>Rows</th><th>Quality</th><th>Refreshed</th></tr></thead><tbody>{item.versions.map(version => <tr key={version.version_id}><td>{version.version_id}</td><td>{version.row_count}</td><td>{version.quality_score.toFixed(3)}</td><td>{version.last_refreshed_at}</td></tr>)}</tbody></table></div>
        </section>
        <section className="panel">
          <h2>Normalized OHLCV rows</h2>
          <div className="table-wrap"><table><thead><tr><th>Timestamp</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead><tbody>{item.sample_rows.map(row => <tr key={row.timestamp}><td>{row.timestamp}</td><td>{row.open}</td><td>{row.high}</td><td>{row.low}</td><td>{row.close}</td><td>{row.volume}</td></tr>)}</tbody></table></div>
        </section>
      </>}
    </DataState>
  </>;
}
