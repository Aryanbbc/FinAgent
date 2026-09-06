export function DataState({ error, empty, children }: { error?: string | null; empty?: boolean; children?: React.ReactNode }) {
  if (error) return <section className="state error"><h2>Local data unavailable</h2><p>{error}</p><p>Confirm the FastAPI service is running on the configured local address.</p></section>;
  if (empty) return <section className="state"><h2>No records yet</h2><p>Run a historical experiment through the existing CLI or the controlled local API.</p></section>;
  return <>{children}</>;
}
