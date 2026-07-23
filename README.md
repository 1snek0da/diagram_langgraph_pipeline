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

研究资料统一通过 `SourceRequest -> SourceBatch` 接口进入节点。默认 Provider 会读取
`research_inputs` 和用户授权的本地报告目录；只有设置 `ENABLE_NETWORK_RESEARCH=1`
后才会启用网络来源，因此 CI 和演示可完全离线运行。

当前内置适配器包括：

- SEC EDGAR Company Facts：海外企业已披露总 CapEx。
- ECB：以 EUR 为交叉货币生成可复现的 USD/CNY 日度汇率。
- 国务院、工信部、发改委等官方政策网页白名单。
- Tushare Pro：公司资料、主营构成、业绩预告、新闻线索、估值与行业成分。
- 巨潮授权数据服务：端点和鉴权由环境配置提供，不猜测未公开接口。
- PDF、DOCX、HTML、TXT 授权报告目录；支持同名 `.扩展名.json` sidecar 提供结构化事实与证据。
- Wind 与 iFinD 运行时插件；未安装 SDK 或未配置查询映射时返回明确的不可用状态。

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

生产环境还需实现 PostgreSQL `AnalysisRepository`；默认仓储无副作用。

## 数据库设计

数据库定义位于 `database/schema.sql`，实体关系图位于 `database/relationships.md`。决策、节点运行记录、证据和最终报告均可通过 `run_id` 追溯。

## 声明

本项目输出不构成投资建议。公开仓库暂未附带开源许可证，默认保留全部权利。
