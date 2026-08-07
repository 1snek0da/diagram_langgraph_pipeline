# Diagram LangGraph Pipeline

这是一个按研究流程示意图构建的独立股票研究 LangGraph 流水线。行业、个股、市场和综合决策节点分别实现，并最终生成 Markdown 研究报告。系统只提供研究辅助判断，不执行自动交易。

## 目录

```text
.
├── src/diagram_langgraph_pipeline/
│   ├── agents/              # 一个 LangGraph 节点一个文件
│   ├── analysis/            # 股市指标纯函数
│   ├── providers/           # 行情、研究资料和持久化适配器
│   ├── schemas/             # Pydantic v2 来源、事实、证据与覆盖度契约
│   ├── graph.py             # StateGraph 节点与边
│   └── state.py             # TypedDict State
├── database/
│   ├── schema.sql           # PostgreSQL DDL
│   ├── migrations/          # 现有数据库增量迁移
│   └── relationships.md     # Mermaid ER 图
├── tests/
├── PLAN.md                  # 详细实施计划
└── pyproject.toml           # 打包、依赖与测试配置
```

## 安装与验证

需要 Python 3.10 或更高版本。在仓库根目录执行：

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m diagram_langgraph_pipeline
```

安装后也可以使用命令行入口：

```powershell
diagram-langgraph-pipeline
```

## 交互 CLI 与 DB-first 运行

CLI 强制使用 PostgreSQL：先检查数据库，再从缓存读取行情与研究资料，只有覆盖不足或
过期时才调用 Provider。无参数且连接 TTY 时进入循环向导；管道或重定向环境中显示帮助。

```powershell
# 诊断连接并按校验和应用 001–003 迁移
diagram-langgraph-pipeline init

# 完整研究；报告窗口与 MA250 等技术计算窗口相互独立
diagram-langgraph-pipeline run AAPL --report-days 70 --technical-days 251

# 只读检查覆盖，或显式绕过正缓存补采
diagram-langgraph-pipeline data status 0700.HK
diagram-langgraph-pipeline data refresh 600519.SS --technical-days 500

# 可脚本化 JSON；进度只写 stderr
diagram-langgraph-pipeline run AAPL --no-llm --json

# 原有无需数据库、无需网络的演示
diagram-langgraph-pipeline demo
```

### 任务 Router

`run` 通过 `--task` 显式选择研究范围，支持 `full`、`industry`、
`fundamental`、`technical` 和 `market` 五种任务。五种任务都必须提供真实股票代码；
股票代码既用于标识本次研究，也用于读取公司、行业、市场和板块元数据。
`industry_name` 可以通过 `--industry-name` 显式传入，留空时会优先使用该股票的元数据补齐。

```powershell
# 完整研究（省略 --task 时也默认执行 full）
diagram-langgraph-pipeline run AAPL --task full --no-llm

# 行业研究；行业名可省略并从 AAPL 元数据补齐
diagram-langgraph-pipeline run AAPL --task industry --no-llm
diagram-langgraph-pipeline run AAPL --task industry --industry-name 通信 --no-llm

# 个股基本面与估值
diagram-langgraph-pipeline run AAPL --task fundamental --no-llm

# 个股技术面
diagram-langgraph-pipeline run AAPL --task technical --no-llm

# 市场环境；基准和板块可从 AAPL 元数据推断，也可显式指定
diagram-langgraph-pipeline run AAPL --task market --no-llm
diagram-langgraph-pipeline run AAPL --task market --benchmark ^GSPC --sector-index XLK --no-llm
```

只有 `full` 会运行综合决策节点并给出完整买入、持有、观察、减仓或卖出结论；
其余任务只报告所选范围内的研究结果。未选中的节点不会被构建和执行，也不会调用对应的
Provider 或 LLM。基本面任务中的边际变化属于可选节点：获取失败时会记录为
`skipped/degraded` 并继续生成报告，不会伪造数据或阻塞估值。

`--offline` 只读取数据库，`--refresh` 强制补采，两者互斥。免费 Yahoo、SEC、ECB
和官方网页在缺数时可自动调用；检测到 Tushare、CNINFO、Wind 或 iFinD 配置时，向导会
先确认，非交互运行必须显式传入 `--allow-paid`。成功报告默认写入 `outputs/`。
向导运行结束后可选择 `tokens`，检查总 Token、缓存 Token、输入估算偏差及逐节点用量。

### Demo 任务选择

运行 `python -m diagram_langgraph_pipeline demo` 后，使用上、下方向键移动五种 Router 任务的高亮项，按 Enter 确认。Demo 使用固定离线数据，不连接数据库、不访问网络，也不调用 LLM。

## 接入生产数据

生产行情可通过 `YFinanceMarketDataProvider` 接入：

```python
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers.yfinance_market import YFinanceMarketDataProvider
from diagram_langgraph_pipeline.runner import run_research

