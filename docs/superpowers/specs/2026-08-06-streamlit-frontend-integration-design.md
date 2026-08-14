# Streamlit 前端接入设计

## 1. 背景与目标

当前 Task Router 基线提交 `c6483db` 已实现 `full`、`industry`、`fundamental`、`technical` 和 `market` 五种显式研究任务，并通过统一执行计划控制节点范围、输入要求、结果范围和 Review 规则。

本次工作从 Router 最新提交建立独立的 `feature/frontend-integration` 工作树，接入 `Sandy230606/agent-project` 仓库中 `trading_agent_learn_frontend_backend_bundle.zip` 的 Streamlit 前端。只复用 ZIP 中的页面、样式、前端模型和 Gateway 思路，不引入其中的 `multiple_agent_finance` Agent、Graph、Service 或存储实现。

交付目标：

- 保留研究工作台、新建分析、运行任务、行情视图、研究报告和历史记录六个页面；
- 前端通过 FastAPI 异步任务接口调用现有 Task Router；
- PostgreSQL 是任务状态、历史、节点进度和报告的权威存储；
- 五种任务均能从页面提交并准确显示执行范围；
- 保持系统仅用于研究分析，不执行交易。

## 2. 选定方案

采用适配器式迁移：将可复用前端迁入 `diagram_langgraph_pipeline.ui`，重新实现 HTTP Gateway 和 FastAPI 后端，使其调用现有 `run_analysis`、Task Router、Provider 与 PostgreSQL Repository。

不保留 `multiple_agent_finance` 包名兼容层，也不重新实现一套分析图。Router 是任务枚举、节点范围、必填输入、结果字段和结论范围的唯一权威来源。

## 3. 总体架构

```text
Streamlit 六页面
    ↓ HTTP/JSON
FastAPI /api/v1
    ↓ 有界异步任务服务
现有 run_analysis + Task Router
    ↓
PostgreSQL + Provider + LangGraph
```

### 3.1 前端模块

`diagram_langgraph_pipeline.ui` 包含：

- `pages/`：六个页面；
- `gateway.py`：前端依赖的稳定协议；
- `api_gateway.py`：HTTP 实现；
- `models.py`：纯前端请求和显示模型；
- `state.py`：Streamlit 会话状态与导航；
- `components.py`、`styles.py`：复用并修正 ZIP 的终端风格组件；
- `streamlit_app.py`：应用入口。

Streamlit 不直接导入 `runner`、`graph`、`service` 或数据库 Repository。

### 3.2 API 模块

`diagram_langgraph_pipeline.api` 包含：

- `app.py`：FastAPI 应用工厂与生命周期；
- `routes.py`：版本化 `/api/v1` 路由；
- `schemas.py`：请求、响应和错误契约；
- `errors.py`：异常到 HTTP 的稳定映射；
- `jobs.py`：有界任务队列、状态转换和启动恢复。

API Schema 直接使用或投影现有 `TaskType` 与 `TaskExecutionPlan`，不维护第二套任务枚举或节点清单。

### 3.3 异步任务服务

提交任务时由 API 生成 `run_id`，先写入 PostgreSQL，再将同一个标识传给分析服务。`RunOptions` 或等价的应用服务输入增加可选的调用方 `run_id`，命令行未提供时仍保持现有自动生成行为。

任务队列默认只并发执行一个分析任务，可通过明确的环境变量调整上限。队列存在于 FastAPI 进程内，PostgreSQL 保存权威状态。服务重启时，遗留的 `pending` 或 `running` 任务被标记为 `interrupted`；本阶段不自动续跑，也不提供运行中取消。

## 4. 页面设计与数据流

### 4.1 研究工作台

展示近期任务数量、各状态数量、失败或降级数量及最新报告。数据来自 PostgreSQL 聚合查询，不从 Streamlit 会话推导历史。

### 4.2 新建分析

页面首先调用 `GET /api/v1/task-types`，读取五种任务的名称、说明、必填字段、节点分类和结论范围。

当前 Router 的真实输入规则是：

- 五种任务都必须填写真实证券代码和分析日期；
- `full`、`industry`、`fundamental` 显示投资周期；
- 行业名称允许留空，由证券元数据推导；用户填写时作为明确覆盖值；
- 报告窗口、技术窗口、离线模式、强制刷新、LLM 和付费数据授权放入高级选项。

付费数据授权只有在服务端明确允许时才显示。提交 `POST /api/v1/analysis-runs` 后立即返回 `202`、`run_id` 和轮询地址。

### 4.3 运行任务

页面轮询任务状态与节点事件。节点按 Router 的 `required`、`support`、`optional` 和 `skipped` 分类显示；主动屏蔽的节点不得显示为失败或数据缺失。

完成后跳转研究报告。失败时展示安全错误摘要和重新创建任务入口，不展示服务端堆栈或凭据。

### 4.4 行情视图

通过数据库优先的行情接口读取历史 K 线、成交量和现有技术指标。页面只负责展示，不复制技术指标算法。

### 4.5 研究报告

从 PostgreSQL `final_reports` 读取 Markdown，同时展示任务范围、Review、数据缺口、可选节点降级项和 Token 使用。支持从数据库内容生成 Markdown 下载响应，不接受任意服务器文件路径。

### 4.6 历史记录

