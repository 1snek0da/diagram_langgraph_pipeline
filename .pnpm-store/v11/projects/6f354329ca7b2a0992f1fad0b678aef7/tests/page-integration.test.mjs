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
  assert.match(html, /getReportView/);
  assert.match(html, /getMarketView/);
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
  assert.match(html, /getReportView\(runId\)/);
  assert.match(html, /id="industryValuationBadge"/);
  assert.match(html, /id="reportRiskGroups"/);
  assert.doesNotMatch(html, /演示参数/);
});

test("market view is run-scoped and renders the returned series", () => {
  assert.match(html, /name === 'market'\) loadMarket\(runId\)/);
  assert.match(html, /getMarketView\(runId/);
  assert.match(html, /id="marketCanvas"/);
  assert.match(html, /data-value="intraday"/);
  assert.match(html, /drawMarketChart/);
  assert.doesNotMatch(html, /行情接口待接入/);
  assert.doesNotMatch(html, /<strong class="mono">AAPL<\/strong>/);
});

test("analysis form sends a date range with the final date defaulting to today", () => {
  assert.match(html, /id="analysisStartDate"/);
  assert.match(html, /id="analysisEndDate"/);
  assert.match(html, /start_date: startDate/);
  assert.match(html, /as_of_date: endDate/);
  assert.match(html, /localDateValue\(today\)/);
  assert.doesNotMatch(html, /value="2026-07-22"/);
});

test("analysis form exposes market and news acquisition limits", () => {
  assert.match(html, /id="reportDays"/);
  assert.match(html, /id="technicalDays"/);
  assert.match(html, /id="marketBarsPerDay"/);
  assert.match(html, /id="newsPerDay"/);
  assert.match(html, /id="newsLimit"/);
  assert.match(html, /market_bars_per_day:/);
  assert.match(html, /news_per_day:/);
  assert.match(html, /id="workflowDataScope"/);
});
