# 前端页面与接入文件审核清单

## 1. 页面使用说明

当前前端入口为 `frontend/public/trading-analysis-ui-design.html`，通过同源 FastAPI `/api/v1` 访问后端，浏览器不直接连接 PostgreSQL。

### 研究工作台

查看最近任务、任务数量和当前研究入口。数据来自 `GET /api/v1/analysis-runs`。

### 新建分析

填写证券代码、行业、分析日期和投资周期，点击“启动研究”创建任务。提交接口为 `POST /api/v1/analysis-runs`，返回 `run_id` 后自动进入运行任务页。

### 运行任务

查看任务和节点状态。页面请求 `GET /api/v1/analysis-runs/{run_id}` 与 `GET /api/v1/analysis-runs/{run_id}/nodes`。节点状态包括等待、运行中、完成、降级和失败；运行中的任务会自动轮询。节点卡片底部进度条使用状态颜色显示进度，失败节点显示 `error_summary`。

### 行情视图

按证券代码读取行情缓存，调用 `GET /api/v1/market-bars?ticker=...`。当前显示行情是否存在及记录数量，完整 K 线和技术指标图表仍是后续增强项。

### 研究报告

进入页面后读取当前任务的 `run_id`，调用 `GET /api/v1/analysis-runs/{run_id}/report` 展示 Markdown，并支持下载 `.md` 文件。任务仍在运行时可能返回 `REPORT_NOT_READY`；任务完成或降级后应能读取报告。

### 历史记录

读取 PostgreSQL 中的历史任务，调用 `GET /api/v1/analysis-runs?limit=20`。从记录进入运行任务或报告时会保留对应 `run_id`。

## 2. 后端接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/health` | API 与 PostgreSQL 健康检查 |
| GET | `/api/v1/task-types` | 查询任务类型配置 |
| POST | `/api/v1/analysis-runs` | 创建研究任务 |
| GET | `/api/v1/analysis-runs` | 查询历史任务 |
| GET | `/api/v1/analysis-runs/{run_id}` | 查询任务状态 |
| GET | `/api/v1/analysis-runs/{run_id}/nodes` | 查询节点状态 |
| GET | `/api/v1/analysis-runs/{run_id}/report` | 获取 Markdown 报告 |
| GET | `/api/v1/market-bars` | 获取行情记录 |

## 3. 本批额外生成或修改文件

### 页面与接口接入

- `frontend/public/trading-analysis-ui-design.html`：Sites 页面、路由、任务状态、进度条、报告读取和下载。
- `frontend/public/api-client.mjs`：同源 FastAPI 客户端和错误处理。
- `frontend/public/router.mjs`：六个页面的 URL 路由和 `run_id` 保留。
- `frontend/tests/page-integration.test.mjs`：页面接口接入、进度条和报告导航测试。

### 服务启动与静态托管

- `scripts/start_web.ps1`：构建 Vinext 前端并启动 FastAPI；自动寻找共享虚拟环境。
- `src/diagram_langgraph_pipeline/api/app.py`：FastAPI 静态托管 Sites 构建结果，并保证 `/api/v1` 优先返回 API。
- `.env.example`：增加 `DLP_FRONTEND_DIST` 等 Web 配置示例。

### 数据库迁移与测试

- `database/migrations/005_degraded_node_runs.sql`：允许可选节点使用 `degraded` 或 `skipped` 状态。
- `tests/test_database_migration.py`：验证新增迁移内容。
- `tests/api/test_app.py`：验证静态页面和 API 路由优先级。

### 文档与验收记录

- `docs/verification/2026-08-12-sites-v2-postgres-acceptance.md`：Sites、FastAPI 和 PostgreSQL 现场验收记录。
- `docs/frontend-pages-and-files.md`：本审核清单。

## 4. 不应提交的构建或本地文件

以下属于本地依赖、构建产物或运行缓存，不作为人工源码提交：

- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/.wrangler/`
- `frontend/.vinext/`
- `frontend/build/` 中仅用于构建生成的临时产物
- `.env.local`、数据库密码、模型 API Key 和代理配置

## 5. 当前审核结论

- 页面与 FastAPI Router 已连接。
- 任务、节点、行情和报告接口已连接 PostgreSQL 数据层。
- 报告接口已验证可返回 Markdown；前端需要使用带 `run_id` 的任务上下文。
- 大模型适配器已存在，但没有配置真实 API Key 时不会调用外部模型。
- 行情图表、报告结构化卡片和任务重试仍属于后续增强项。
