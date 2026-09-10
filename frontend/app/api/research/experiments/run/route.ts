import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// A controlled historical run can take longer than a simple read endpoint.
export const maxDuration = 60;

const DATASET_ID = /^DATA-[A-Z0-9-]{3,120}$/;
const STANDARD_EXPERIMENT_CONFIG = "config/experiments.yaml";

type BackendFailure = { error_code?: unknown; message?: unknown; detail?: { message?: unknown } | unknown };

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
  const origin = request.headers.get("origin");
  return origin === request.nextUrl.origin;
}

/**
 * A same-origin, server-only bridge for one bounded historical workflow.
 * Browser code submits a dataset ID only; it never receives an administrator
 * credential, a configurable path, or a trading/execution capability.
 */
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) {
    return failure(403, "INVALID_EXECUTION_ORIGIN", "Historical experiment requests must originate from this FinAgent deployment.");
  }
  const adminKey = process.env.FINAGENT_SERVER_ADMIN_API_KEY?.trim();
  const backendUrl = configuredBackendUrl();
  if (!adminKey || !backendUrl) {
    return failure(503, "HISTORICAL_EXECUTION_NOT_CONFIGURED", "Historical experiment execution is not configured on this deployment.");
  }

  let body: { dataset_id?: unknown };
  try {
    body = await request.json() as { dataset_id?: unknown };
  } catch {
    return failure(400, "INVALID_EXPERIMENT_REQUEST", "A valid dataset ID is required to run a historical experiment.");
  }
  const datasetId = typeof body.dataset_id === "string" ? body.dataset_id.trim().toUpperCase() : "";
  if (!DATASET_ID.test(datasetId)) {
    return failure(400, "INVALID_EXPERIMENT_REQUEST", "A valid dataset ID is required to run a historical experiment.");
  }

  let response: Response;
  try {
    response = await fetch(`${backendUrl}/api/experiments/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-FinAgent-Admin-Key": adminKey },
      body: JSON.stringify({ config_path: STANDARD_EXPERIMENT_CONFIG, dataset_id: datasetId }),
      cache: "no-store",
      signal: AbortSignal.timeout(55_000),
    });
  } catch {
    return failure(503, "HISTORICAL_EXECUTION_UNAVAILABLE", "Historical experiment execution is temporarily unavailable. Please try again.");
  }

  const payload = await response.json().catch(() => ({})) as BackendFailure & { experiment_id?: unknown; status?: unknown; metadata?: unknown };
  if (!response.ok) {
    const code = typeof payload.error_code === "string" ? payload.error_code : "HISTORICAL_EXECUTION_FAILED";
    return failure(response.status, code, backendMessage(payload, "The historical experiment could not be completed."));
  }
  if (typeof payload.experiment_id !== "string" || !payload.experiment_id) {
    return failure(502, "HISTORICAL_EXECUTION_RESPONSE_INVALID", "The research service did not return an experiment ID.");
  }
  return NextResponse.json(
    { status: typeof payload.status === "string" ? payload.status : "completed", experiment_id: payload.experiment_id, metadata: payload.metadata ?? null },
    { headers: { "Cache-Control": "no-store" } },
  );
}
