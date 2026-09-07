import assert from "node:assert/strict";
import test from "node:test";
import { api, ApiError } from "../lib/api";

test("central API client returns parsed typed payloads", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ status: "ok", version: "1.0.0" }), { status: 200, headers: { "Content-Type": "application/json" } });
  try { assert.equal((await api.health()).status, "ok"); } finally { globalThis.fetch = original; }
});

test("central API client exposes useful API errors", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ error_code: "NOT_FOUND", message: "missing", request_id: "req-1" }), { status: 404, headers: { "Content-Type": "application/json" } });
  try { await assert.rejects(api.health(), (error: unknown) => error instanceof ApiError && error.status === 404 && error.code === "NOT_FOUND" && error.requestId === "req-1"); } finally { globalThis.fetch = original; }
});

test("terminal API calls use the bounded persisted-data routes", async () => {
  const original = globalThis.fetch; const paths: string[] = [];
  globalThis.fetch = async (input) => { paths.push(String(input)); return new Response(JSON.stringify({ items: [], downsampled: false, pagination: { limit: 50, offset: 0, total: 0 } }), { status: 200, headers: { "Content-Type": "application/json" } }); };
  try { await api.experimentMarketData("EXP-1", "?limit=50"); await api.activity("?limit=50"); } finally { globalThis.fetch = original; }
  assert.ok(paths.some((path) => path.includes("/api/experiments/EXP-1/market-data?limit=50")));
  assert.ok(paths.some((path) => path.includes("/api/experiments/activity/recent?limit=50")));
});
