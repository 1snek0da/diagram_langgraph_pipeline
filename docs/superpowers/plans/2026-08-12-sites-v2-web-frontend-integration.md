# Sites V2 Web 前端接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with a verification checkpoint after every task.

**Goal:** 将 Sites 版本 2 的六页 Web 前端原样落地到 `frontend/`，通过现有 FastAPI Router 使用真实 PostgreSQL 数据，并由 FastAPI 在正式环境提供单地址访问。

**Architecture:** 前端保留 Sites V2 的原始工具链和视觉组件，仅增加类型化 API 客户端、页面数据映射和必要状态。FastAPI 继续提供 `/api/v1`，再托管 `frontend/dist` 的静态文件并为客户端路由提供入口回退。Streamlit 保留为调试入口，不参与正式页面。

**Tech Stack:** Sites V2 原始 Web 工具链（以落地源码的 `package.json` 为准）、TypeScript/JavaScript、FastAPI、Uvicorn、PostgreSQL、现有 Python pytest。

## Global Constraints

- Sites 项目 ID 必须使用 `appgprj_6a603dbc97408191ae68ca4e0aa2e74d`。
- 视觉基准必须是 Sites 版本 2，版本源提交为 `b54f8ff76604c80b0974ab4d8a62a2804ce14095`，归档元数据为 39 个文件。
- 不用 Streamlit 控件替换 Sites 原组件，不重新设计六页。
- 前端只调用同源 `/api/v1`，不得连接 PostgreSQL 或保存 `DATABASE_URL`。
- 正式环境由 FastAPI 在 `/` 托管生产构建，在 `/api/v1` 提供 API。
- 每项任务按“先写失败测试、验证失败、最小实现、验证通过、提交”执行。
- 每批结束必须有独立检查点；检查点未通过不得进入下一批。

---

## 文件职责地图

| 文件/目录 | 职责 |
|---|---|
| `frontend/` | Sites V2 原始前端及其原始构建配置 |
| `frontend/src/lib/api-client.*` | 唯一 HTTP 客户端与错误归一化 |
| `frontend/src/lib/models.*` | API 响应的前端类型和页面模型 |
| `frontend/src/pages/*` | 保留 Sites V2 页面组件，仅替换数据接入 |
| `frontend/src/router.*` | 六页路由及运行 ID 上下文恢复 |
| `src/diagram_langgraph_pipeline/api/app.py` | FastAPI 应用、静态目录和 SPA 回退 |
| `tests/api/test_static_frontend.py` | 静态文件、API 优先级和 SPA 回退测试 |
| `tests/frontend/` | 前端 API、路由、映射和状态测试 |
| `scripts/start_web.ps1` | 单地址正式启动说明/脚本 |
| `docs/.../2026-08-12-sites-v2-web-frontend-integration-design.md` | 已批准设计约束 |

---

### Task 1: 固定 Sites V2 源码并建立可构建前端

**Files:**
- Create: `frontend/`（Sites V2 版本 2 的原始源码）
- Create: `frontend/README.md`（来源、版本、构建命令）
- Modify: `frontend/package.json` 或原始工具链配置（仅为当前仓库路径和脚本做必要调整）
- Test: `frontend/tests/source-integrity.test.*`

**Interfaces:**
- Produces: 可在无 API 服务时独立执行的 `frontend` 生产构建和六页路由入口。
- Source identity: Sites project `appgprj_6a603dbc97408191ae68ca4e0aa2e74d`, version 2, commit `b54f8ff76604c80b0974ab4d8a62a2804ce14095`。

- [ ] **Step 1: 写来源完整性测试**

```ts
it("contains the six design routes and the pinned Sites source identity", () => {
  expect(readManifest().sitesVersion).toBe(2);
  expect(readManifest().sourceCommit).toBe("b54f8ff76604c80b0974ab4d8a62a2804ce14095");
  expect(readManifest().routes).toEqual([
    "/workspace", "/analysis", "/workflow", "/market", "/report", "/history",
  ]);
});
```

- [ ] **Step 2: 运行测试确认源码尚未落地时失败**

