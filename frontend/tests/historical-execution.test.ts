import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { NextRequest } from "next/server";
import { POST } from "../app/api/research/experiments/run/route";
import { POST as runImprovement } from "../app/api/research/improvements/run/route";
import { api } from "../lib/api";
import { dashboardContextUrl } from "../lib/dashboard-context";
import { globalSelectionUrl, isSelectionAwareRoute } from "../lib/global-selection";
import { historicalRunReducer, initialHistoricalRunState } from "../lib/historical-execution";
import { canRunImprovement, improvementContextUrl, improvementResultMessage, improvementRunReducer, improvementViewState, initialImprovementRunState, resolveImprovementExperiment } from "../lib/improvement-execution";

const routeUrl = "https://finagent.example/api/research/experiments/run";

function routeRequest(datasetId = "DATA-AUTO-AAPL-1D") {
  return new NextRequest(routeUrl, {
    method: "POST",
    headers: { Origin: "https://finagent.example", "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId }),
  });
}

function improvementRequest(experimentId = "EXP-000002", asset = "AAPL") {
  return new NextRequest("https://finagent.example/api/research/improvements/run", {
    method: "POST",
    headers: { Origin: "https://finagent.example", "Content-Type": "application/json" },
    body: JSON.stringify({ experiment_id: experimentId, asset }),
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

test("browser improvement client sends only the explicit AAPL experiment context", async () => {
  const original = globalThis.fetch;
  let path = ""; let body = ""; let headers: Headers | undefined;
  globalThis.fetch = async (input, init) => {
    path = String(input); body = String(init?.body); headers = new Headers(init?.headers);
    return new Response(JSON.stringify({ status: "completed", experiment_id: "EXP-000002", run_id: "CAND-0001", metadata: { candidate_count: 1, evaluated_count: 1, rejected_count: 1, promoted_version: null } }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try { await api.runImprovementCycle("EXP-000002", "AAPL"); } finally { globalThis.fetch = original; }
  assert.equal(path, "/api/research/improvements/run");
  assert.equal(body, '{"experiment_id":"EXP-000002","asset":"AAPL"}');
  assert.equal(headers?.has("X-FinAgent-Admin-Key"), false);
});

test("server improvement bridge forwards the explicit parent and returns real rejection evidence", async () => {
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example/", FINAGENT_SERVER_ADMIN_API_KEY: "server-only-test-secret" }, async () => {
    const original = globalThis.fetch;
    let target = ""; let request: RequestInit | undefined;
    globalThis.fetch = async (input, init) => {
      target = String(input); request = init;
      return new Response(JSON.stringify({ workflow: "improvement", status: "completed", experiment_id: "EXP-000002", run_id: "CAND-0001", metadata: { candidate_count: 1, evaluated_count: 1, rejected_count: 1, promoted_version: null } }), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    try {
      const response = await runImprovement(improvementRequest());
      assert.equal(response.status, 200);
      assert.deepEqual(await response.json(), { status: "completed", experiment_id: "EXP-000002", run_id: "CAND-0001", metadata: { candidate_count: 1, evaluated_count: 1, rejected_count: 1, promoted_version: null } });
    } finally { globalThis.fetch = original; }
    assert.equal(target, "https://api.finagent.example/api/improvements/run");
    assert.equal(new Headers(request?.headers).get("X-FinAgent-Admin-Key"), "server-only-test-secret");
    assert.equal(request?.body, '{"config_path":"config/aapl_improvement.yaml","experiment_id":"EXP-000002","asset":"AAPL"}');
  });
});

test("improvement bridge preserves a genuine promoted outcome", async () => {
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example", FINAGENT_SERVER_ADMIN_API_KEY: "server-only-test-secret" }, async () => {
    const original = globalThis.fetch;
    globalThis.fetch = async () => new Response(JSON.stringify({ workflow: "improvement", status: "completed", experiment_id: "EXP-000002", run_id: "CAND-0002", metadata: { candidate_count: 2, evaluated_count: 2, rejected_count: 1, promoted_version: "FinAgent-A0002" } }), { status: 200, headers: { "Content-Type": "application/json" } });
    try {
      const response = await runImprovement(improvementRequest());
      assert.equal(response.status, 200);
      const result = await response.json();
      assert.equal(result.metadata.promoted_version, "FinAgent-A0002");
    } finally { globalThis.fetch = original; }
  });
});

test("improvement bridge handles missing secret, missing experiment, and backend failures explicitly", async () => {
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example", FINAGENT_SERVER_ADMIN_API_KEY: undefined }, async () => {
    const response = await runImprovement(improvementRequest());
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error_code, "HISTORICAL_IMPROVEMENT_NOT_CONFIGURED");
  });
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example", FINAGENT_SERVER_ADMIN_API_KEY: "server-only-test-secret" }, async () => {
    const original = globalThis.fetch;
    globalThis.fetch = async () => new Response(JSON.stringify({ error_code: "NOT_FOUND", message: "hidden" }), { status: 404, headers: { "Content-Type": "application/json" } });
    try {
      const response = await runImprovement(improvementRequest());
      assert.equal(response.status, 404);
      assert.deepEqual(await response.json(), { error_code: "EXPERIMENT_NOT_FOUND", message: "The selected experiment no longer exists. Refresh the research record and select it again." });
    } finally { globalThis.fetch = original; }
    globalThis.fetch = async () => new Response(JSON.stringify({ error_code: "INVALID_CONFIGURATION", message: "Configured learning policy rejected the request." }), { status: 400, headers: { "Content-Type": "application/json" } });
    try {
      const response = await runImprovement(improvementRequest());
      assert.equal(response.status, 400);
      assert.equal((await response.json()).message, "Configured learning policy rejected the request.");
    } finally { globalThis.fetch = original; }
  });
});

