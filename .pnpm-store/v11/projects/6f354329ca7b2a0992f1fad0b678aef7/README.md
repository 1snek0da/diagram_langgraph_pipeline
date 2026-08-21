# Sites V2 前端源码

本目录来自 `Trading Analysis UI Design` 的 published-site 源码，固定基准为 Sites 版本 2。

- 项目：`appgprj_6a603dbc97408191ae68ca4e0aa2e74d`
- 源提交：`b54f8ff76604c80b0974ab4d8a62a2804ce14095`
- 页面主体：`public/trading-analysis-ui-design.html`
- Next/Vinext 入口：`app/page.tsx`

当前批次只验证原始源码和构建，不接入 API。后续页面数据统一通过同源 `/api/v1` 请求 FastAPI；浏览器端不得读取 PostgreSQL 凭据。

```powershell
npm.cmd ci
npm.cmd run build
```
