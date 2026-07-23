# 项目协作记忆

## 项目定位

本仓库是从父工作区 `trading_agent_learn` 独立出来的
`diagram_langgraph_pipeline` 项目。它依据原始研究流程示意图构建股票研究
LangGraph，输出可追溯的 Markdown 研究报告。

- 系统只提供研究辅助判断，不自动下单，也不让 LLM 直接控制券商接口。
- 当前主线是日线级行业、个股、市场研究；高频盘口、订单执行、做市和强化学习
  均属于未来可选子系统。
- 输入至少包含 `ticker` 和 `industry_name`。
- 公开仓库未添加 LICENSE，默认保留全部权利。

更完整的历史决策、研究结论和路线图见 `docs/PROJECT_MEMORY.md`。

## 当前架构

- 源码采用 `src/` 布局，包名为 `diagram_langgraph_pipeline`。
- 每个 LangGraph 节点独立放在一个 `agents/*_agent.py` 文件中。
- `graph.py` 只负责图装配、依赖注入和统一节点审计，不应承载具体研究逻辑。
- `analysis/` 保存可测试的纯指标计算；`providers/` 保存行情、研究资料和持久化适配器。
- State 的权威定义是 `state.py`，实施目标和决策规则的权威说明是 `PLAN.md`。
- PostgreSQL DDL 和关系图分别位于 `database/schema.sql` 与
  `database/relationships.md`。

主流程：

```text
Planner
├─ Industry: report -> capex + policy -> future capex forecast -> valuation
├─ Stock: market fetch -> analysis -> technical
│         business -> forecast + marginal change -> valuation
└─ Market: index + sector technical + sentiment
        -> Research Join -> Decision -> Review
        -> retry Planner 或 Report -> END
```

研究资料已采用 `SourceRequest -> SourceBatch` 类型化契约。事实值使用 `Decimal`，
并区分 `reported`、`extracted`、`estimated`、`derived`；网络和商业来源均为
可插拔 Adapter，默认离线运行。行业需求侧只汇总 Alphabet、Amazon、Microsoft、
Meta、Oracle，NVIDIA 单列为供应侧指标；通信 CapEx 缺失时必须保持空值。

## 不可破坏的产品约束

- 保留行业、个股、市场三条并行研究分支及多前驱汇合语义。
- Reflection 发现资料不足时可回到 Planner，但必须受 `max_retries` 限制。
- 证据不足或行情覆盖不足时，不允许输出高置信度买入或卖出结论。
- 强势但高估值、正向边际变化但技术高位、弱大盘等冲突必须在决策中降级或说明。
- 最终报告必须披露风险、失效条件、证据引用、数据缺口和 Review 结果。
- 新研究模型只能作为受监控的量化信号，不能绕过综合决策和风险约束。

## 开发与验证

在仓库根目录使用：

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m diagram_langgraph_pipeline
diagram-langgraph-pipeline
```

截至 2026-07-23，项目 `.venv` 中的本地基线为 `23 passed`。系统 Python 若未执行
editable 安装，会因 `src/` 包不可见而在测试收集阶段失败；此时应先安装项目，或
使用 `.\.venv\Scripts\python.exe -m pytest -q`。修改图结构、State、指标、决策
规则或 Review 路由时，至少运行完整测试集；修改 CLI 或打包配置时，还应运行两个
入口的冒烟测试。

## 文档优先级

出现冲突时按以下顺序判断当前事实：

1. 当前代码与测试；
2. `PLAN.md`、`database/schema.sql`；
3. `docs/PROJECT_MEMORY.md` 中的“已实现基线”；
4. 项目记忆中的研究建议与历史记录。

研究建议不代表已经实现。尤其不要把 DDG-DA、TRA、Level-2/OFI、Siamese
网络、SAC 做市或实时 Broker 层描述成现有能力。