Run: `npm test -- source-integrity`

Expected: FAIL because `frontend/` and its source manifest do not yet exist. This failure is the required precondition; do not replace the test with a guessed UI.

- [ ] **Step 3: 从 Sites 版本 2 的归档落地原始源码**

Use the Sites project/version artifact identified by:

```text
project_id = appgprj_6a603dbc97408191ae68ca4e0aa2e74d
version_id = appgprj_6a603dbc97408191ae68ca4e0aa2e74d~appgver_c670f308fda0819184310a362f5a2668
archive_format = tar
sediment_file_id = file_0000000030fc81f8931dd65c4b951bae
```

Extract the archive into `frontend/`, preserve its source files and package manager, and add a small `frontend/sites-source.json` manifest containing the exact project ID, version number, source commit, and six route paths. Do not copy the old GitHub ZIP as a substitute; it contains no independent Web frontend.

- [ ] **Step 4: Run the source test and production build**

Run: `npm test -- source-integrity` and the exact build script from the landed `frontend/package.json`.

Expected: source test passes; production build creates `frontend/dist` (or the toolchain's documented output) with no API data required.

- [ ] **Step 5: Commit the source checkpoint**

```bash
git add frontend
git commit -m "feat: land Sites v2 web frontend source"
```

**Checkpoint 1:** source identity, six routes, dependency installation and production build all pass.

---

### Task 2: Add the typed API client and route state

**Files:**
- Create: `frontend/src/lib/models.*`
- Create: `frontend/src/lib/api-client.*`
- Modify: `frontend/src/router.*`
- Test: `frontend/tests/api-client.test.*`, `frontend/tests/router.test.*`

**Interfaces:**
- `createApiClient(baseUrl = "/api/v1"): ApiClient`
- `ApiClient.health(): Promise<HealthResponse>`
- `ApiClient.taskTypes(): Promise<TaskType[]>`
- `ApiClient.createRun(request: CreateRunRequest): Promise<AcceptedRun>`
- `ApiClient.listRuns(filters): Promise<RunPage>`
- `ApiClient.getRun(runId): Promise<Run>`
- `ApiClient.getNodes(runId): Promise<NodePage>`
- `ApiClient.getReport(runId): Promise<Report>`
- `ApiClient.getMarketBars(query): Promise<MarketBars>`
- `ApiClientError { code: string; message: string; retryable: boolean; status: number }`

- [ ] **Step 1: Write failing client tests**

```ts
it("uses the same-origin versioned API and preserves retry metadata", async () => {
  server.get("/api/v1/analysis-runs/run-1/report", {
    status: 409,
    body: { error: { code: "REPORT_NOT_READY", message: "Analysis report is not ready", retryable: true } },
  });
  await expect(api.getReport("run-1")).rejects.toMatchObject({
    code: "REPORT_NOT_READY", retryable: true, status: 409,
  });
});
```

- [ ] **Step 2: Run client tests and verify the missing-client failure**

Run: `npm test -- api-client`

Expected: FAIL because the typed client and error class do not exist.

- [ ] **Step 3: Implement the client against the existing FastAPI schemas**

Use `fetch`, parse the `ErrorEnvelope`, reject non-2xx responses with `ApiClientError`, and never include a database URL or password in browser code. Keep the base path `/api/v1` configurable only for tests and the development proxy.

- [ ] **Step 4: Add route state with URL restoration**

Map exactly `/workspace`, `/analysis`, `/workflow`, `/market`, `/report`, `/history`. Preserve `runId` in query/path state so refreshing a report or workflow page restores its context.

- [ ] **Step 5: Run focused tests and commit**

Run: `npm test -- api-client router`

Expected: PASS with no mocked production fallback data.

```bash
git add frontend/src/lib frontend/src/router* frontend/tests
git commit -m "feat: add typed API client and web routes"
```

**Checkpoint 2:** client errors, retry flags, same-origin base path and six route restoration pass.

---

### Task 3: Replace page mock data with real API adapters

**Files:**
- Modify: `frontend/src/pages/workspace.*`
- Modify: `frontend/src/pages/analysis.*`
- Modify: `frontend/src/pages/workflow.*`
- Modify: `frontend/src/pages/market.*`
- Modify: `frontend/src/pages/report.*`
- Modify: `frontend/src/pages/history.*`
- Create: `frontend/src/lib/page-adapters.*`
- Test: `frontend/tests/pages/*.test.*`

**Interfaces:**
- `loadWorkspace(api): Promise<WorkspaceModel>`
- `loadAnalysisCatalog(api): Promise<AnalysisCatalogModel>`
- `loadWorkflow(api, runId): Promise<WorkflowModel>`
- `loadMarket(api, query): Promise<MarketModel>`
- `loadReport(api, runId): Promise<ReportModel>`
- `loadHistory(api, filters): Promise<HistoryModel>`

- [ ] **Step 1: Write one failing adapter test per page**

Each test must assert that a fixture matching the existing FastAPI response becomes the exact props expected by the unchanged Sites component. Include empty list, loading, retryable error and terminal error cases.

- [ ] **Step 2: Run page tests and verify they fail before adapters exist**

Run: `npm test -- pages`

Expected: FAIL on missing adapter exports or missing real-data mapping.

- [ ] **Step 3: Implement adapters without changing the visual component tree**

Map `RunListResponse`, `RunResponse`, `NodeListResponse`, `ReportResponse`, `MarketBarsResponse`, and `TaskTypeResponse` to existing component props. Keep Chinese copy and original interaction labels from Sites V2.

- [ ] **Step 4: Add explicit UI states**

Use the original page layout to show loading, no-data, API unavailable, report-not-ready, storage unavailable and retry states. Do not expose database URLs, passwords or Python tracebacks.

- [ ] **Step 5: Run focused page tests and commit**

Run: `npm test -- pages`; Expected: PASS.

```bash
git add frontend/src/pages frontend/src/lib/page-adapters* frontend/tests/pages
git commit -m "feat: connect Sites pages to real API data"
```

**Checkpoint 3:** all six pages render real API-shaped data and all required states without visual redesign.

---

### Task 4: Add FastAPI static hosting and SPA fallback

**Files:**
- Modify: `src/diagram_langgraph_pipeline/api/app.py`
- Create: `tests/api/test_static_frontend.py`
- Create: `scripts/start_web.ps1`
- Modify: `.env.example` for `DLP_FRONTEND_DIST`

**Interfaces:**
- `create_app(..., frontend_dist: str | Path | None = None)` uses the explicit argument first, then `DLP_FRONTEND_DIST`, then no-static mode for tests.
- API routes remain under `/api/v1` and are registered before the SPA fallback.

- [ ] **Step 1: Write failing hosting tests**

```python
def test_root_serves_frontend_and_api_prefix_stays_json(tmp_path):
    (tmp_path / "index.html").write_text("<html>sites-v2</html>", encoding="utf-8")
    app = create_app(repository=FakeRepository(), job_service=FakeJobs(), settings={}, frontend_dist=tmp_path)
    client = TestClient(app)
    assert client.get("/").text == "<html>sites-v2</html>"
    assert client.get("/api/v1/health").headers["content-type"].startswith("application/json")
```

- [ ] **Step 2: Run the hosting test and verify it fails**

Run: `pytest tests/api/test_static_frontend.py -v`

Expected: FAIL because `create_app` has no static directory parameter or root route.

- [ ] **Step 3: Implement static hosting after API registration**

Mount existing assets when the configured directory exists. Add an HTML fallback for non-API paths, but return the existing JSON 404 behavior for unknown `/api/v1` paths. Keep no-static mode so current API tests remain deterministic.

- [ ] **Step 4: Add the single-address startup script**

The script must build the frontend, set `DLP_FRONTEND_DIST`, and start `uvicorn diagram_langgraph_pipeline.api.app:create_app --factory --host 127.0.0.1 --port 8000`. It must not print or modify `DATABASE_URL`.

- [ ] **Step 5: Run API tests and commit**

Run: `pytest tests/api/test_static_frontend.py tests/api -q`; Expected: PASS.

```bash
git add src/diagram_langgraph_pipeline/api/app.py tests/api/test_static_frontend.py scripts/start_web.ps1 .env.example
git commit -m "feat: serve frontend from FastAPI"
```

**Checkpoint 4:** root/static assets, client-route fallback and API JSON precedence pass.

---

### Task 5: Add development proxy, production build verification and visual route smoke tests

**Files:**
- Modify: `frontend/package.json` and the landed toolchain config
- Create: `frontend/tests/smoke/six-routes.test.*`
- Create: `tests/e2e/test_frontend_api_smoke.py` if the project already has an E2E runner
- Modify: `README.md`

- [ ] **Step 1: Write failing route smoke tests**

Assert each of the six routes renders its original page heading, no page issues a direct PostgreSQL request, and every API request starts with `/api/v1`.

- [ ] **Step 2: Run smoke tests and confirm missing proxy/route wiring fails**

Run: the exact frontend test command from `frontend/package.json`.

Expected: FAIL only on missing proxy or page wiring, not on unrelated Python tests.

- [ ] **Step 3: Configure development proxy and browser API base**

Proxy `/api/v1` to `http://127.0.0.1:8000`; keep the browser base path same-origin. Add a concise development command for the frontend and API.

- [ ] **Step 4: Run build and all tests**

Run:

```powershell
npm run build --prefix frontend
pytest -q -p no:cacheprovider --basetemp=.pytest-tmp\web-final
```

Expected: frontend production build succeeds and all existing Python tests pass; the only permitted warning is the already-known Starlette/httpx deprecation warning.

- [ ] **Step 5: Commit the integration verification checkpoint**

```bash
git add frontend README.md tests/e2e
git commit -m "test: verify six-page web integration"
```

**Checkpoint 5:** production build and route/API smoke tests pass.

---

### Task 6: Real PostgreSQL single-address acceptance

**Files:**
- Modify: `README.md` with the verified Windows startup steps
- Create: `docs/verification/2026-08-12-sites-v2-postgres-acceptance.md`

- [ ] **Step 1: Verify environment without printing secrets**

```powershell
if (-not $env:DATABASE_URL) { throw "DATABASE_URL 未配置" }
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m diagram_langgraph_pipeline init
```

Expected: database connected and migrations report up to date. Do not paste the connection string into logs or documentation.

- [ ] **Step 2: Build and start the single-address server**

```powershell
npm run build --prefix frontend
$env:DLP_FRONTEND_DIST = "$PWD\frontend\dist"
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m uvicorn diagram_langgraph_pipeline.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

- [ ] **Step 3: Verify health and root response**

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-WebRequest http://127.0.0.1:8000/ | Select-Object -ExpandProperty StatusCode
```

Expected: health returns `service=ok, storage=ok`; root returns HTTP 200 and Sites V2 HTML.

- [ ] **Step 4: Trace one real run through all six views**

Create one permitted analysis from the original form, record its `run_id`, then verify the same ID appears in workspace/history, workflow nodes update, report becomes available or clearly reports not-ready, and market view uses the API response. Do not claim success if an external provider is unavailable; record the specific unavailable state.

- [ ] **Step 5: Record and commit acceptance evidence**

```bash
git add README.md docs/verification/2026-08-12-sites-v2-postgres-acceptance.md
git commit -m "docs: record Sites v2 PostgreSQL acceptance"
```

**Checkpoint 6:** one FastAPI address serves the original six-page frontend backed by the configured PostgreSQL database.

---

## Self-review

- Spec coverage: source identity and extraction are Task 1; API contract and route state are Task 2; six page data/state behavior is Task 3; static hosting and SPA fallback are Task 4; build and visual/API smoke tests are Task 5; real PostgreSQL acceptance is Task 6.
- No implementation begins before Sites source is actually present and the source-integrity test fails as specified.
- Every later task consumes named interfaces from earlier tasks.
- No task authorizes replacing the Sites V2 visual tree with Streamlit widgets or invented mock finance data.
- The existing Streamlit entry point remains untouched except for future cleanup explicitly approved outside this plan.
