export type HistoricalRunState = { status: "idle" | "running" | "success" | "error"; message: string; experimentId: string | null };

export const initialHistoricalRunState: HistoricalRunState = { status: "idle", message: "", experimentId: null };

export type HistoricalRunEvent =
  | { type: "start" }
  | { type: "success"; experimentId: string; message: string }
  | { type: "failure"; message: string }
  | { type: "reset" };

/** Keeps a duplicate browser interaction from starting a second simulation. */
export function historicalRunReducer(state: HistoricalRunState, event: HistoricalRunEvent): HistoricalRunState {
  if (event.type === "start") return state.status === "running" ? state : { status: "running", message: "", experimentId: null };
  if (event.type === "success") return { status: "success", message: event.message, experimentId: event.experimentId };
  if (event.type === "failure") return { status: "error", message: event.message, experimentId: null };
  return initialHistoricalRunState;
}
