import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { NextRequest } from "next/server";
import { POST } from "../app/api/research/experiments/run/route";
import { api } from "../lib/api";
import { dashboardContextUrl } from "../lib/dashboard-context";
import { historicalRunReducer, initialHistoricalRunState } from "../lib/historical-execution";

const routeUrl = "https://finagent.example/api/research/experiments/run";

function routeRequest(datasetId = "DATA-AUTO-AAPL-1D") {
  return new NextRequest(routeUrl, {
    method: "POST",
    headers: { Origin: "https://finagent.example", "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId }),
  });
}

async function withServerEnvironment<T>(values: Record<string, string | undefined>, work: () => Promise<T>) {
  const previous = Object.fromEntries(Object.keys(values).map((key) => [key, process.env[key]]));
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
  try { return await work(); } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
}

test("browser execution client sends only a dataset ID to the same-origin bridge", async () => {
  const original = globalThis.fetch;
  let path = ""; let body = ""; let headers: Headers | undefined;
  globalThis.fetch = async (input, init) => {
    path = String(input); body = String(init?.body); headers = new Headers(init?.headers);
    return new Response(JSON.stringify({ status: "completed", experiment_id: "EXP-000002", metadata: null }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    const result = await api.runHistoricalExperiment("DATA-AUTO-AAPL-1D");
    assert.equal(result.experiment_id, "EXP-000002");
  } finally { globalThis.fetch = original; }
  assert.equal(path, "/api/research/experiments/run");
  assert.equal(body, '{"dataset_id":"DATA-AUTO-AAPL-1D"}');
  assert.equal(headers?.has("X-FinAgent-Admin-Key"), false);
  assert.equal(headers?.has("X-FinAgent-Server-Admin-Key"), false);
});

test("server bridge forwards a fixed configuration with its server-only credential", async () => {
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example/", FINAGENT_SERVER_ADMIN_API_KEY: "server-only-test-secret" }, async () => {
    const original = globalThis.fetch;
    let target = ""; let request: RequestInit | undefined;
    globalThis.fetch = async (input, init) => {
      target = String(input); request = init;
      return new Response(JSON.stringify({ status: "completed", experiment_id: "EXP-000002", metadata: { dataset_id: "DATA-AUTO-AAPL-1D" } }), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    try {
      const response = await POST(routeRequest());
      assert.equal(response.status, 200);
      assert.deepEqual(await response.json(), { status: "completed", experiment_id: "EXP-000002", metadata: { dataset_id: "DATA-AUTO-AAPL-1D" } });
    } finally { globalThis.fetch = original; }
    assert.equal(target, "https://api.finagent.example/api/experiments/run");
    assert.equal(new Headers(request?.headers).get("X-FinAgent-Admin-Key"), "server-only-test-secret");
    assert.equal(request?.body, '{"config_path":"config/experiments.yaml","dataset_id":"DATA-AUTO-AAPL-1D"}');
  });
});

test("server bridge reports a configured, readable error when the secret is absent", async () => {
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example", FINAGENT_SERVER_ADMIN_API_KEY: undefined }, async () => {
    const response = await POST(routeRequest());
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), {
      error_code: "HISTORICAL_EXECUTION_NOT_CONFIGURED",
      message: "Historical experiment execution is not configured on this deployment.",
    });
  });
});

test("server bridge preserves a safe backend failure message", async () => {
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example", FINAGENT_SERVER_ADMIN_API_KEY: "server-only-test-secret" }, async () => {
    const original = globalThis.fetch;
    globalThis.fetch = async () => new Response(JSON.stringify({ error_code: "INVALID_CONFIGURATION", message: "The selected dataset cannot be used by this configuration." }), { status: 400, headers: { "Content-Type": "application/json" } });
    try {
      const response = await POST(routeRequest());
      assert.equal(response.status, 400);
      assert.deepEqual(await response.json(), { error_code: "INVALID_CONFIGURATION", message: "The selected dataset cannot be used by this configuration." });
    } finally { globalThis.fetch = original; }
  });
});

test("run state ignores a duplicate click and a completed run selects its new experiment", () => {
  const running = historicalRunReducer(initialHistoricalRunState, { type: "start" });
  assert.equal(running.status, "running");
  assert.equal(historicalRunReducer(running, { type: "start" }), running);
  const completed = historicalRunReducer(running, { type: "success", experimentId: "EXP-000002", message: "done" });
  assert.equal(completed.experimentId, "EXP-000002");
  const query = new URL(dashboardContextUrl("asset=AAPL", "AAPL", completed.experimentId), "https://finagent.example").searchParams;
  assert.equal(query.get("asset"), "AAPL");
  assert.equal(query.get("experiment"), "EXP-000002");
});

test("server-only credential names never appear in the browser API client", async () => {
  const source = await readFile(new URL("../lib/api.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /FINAGENT_(?:SERVER_)?ADMIN_API_KEY/);
  assert.doesNotMatch(source, /X-FinAgent-Admin-Key/);
});
