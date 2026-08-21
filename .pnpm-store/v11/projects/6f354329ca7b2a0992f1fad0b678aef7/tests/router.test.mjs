import assert from "node:assert/strict";
import test from "node:test";
import { routeFromLocation, routePath } from "../public/router.mjs";

test("restores all six pages and preserves a run id", () => {
  for (const page of ["workspace", "analysis", "workflow", "market", "report", "history"]) {
    assert.deepEqual(routeFromLocation({ pathname: `/${page}`, search: "?run_id=abc" }), {
      page,
      runId: "abc",
    });
  }
  assert.equal(routePath("report", "run/1"), "/report?run_id=run%2F1");
  assert.deepEqual(routeFromLocation({ pathname: "/unknown", search: "" }), {
    page: "workspace", runId: null,
  });
});