test("improvement bridge rejects no selection and malformed backend evidence", async () => {
  const noSelection = new NextRequest("https://finagent.example/api/research/improvements/run", {
    method: "POST", headers: { Origin: "https://finagent.example", "Content-Type": "application/json" }, body: "{}",
  });
  await withServerEnvironment({ FINAGENT_API_URL: "https://api.finagent.example", FINAGENT_SERVER_ADMIN_API_KEY: "server-only-test-secret" }, async () => {
    const missing = await runImprovement(noSelection);
    assert.equal(missing.status, 400);
    assert.equal((await missing.json()).error_code, "INVALID_IMPROVEMENT_REQUEST");

    const original = globalThis.fetch;
    globalThis.fetch = async () => new Response(JSON.stringify({ status: "completed", experiment_id: "EXP-000002", metadata: {} }), { status: 200, headers: { "Content-Type": "application/json" } });
    try {
      const malformed = await runImprovement(improvementRequest());
      assert.equal(malformed.status, 502);
      assert.equal((await malformed.json()).error_code, "HISTORICAL_IMPROVEMENT_RESPONSE_INVALID");
    } finally { globalThis.fetch = original; }
  });
});

test("improvement UI only enables explicit AAPL selection and preserves it after refresh", () => {
  const aapl = { experiment_id: "EXP-000002", asset: "AAPL", created_at: "2026-09-11", strategy: "momentum", start_date: "2022-01-01", end_date: "2023-01-01", total_return: null, sharpe_ratio: null, maximum_drawdown: null, number_of_trades: null };
  const legacy = { ...aapl, experiment_id: "EXP-000001", asset: "EXAMPLE" };
  assert.equal(canRunImprovement(undefined), false);
  assert.equal(canRunImprovement(legacy), false);
  assert.equal(canRunImprovement(aapl), true);
  const running = improvementRunReducer(initialImprovementRunState, { type: "start" });
  assert.equal(improvementRunReducer(running, { type: "start" }), running);
  const result = { status: "completed" as const, experiment_id: aapl.experiment_id, run_id: "CAND-0001", metadata: { candidate_count: 1, evaluated_count: 1, rejected_count: 1, promoted_version: null } };
  const completed = improvementRunReducer(running, { type: "success", result, message: improvementResultMessage(result) });
  assert.match(completed.message, /No candidate promoted/);
  const query = new URL(improvementContextUrl("view=cycle", aapl.asset, aapl.experiment_id), "https://finagent.example").searchParams;
  assert.equal(query.get("asset"), "AAPL");
  assert.equal(query.get("experiment"), "EXP-000002");
  assert.equal(query.get("view"), "cycle");
});

test("improvement selection canonicalizes a direct AAPL link without falling back to EXAMPLE", () => {
  const aapl = { experiment_id: "EXP-000002", asset: "AAPL", created_at: "2026-09-11", strategy: "momentum", start_date: "2022-01-01", end_date: "2023-01-01", total_return: null, sharpe_ratio: null, maximum_drawdown: null, number_of_trades: null };
  const legacy = { ...aapl, experiment_id: "EXP-000001", asset: "EXAMPLE" };
  const experiments = [legacy, aapl];
  assert.equal(resolveImprovementExperiment(experiments, "AAPL", "EXP-000002")?.experiment_id, aapl.experiment_id);
  assert.equal(resolveImprovementExperiment(experiments, undefined, undefined)?.experiment_id, aapl.experiment_id);
  assert.equal(resolveImprovementExperiment(experiments, "AAPL", legacy.experiment_id)?.experiment_id, aapl.experiment_id);
  assert.equal(resolveImprovementExperiment([legacy], undefined, undefined), null);
  const deepLink = improvementContextUrl("view=cycle", aapl.asset, aapl.experiment_id);
  assert.equal(deepLink, "/improvements?view=cycle&asset=AAPL&experiment=EXP-000002");
  assert.equal(isSelectionAwareRoute("/improvements"), true);
  assert.equal(globalSelectionUrl("/improvements", "view=cycle", aapl.asset, aapl.experiment_id), deepLink);
  assert.equal(globalSelectionUrl("/", "view=cycle", aapl.asset, aapl.experiment_id), "/?view=cycle&asset=AAPL&experiment=EXP-000002");
});

test("improvement empty state distinguishes no selection, ready parent, and persisted evidence", () => {
  const aapl = { experiment_id: "EXP-000002", asset: "AAPL", created_at: "2026-09-11", strategy: "momentum", start_date: "2022-01-01", end_date: "2023-01-01", total_return: null, sharpe_ratio: null, maximum_drawdown: null, number_of_trades: null };
  assert.equal(improvementViewState(null, 0), "select-experiment");
  assert.equal(improvementViewState(aapl, 0), "ready-to-run");
  assert.equal(improvementViewState(aapl, 1), "evidence");
});
