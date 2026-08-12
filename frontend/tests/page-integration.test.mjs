import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const html = fs.readFileSync(new URL("../public/trading-analysis-ui-design.html", import.meta.url), "utf8");

test("published terminal wires the original page to the shared API client", () => {
  assert.match(html, /\/api-client\.mjs/);
  assert.match(html, /createApiClient/);
  assert.match(html, /createRun/);
  assert.match(html, /listRuns/);
  assert.match(html, /getNodes/);
  assert.match(html, /getReport/);
  assert.match(html, /getMarketBars/);
  assert.doesNotMatch(html, /推进演示状态/);
});

test("workflow nodes expose in-card progress fill and failure details", () => {
  assert.match(html, /node-progress-track/);
  assert.match(html, /node-progress-fill/);
  assert.match(html, /error_summary/);
  assert.match(html, /progress-fill/);
  assert.match(html, /setTimeout\(\(\) => loadWorkflow/);
});

test("report navigation loads the selected run report", () => {
  assert.match(html, /name === 'report'\) loadReport\(runId\)/);
  assert.match(html, /getReport\(runId\)/);
});
