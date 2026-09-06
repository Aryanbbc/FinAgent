import assert from "node:assert/strict";
import test from "node:test";
import { api, ApiError } from "../lib/api";

test("central API client returns parsed typed payloads", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ status: "ok", version: "0.7.0" }), { status: 200, headers: { "Content-Type": "application/json" } });
  try { assert.equal((await api.health()).status, "ok"); } finally { globalThis.fetch = original; }
});

test("central API client exposes useful API errors", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: { message: "missing" } }), { status: 404, headers: { "Content-Type": "application/json" } });
  try { await assert.rejects(api.health(), (error: unknown) => error instanceof ApiError && error.status === 404); } finally { globalThis.fetch = original; }
});
