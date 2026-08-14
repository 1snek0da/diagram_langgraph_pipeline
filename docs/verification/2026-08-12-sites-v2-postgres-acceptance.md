# Sites V2 + PostgreSQL 现场验收

## 验收结果

- PostgreSQL：连接成功，数据库 `diagram_langgraph_pipeline`，端口 `5432`。
- 迁移：已是最新状态，无缺失迁移。
- 前端构建：Sites V2 `vinext build` 成功。
- FastAPI 健康检查：`GET /api/v1/health` 返回 `200`，内容为 `service=ok, storage=ok`。
- 根页面：`GET /` 返回 `200 text/html`，内容为原始智能投研终端。
- 客户端路由：`GET /report?run_id=现场验证` 返回 `200 text/html`，页面入口正常回退。
- API 优先级：`/api/v1/health` 仍返回 JSON，没有被前端回退路由拦截。

## 现场命令

以下命令依赖本机已配置的 `.env.local`；验收记录不保存连接串或密码：

```powershell
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m diagram_langgraph_pipeline init

Push-Location frontend
$env:WRANGLER_LOG_PATH = '.wrangler/wrangler.log'
.\node_modules\.bin\vinext.cmd build
Pop-Location

$env:DLP_FRONTEND_DIST = "$PWD\frontend\dist"
$env:PYTHONPATH = "$PWD\src"
D:\diagram_langgraph_pipeline\.venv\Scripts\python.exe -m uvicorn `
  diagram_langgraph_pipeline.api.app:create_app `
  --factory --host 127.0.0.1 --port 8000
```

## 说明

Vinext 的生产输出入口位于 `frontend/dist/client/trading-analysis-ui-design.html`，FastAPI 已兼容该目录结构；不应把 `frontend/dist` 误认为必须包含根级 `index.html`。
