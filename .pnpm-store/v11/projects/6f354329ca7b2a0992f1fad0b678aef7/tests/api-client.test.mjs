import assert from "node:assert/strict";
import test from "node:test";
import { ApiClientError, createApiClient } from "../public/api-client.mjs";

test("client uses the versioned same-origin API and normalizes retryable errors", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return new Response(JSON.stringify({
      error: { code: "REPORT_NOT_READY", message: "Analysis report is not ready", retryable: true },
    }), { status: 409, headers: { "Content-Type": "application/json" } });
  };
  try {
    await assert.rejects(
      createApiClient().getReport("run/1"),
      (error) => error instanceof ApiClientError
        && error.code === "REPORT_NOT_READY"
        && error.retryable
        && error.status === 409,
    );
    assert.equal(calls[0][0], "/api/v1/analysis-runs/run%2F1/report");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("client binds report and market presentation endpoints to the run id", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    const client = createApiClient();
    await client.getReportView("run/1");
    await client.getMarketView("run/1", { period: "weekly", adjustment: "none", limit: 250 });
    assert.equal(calls[0], "/api/v1/analysis-runs/run%2F1/report-view");
    assert.equal(calls[1], "/api/v1/analysis-runs/run%2F1/market-view?period=weekly&adjustment=none&limit=250");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

