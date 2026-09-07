import { LiveWorkspace } from "@/components/live-workspace";
import { api } from "@/lib/api";
import { load } from "@/lib/load";

export default async function LivePage() {
  const [status, symbols] = await Promise.all([load(api.liveStatus()), load(api.liveSymbols())]);
  const symbol = symbols.data?.items[0]?.symbol ?? status.data?.symbols[0]?.symbol ?? "AAPL";
  const [snapshot, history, signals, events] = await Promise.all([
    load(api.liveSnapshot(symbol)), load(api.liveHistory(symbol)), load(api.liveSignals(symbol)), load(api.liveEvents(symbol)),
  ]);
  return <LiveWorkspace initialSymbols={symbols.data?.items ?? []} initialState={status.data?.symbols[0] ?? null} initialSnapshot={snapshot.data} initialHistory={history.data?.items ?? []} initialSignals={signals.data?.items ?? []} initialEvents={events.data?.items ?? []} pollSeconds={status.data?.poll_seconds ?? 60} error={status.error ?? symbols.error ?? snapshot.error ?? history.error ?? signals.error ?? events.error}/>;
}
