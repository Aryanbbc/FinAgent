import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Walk-forward evaluation can legitimately take longer than a read request.
export const maxDuration = 300;

const EXPERIMENT_ID = /^EXP-[0-9]{6}$/;
const ASSET = /^[A-Z0-9._^=-]{1,32}$/;
const IMPROVEMENT_CONFIG_BY_ASSET: Record<string, string> = {
  AAPL: "config/aapl_improvement.yaml",
};

type BackendFailure = { error_code?: unknown; message?: unknown; detail?: { message?: unknown } | unknown };
type BackendPayload = BackendFailure & { status?: unknown; experiment_id?: unknown; run_id?: unknown; metadata?: unknown };

function failure(status: number, errorCode: string, message: string) {
  return NextResponse.json({ error_code: errorCode, message }, { status, headers: { "Cache-Control": "no-store" } });
}

function configuredBackendUrl() {
  return (process.env.FINAGENT_API_URL ?? process.env.NEXT_PUBLIC_FINAGENT_API_URL ?? "").trim().replace(/\/$/, "");
}

function backendMessage(payload: BackendFailure, fallback: string) {
  const detail = typeof payload.detail === "object" && payload.detail !== null ? (payload.detail as { message?: unknown }).message : payload.detail;
  return typeof payload.message === "string" ? payload.message : typeof detail === "string" ? detail : fallback;
}

function sameOrigin(request: NextRequest) {
  return request.headers.get("origin") === request.nextUrl.origin;
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** A narrow server-only bridge to FinAgent's existing deterministic workflow. */
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) {
    return failure(403, "INVALID_IMPROVEMENT_ORIGIN", "Improvement requests must originate from this FinAgent deployment.");
  }
  const adminKey = process.env.FINAGENT_SERVER_ADMIN_API_KEY?.trim();
  const backendUrl = configuredBackendUrl();
  if (!adminKey || !backendUrl) {
    return failure(503, "HISTORICAL_IMPROVEMENT_NOT_CONFIGURED", "Historical improvement execution is not configured on this deployment.");
  }

  let body: { experiment_id?: unknown; asset?: unknown };
  try {
    body = await request.json() as { experiment_id?: unknown; asset?: unknown };
  } catch {
    return failure(400, "INVALID_IMPROVEMENT_REQUEST", "Select a persisted AAPL experiment before running an improvement cycle.");
  }
  const experimentId = typeof body.experiment_id === "string" ? body.experiment_id.trim().toUpperCase() : "";
  const asset = typeof body.asset === "string" ? body.asset.trim().toUpperCase() : "";
  const configPath = IMPROVEMENT_CONFIG_BY_ASSET[asset];
  if (!EXPERIMENT_ID.test(experimentId) || !ASSET.test(asset)) {
    return failure(400, "INVALID_IMPROVEMENT_REQUEST", "Select a persisted AAPL experiment before running an improvement cycle.");
  }
  if (!configPath) {
    return failure(400, "UNSUPPORTED_IMPROVEMENT_ASSET", `Controlled improvement is not configured for ${asset}. Select an AAPL experiment.`);
  }

  let response: Response;
  try {
    response = await fetch(`${backendUrl}/api/improvements/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-FinAgent-Admin-Key": adminKey },
      body: JSON.stringify({ config_path: configPath, experiment_id: experimentId, asset }),
      cache: "no-store",
      signal: AbortSignal.timeout(295_000),
    });
  } catch (error) {
    const timedOut = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
    return timedOut
      ? failure(504, "HISTORICAL_IMPROVEMENT_TIMEOUT", "The improvement cycle timed out before it completed. No promotion was assumed.")
      : failure(503, "HISTORICAL_IMPROVEMENT_UNAVAILABLE", "Historical improvement execution is temporarily unavailable. Please try again.");
  }

  const payload = await response.json().catch(() => ({})) as BackendPayload;
  if (!response.ok) {
    if (response.status === 404) return failure(404, "EXPERIMENT_NOT_FOUND", "The selected experiment no longer exists. Refresh the research record and select it again.");
    const code = typeof payload.error_code === "string" ? payload.error_code : "HISTORICAL_IMPROVEMENT_FAILED";
    return failure(response.status, code, backendMessage(payload, "The improvement cycle could not be completed."));
  }
  if (payload.experiment_id !== experimentId || typeof payload.status !== "string" || typeof payload.metadata !== "object" || payload.metadata === null) {
    return failure(502, "HISTORICAL_IMPROVEMENT_RESPONSE_INVALID", "The research service returned an incomplete improvement result.");
  }
  const metadata = payload.metadata as Record<string, unknown>;
  const candidateCount = numberValue(metadata.candidate_count);
  const evaluatedCount = numberValue(metadata.evaluated_count);
  const rejectedCount = numberValue(metadata.rejected_count);
  const promotedVersion = metadata.promoted_version;
  if (candidateCount === null || evaluatedCount === null || rejectedCount === null || !(typeof promotedVersion === "string" || promotedVersion === null)) {
    return failure(502, "HISTORICAL_IMPROVEMENT_RESPONSE_INVALID", "The research service returned incomplete candidate evidence.");
  }
  return NextResponse.json({
    status: payload.status,
    experiment_id: experimentId,
    run_id: typeof payload.run_id === "string" ? payload.run_id : null,
    metadata: { candidate_count: candidateCount, evaluated_count: evaluatedCount, rejected_count: rejectedCount, promoted_version: promotedVersion },
  }, { headers: { "Cache-Control": "no-store" } });
}
