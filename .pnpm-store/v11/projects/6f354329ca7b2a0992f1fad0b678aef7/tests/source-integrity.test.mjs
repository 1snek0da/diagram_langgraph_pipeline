import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const root = new URL("..", import.meta.url);
const read = (name) => fs.readFileSync(new URL(name, root), "utf8");

test("pins Sites V2 source identity and all six design routes", () => {
  const manifest = JSON.parse(read("sites-source.json"));
  assert.equal(manifest.version, 2);
  assert.equal(manifest.sourceCommit, "b54f8ff76604c80b0974ab4d8a62a2804ce14095");
  assert.deepEqual(manifest.routes, [
    "/workspace", "/analysis", "/workflow", "/market", "/report", "/history",
  ]);

  const html = read("public/trading-analysis-ui-design.html");
  for (const label of ["研究工作台", "新建分析", "运行任务", "行情视图", "研究报告", "历史记录"]) {
    assert.match(html, new RegExp(label));
  }
});
