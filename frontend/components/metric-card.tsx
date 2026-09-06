export function MetricCard({ label, value, note, tone = "neutral", hint }: { label: string; value: string; note?: string; tone?: "neutral" | "positive" | "negative"; hint?: string }) {
  return <section className={`metric-card ${tone}`}><p>{label}{hint && <span className="help" title={hint}>i</span>}</p><strong>{value}</strong>{note && <small>{note}</small>}</section>;
}
