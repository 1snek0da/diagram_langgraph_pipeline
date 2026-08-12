import assert from "node:assert/strict";
import { access, readFile, readdir } from "node:fs/promises";
import test from "node:test";

const templateRoot = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the published trading terminal entry", async () => {
  const response = await render();
  assert.equal(response.status, 307);
  assert.match(response.headers.get("location") ?? "", /\/trading-analysis-ui-design\.html$/);
});

test("keeps the original financial terminal as the browser source", async () => {
  const [page, html] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../public/trading-analysis-ui-design.html", import.meta.url), "utf8"),
  ]);
  assert.match(page, /trading-analysis-ui-design\.html/);
  for (const label of ["研究工作台", "新建分析", "运行任务", "行情视图", "研究报告", "历史记录"]) {
    assert.match(html, new RegExp(label));
  }
});