result = run_research(
    initial_state,
    AgentDependencies(market_data=YFinanceMarketDataProvider()),
)
print(result["final_markdown"])
```

研究资料统一通过 `SourceRequest -> SourceBatch` 接口进入节点。直接使用 Python 工厂时，
默认 Provider 会读取 `research_inputs` 和用户授权的本地报告目录；只有设置
`ENABLE_NETWORK_RESEARCH=1` 后才会启用网络来源。交互 CLI 则按上述 DB-first 策略
自动启用免费来源，因此 CI 和 `demo` 仍可完全离线运行。

当前内置适配器包括：

- SEC EDGAR Company Facts：海外企业已披露总 CapEx。
- ECB：以 EUR 为交叉货币生成可复现的 USD/CNY 日度汇率。
- 国务院、工信部、发改委等官方政策网页白名单。
- Tushare Pro：公司资料、主营构成、业绩预告、新闻线索、估值与行业成分。
- 巨潮授权数据服务：端点和鉴权由环境配置提供，不猜测未公开接口。
- PDF、DOCX、HTML、TXT 授权报告目录；支持同名 `.扩展名.json` sidecar 提供结构化事实与证据。
- Wind 与 iFinD 运行时插件；未安装 SDK 或未配置查询映射时返回明确的不可用状态。

## “输入输出.docx”规则实现

个股研究分支已把文档中可量化、无歧义的规则固化为纯函数和节点输出：

- 日线行情同时计算 MA5、MA10、MA20、MA60、MA120、MA250，并接收可选的当日
  1 分钟 K 线；缺少分钟线时明确披露，历史分析不伪造盘中状态。
- 趋势评分由均线系统 70 分与成交量系统 30 分组成；技术形态评分按突破 K 线
  质量 40% 与当前介入点 60% 合成，再按趋势 70%/形态 30% 形成综合信号。
- 盈利预测先按公司行业地位进行基础修正，再根据半年完成度、利润质量、连续季度
  拐点、产品升级和不及预期类型进行第二次修正。
- 个股估值对每个预测年度输出调整后净利润、最终 PE、合理市值和上下行空间；
  文档阈值信号只作为综合决策输入，不能绕过证据、覆盖度和风险约束。

文档中标记“下面写”或未给出计算标准的内容保持为缺失项，不由系统猜测补全。

所有数值事实保留 `reported`、`extracted`、`estimated` 或 `derived` 口径，
并携带来源、币种、单位、期间和覆盖度。通信 CapEx 没有明确披露时保持空值。
详细字段、时间规则与授权报告 sidecar 示例见
[`docs/research_source_contract.md`](docs/research_source_contract.md)。

### 来源配置

复制 `.env.example` 后按需设置环境变量。凭据只从环境变量读取，不进入 State、
日志或数据库请求快照。

```powershell
$env:ENABLE_NETWORK_RESEARCH = "1"
$env:SEC_USER_AGENT = "research-app contact@example.com"
$env:TUSHARE_TOKEN = "..."
python -m diagram_langgraph_pipeline
```

不设置商业数据凭据仍可安装、测试和运行离线样本。Tushare SDK 单独安装：

```powershell
python -m pip install -e ".[sources]"
```

PostgreSQL 持久化使用可选依赖与 `PostgresAnalysisRepository`；未显式注入时仍使用
无副作用的 `NullRepository`：

```powershell
python -m pip install -e ".[postgres]"
$env:DATABASE_URL = "postgresql://user:password@127.0.0.1:5432/database"
```

实时行情可通过 `market_history_days` 指定自然日窗口；来源证据、行情、节点审计、
技术分析、决策、Review 和最终报告均按 `run_id` 写入 PostgreSQL。

### 可选 LLM 辅助解读

项目支持通过火山引擎方舟或 OpenAI 兼容中转调用 `deepseek-v4-flash`。默认关闭，
启用后模型只总结已经形成的结构化研究结果，不修改规则决策、评分、买卖区间或
Review。官方方舟地址为 `https://ark.cn-beijing.volces.com/api/v3`；中转服务可通过
`VOLCENGINE_LLM_BASE_URL` 覆盖：

```powershell
$env:ENABLE_LLM_ADVISORY = "1"
$env:VOLCENGINE_LLM_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
$env:VOLCENGINE_LLM_API_KEY = "..."
$env:VOLCENGINE_LLM_MODEL = "deepseek-v4-flash"
```

如果方舟控制台要求使用推理接入点 ID，将 `VOLCENGINE_LLM_MODEL` 设置为对应的
`ep-...`，无需修改代码。客户端调用 OpenAI 兼容的 `/chat/completions`，不自动重试
超时请求，避免产生重复推理费用。

## 数据库设计

数据库定义位于 `database/schema.sql`，实体关系图位于 `database/relationships.md`。决策、节点运行记录、证据和最终报告均可通过 `run_id` 追溯。

## D4F 70 日增强配置

在输入 State 中设置 `"run_profile": "d4f_70d"` 会启用 70 个交易日日线、Yahoo `60m`
盘中数据、最多 36 条窗口内新闻，以及 23 个节点的 D4F 辅助分析。模型输入按节点职责投影，
目标不超过 115K Token、硬上限 128K Token；裁剪清单和实际 usage 会写入
`llm_invocations`。现有数据库先执行：

2026-07-31 的 AAPL 实测中，23 个节点累计约 50.2 万输入 Token、4591 输出 Token；
投影器预估约 58.2 万输入 Token。实际用量会随资料正文、新闻长度和 Reflection 重试变化。

```powershell
psql $env:DATABASE_URL -f database/migrations/002_d4f_70d.sql
```

完整 Apple 入口为：

```powershell
.\.venv\Scripts\python.exe scripts\run_live_apple.py
```

## 声明

本项目输出不构成投资建议。公开仓库暂未附带开源许可证，默认保留全部权利。
