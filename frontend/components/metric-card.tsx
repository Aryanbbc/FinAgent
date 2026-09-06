export function MetricCard({ label, value, note, tone = "neutral" }: { label: string; value: string; note?: string; tone?: "neutral" | "positive" | "negative" }) {
  return <section className={`metric-card ${tone}`}><p>{label}</p><strong>{value}</strong>{note && <small>{note}</small>}</section>;
}
