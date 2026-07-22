# Diagram LangGraph Pipeline

这是一个按研究流程示意图构建的独立股票研究 LangGraph 流水线。行业、个股、市场和综合决策节点分别实现，并最终生成 Markdown 研究报告。系统只提供研究辅助判断，不执行自动交易。

## 目录

```text
.
├── src/diagram_langgraph_pipeline/
│   ├── agents/              # 一个 LangGraph 节点一个文件
│   ├── analysis/            # 股市指标纯函数
│   ├── providers/           # 行情、研究资料和持久化适配器
│   ├── graph.py             # StateGraph 节点与边
│   └── state.py             # TypedDict State
├── database/
│   ├── schema.sql           # PostgreSQL DDL
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

真实部署还应为研报、政策、公告和情绪资料实现 `ResearchDataProvider`，并为 PostgreSQL 实现 `AnalysisRepository`。默认实现适合离线测试，不会写数据库。

## 数据库设计

数据库定义位于 `database/schema.sql`，实体关系图位于 `database/relationships.md`。决策、节点运行记录、证据和最终报告均可通过 `run_id` 追溯。

## 声明

本项目输出不构成投资建议。公开仓库暂未附带开源许可证，默认保留全部权利。