从 `analysis_runs` 分页查询，支持按证券代码、任务类型、状态和日期筛选。用户可以重新打开任务进度或已完成报告。

## 5. API 契约

首期接口：

- `GET /api/v1/health`
- `GET /api/v1/task-types`
- `POST /api/v1/analysis-runs`
- `GET /api/v1/analysis-runs`
- `GET /api/v1/analysis-runs/{run_id}`
- `GET /api/v1/analysis-runs/{run_id}/nodes`
- `GET /api/v1/analysis-runs/{run_id}/report`
- `GET /api/v1/market/{ticker}/bars`

分析状态为：

```text
pending -> running -> completed
                  |-> degraded
                  `-> failed
```

HTTP `202 Accepted` 表示任务已经持久化并进入 `pending`，`submitted` 不是数据库状态。

`interrupted` 用于服务启动恢复时标记未正常结束的旧任务。`degraded` 表示任务完成但存在允许的可选节点降级，不等同于失败。

任务类型元数据接口公开展示所需的 Router 投影，不暴露凭据、内部异常或敏感 Provider 配置。

## 6. PostgreSQL 设计

继续复用 `analysis_runs`、`node_runs`、`final_reports`、行情与领域结果表。新增迁移只补充 API 查询和生命周期所需的字段与索引，包括：

- `analysis_runs.task_type`；
- 可区分 `pending`、`running`、`completed`、`degraded`、`failed`、`interrupted` 的状态约束；
- 安全错误代码与错误摘要；
- 按任务类型、状态、证券代码和创建时间查询历史所需的索引。

迁移必须可重复执行，并兼容已有分析记录。Repository 增加窄接口用于创建任务、更新状态、分页列表、查询节点进度和读取报告，不把 SQL 放入 API 路由或 Streamlit 页面。

## 7. 错误处理与安全

- 输入不合法：HTTP `422`，且必须在 Provider 调用前拒绝；
- 任务不存在：HTTP `404`；
- 节点或报告尚未就绪：HTTP `409`，并标记可重试；
- PostgreSQL 不可用：HTTP `503`，不启动分析；
- Provider 数据不足：记录数据缺口或允许的降级；
- 程序错误：任务标为 `failed`，API 只返回安全摘要，完整堆栈进入服务日志；
- 服务重启：遗留任务标为 `interrupted`。

数据库密码、LLM Key 和 Provider 凭据只从服务端环境变量读取，不进入 API 响应、LangGraph State 或浏览器会话。CORS 默认只允许本机 Streamlit 地址，扩展来源必须显式配置。

## 8. 启动与配置

FastAPI 与 Streamlit 分别提供 PowerShell 启动脚本。可增加一个开发脚本同时启动两个隐藏子进程，但两者仍是独立服务，生产部署不依赖该脚本。

新增依赖按用途拆分到可选依赖组，例如 `web` 包含 FastAPI、Uvicorn、Streamlit 与页面图表依赖；核心 CLI 用户不安装 `web` 时仍可运行现有功能。

前端通过 `DLP_API_BASE_URL` 配置 API 地址。数据库和 Provider 配置继续复用现有环境变量，不新增浏览器端密钥配置。

## 9. 测试策略

### 9.1 Router 回归

保留现有五种任务、图结构和任务范围测试，确保前端接入不改变 Router 行为。

### 9.2 API 契约

覆盖任务类型元数据、任务提交、轮询、历史、节点、行情和报告接口，以及 `404`、`409`、`422`、`503` 和错误脱敏。

### 9.3 异步任务

用伪分析执行器验证状态变化、事件写入、失败记录、同一 `run_id` 传播和服务重启后的中断处理。

### 9.4 PostgreSQL

验证迁移可重复执行，任务筛选、分页、节点进度和报告读取正确。数据库集成测试仅在提供测试 DSN 时运行，其余测试不依赖真实数据库。

### 9.5 Streamlit

迁移 ZIP 中可复用的页面测试，使用伪 Gateway 验证六页导航、五种任务表单、动态字段、轮询、行情和报告渲染。前端测试不得调用真实网络、数据库或 LLM。

### 9.6 端到端与冒烟

离线伪数据端到端测试覆盖五种任务各一次。FastAPI 与 Streamlit 启动入口均执行冒烟测试。

## 10. 验收标准

- 现有 132 项测试继续通过，并增加 API、数据库和 UI 测试；
- 六个页面均可访问，界面保留 ZIP 的终端风格并修复其中的中文乱码；
- 仓库中没有对旧 `multiple_agent_finance` 后端的运行时依赖；
- 五种任务都能从页面提交，并按 Router 范围显示节点进度；
- 服务重启后仍能查看历史记录和已完成报告；
- 主动屏蔽、数据缺失、可选降级、任务失败和服务中断在 UI 中明确区分；
- FastAPI 与 Streamlit 启动脚本通过冒烟测试；
- 系统不连接券商，也不提供交易执行能力。

## 11. 非目标

- 不引入 ZIP 中的旧 Agent、Graph、Service 或存储实现；
- 不实现用户登录、权限系统或多租户；
- 不实现 WebSocket、Server-Sent Events 或运行中取消；
- 不实现服务重启后的任务自动续跑；
- 不改变 Task Router 的五种任务定义和研究规则；
- 不新增交易执行能力。
