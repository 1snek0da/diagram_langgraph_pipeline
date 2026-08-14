# Task Router 与命令行显示优化设计

## 1. 背景与目标

当前研究图固定执行行业、个股和市场三条分支。即使用户只需要技术面或行业分析，系统仍会调度全部节点，产生不必要的数据请求、运行时间和 LLM Token 消耗。

本周交付以 Task Router 为主，并完成命令行显示优化。前端网页不在本周范围内。

目标：

- 用户显式选择研究任务，系统不使用 LLM 猜测任务类型。
- 只构建并执行任务需要的节点；屏蔽节点不调度、不访问 Provider、不调用 LLM。
- 汇总、Review 和报告只评价本次任务范围，不把主动屏蔽误判为数据缺失。
- 保持现有 `full` 完整研究行为兼容。
- 命令行清楚显示任务范围、节点进度和最终结果。

## 2. 设计决策

### 2.1 路由方式

采用“任务配置驱动的图构建”，不采用让所有节点启动后自行退出的方式。

Router 模块的外部接口保持简单：

```text
task_type -> TaskExecutionPlan
```

`TaskExecutionPlan` 隐藏节点集合、连接关系、输入规则和结论范围。图构建器消费执行计划，只装配本次需要的节点和边。

Router 不调用 LLM，不解析自然语言，也不根据运行中间结果改变任务类型。Review 重试时必须复用原任务类型和同一执行计划。

### 2.2 任务类型

| 任务代码 | 命令行名称 | 允许输出的结论 |
|---|---|---|
| `full` | 综合研究 | 综合买入、持有、观望、减仓或卖出倾向 |
| `industry` | 行业分析 | 行业景气、资本开支趋势和行业估值结论 |
| `fundamental` | 个股基本面分析 | 盈利预测、合理 PE、市值空间和基本面风险 |
| `technical` | 个股技术面分析 | 趋势、形态、支撑阻力和介入点信号 |
| `market` | 市场整体分析 | 大盘、板块、情绪和风险偏好结论 |

原先讨论的 `stock` 改为 `fundamental`，避免把偏长期的基本面分析与偏短期的技术分析混为一类。

## 3. 执行计划

每份执行计划必须包含：

- `task_type`：任务代码；
- `required_nodes`：失败即导致任务失败的节点；
- `support_nodes`：为必需节点提供数据的辅助节点；
- `optional_nodes`：允许降级或无数据完成的节点；
- `skipped_nodes`：本次主动屏蔽的节点；
- `required_inputs`：本任务必填输入；
- `required_outputs`：Review 必须检查的结果；
- `conclusion_scope`：报告允许表达的结论范围。

### 3.1 `full`

保持当前 23 节点完整图：

```text
planner
├─ industry_entry -> industry_report -> upstream_capex + policy
│                    -> future_capex_forecast -> industry_valuation
├─ stock_entry -> stock_data_fetch -> stock_data_analysis -> stock_technical
│              -> business -> profit_forecast + marginal_change（可选尝试）
│                           -> company_valuation（边际变化跳过后仍可运行）
└─ market_entry -> index_analysis + sector_technical + sentiment
-> research_join -> decision -> review -> report
```

必填输入：股票代码、行业名称、分析日期和投资周期。

只有该任务执行 `decision` 并输出完整综合投资倾向。

### 3.2 `industry`

```text
planner -> industry_entry -> industry_report
        -> upstream_capex + policy
        -> future_capex_forecast -> industry_valuation
        -> research_join -> review -> report
```

必填输入：行业名称、分析日期和投资周期。股票代码不是必填。

上游资本开支与政策影响并行；未来资本开支预测必须等待两者完成。行业估值输出可触达收入、预计净利润、合理市值区间和当前估值位置。不执行 `decision`，不输出个股买卖建议。

### 3.3 `fundamental`

```text
planner -> stock_entry
        -> business -> profit_forecast -----------------> company_valuation
                    -> marginal_change（可选尝试）-------> company_valuation
        -> stock_data_fetch（估值支持）
        -> research_join -> review -> report
```

必填输入：股票代码、分析日期和投资周期。行业名称可由证券元数据补齐。

- `business` 判断业务分类、行业地位、基础 PE 和调整后 PE。
- `profit_forecast` 保留基础修正与精细修正：利润完成度、利润质量、连续季度拐点、产品升级和不及预期原因。
- `stock_data_fetch` 是支持节点，只为估值提供当前价格、市值、PE 和必要业绩数据，不因此启动技术分析。
- `marginal_change` 是可选节点。系统仍尝试执行；资料不存在、Provider 不可用或没有可信结果时，返回结构化的 `skipped` 状态和原因，不阻断任务，也不触发补采重试。若取得可信结果，`company_valuation` 可以将其作为辅助信息。
- `company_valuation` 输出分年度合理市值、上行空间和基本面估值判断。

不执行 `stock_technical`、市场分支或完整 `decision`。

### 3.4 `technical`

```text
planner -> stock_entry -> stock_data_fetch
        -> stock_data_analysis -> stock_technical
        -> research_join -> review -> report
```

必填输入：股票代码和分析日期。

输出均线与成交量评分、震荡区间、突破 K 线质量、第一/第二介入点评分、综合信号、支撑阻力和技术风险。缺少分钟线时必须说明，不得伪造盘中突破状态。

不执行基本面、行业、市场分支或完整 `decision`。

### 3.5 `market`

```text
planner -> market_entry
        -> index_analysis + sector_technical + sentiment
        -> research_join -> review -> report
```

必填输入：分析日期。指数和板块代码允许使用市场默认值。

输出大盘趋势、板块技术形态、市场情绪和风险偏好。不输出单只股票估值或买卖建议。

## 4. State 与运行审计

State 增加：

```text
task_type
required_nodes
support_nodes
optional_nodes
skipped_nodes
completed_nodes
failed_nodes
conclusion_scope
```

节点完成与失败状态由现有统一 `_instrument` 包装器记录。`skipped_nodes` 来自执行计划，不为屏蔽节点伪造开始或完成事件。

主动屏蔽与数据缺失必须区分：

- 未选择行业任务，因此没有 `industry_valuation_result`：主动屏蔽；
- 已选择技术任务，但行情获取为空：数据缺失；
- 主动屏蔽不降低完整性分数、不触发重试；
- 必需节点实际缺失可以在 `max_retries` 范围内补采；
- 可选节点缺失只形成降级说明。

可选节点只能跳过预期的数据可用性问题，例如没有授权来源、Provider 明确不可用、查询结果为空或证据不足。代码缺陷、类型契约错误和状态字段错误必须正常报错，不能用“可选”掩盖程序问题。

## 5. 公共节点调整

### 5.1 Planner

Planner 只生成当前任务的工作项，不再固定生成行业、个股、市场三个任务列表。重试任务不得超出当前执行计划。

### 5.2 Research Join

只汇总 `required_outputs` 和已经产生的可选结果。未启用分支使用“未纳入本次任务范围”表示，不加入 `missing_items`。

### 5.3 Decision

只在 `full` 任务中运行。其他任务由各自末端分析结果形成任务范围内的结论，不生成完整买卖倾向。

### 5.4 Review

Review 按任务类型读取不同的必需结果和阈值。它必须验证：

- 所有必需节点是否完成；
- 必需数据覆盖是否满足要求；
- 结论是否超出 `conclusion_scope`；
- 是否把主动屏蔽内容误报为缺失；
- 重试任务是否仍位于原执行计划内。

### 5.5 Report

报告只渲染当前任务相关章节，并新增“任务执行范围”：

- 任务类型；
- 运行的必需、支持和可选节点；
- 主动屏蔽节点；
- 实际完成与失败节点；
- 结论适用范围；
- 数据缺口与降级情况。

## 6. 命令行显示优化

本周选择命令行显示优化，不接前端网页。

### 6.1 非交互命令

`run` 增加：

```text
--task full|industry|fundamental|technical|market
```

未传入时默认 `full`，保持现有脚本兼容。非法值由 Typer 拒绝并列出合法选项。

### 6.2 交互向导

运行前显示五种任务的中文名称和一句话说明，用户必须明确选择。选择完成后先展示执行摘要，再确认开始。

### 6.3 运行进度

使用 Rich 显示：

- 当前任务类型；
- 已完成节点数 / 计划节点数；
- 当前执行节点；
- Provider 缓存命中、接口补采或降级状态；
- 完成、失败和可选降级使用不同状态样式。

屏蔽节点只在执行摘要和最终结果中列出，不逐个显示为运行事件。

### 6.4 最终摘要

完成后显示报告路径、任务范围、节点完成数、降级项、数据缺口、结论摘要和 Token 用量。`--json` 输出相同信息的稳定字段，进度仍只写入 stderr。

## 7. 错误处理

- 未指定 `--task`：使用 `full`。
- 非法任务类型：退出码 2，并显示五个合法值。
- 缺少当前任务必填输入：在构建图和访问 Provider 前失败。
- 必需节点失败：记录失败节点并终止本次任务。
- 支持节点失败且下游无法继续：按必需依赖失败处理。
- 可选节点遇到预期的数据不可用：记录 `skipped`、原因和数据来源状态，继续估值与报告。
- 可选节点发生代码错误或数据契约错误：记录 `failed` 并终止，避免静默产生错误结论。
- Review 重试：复用相同 `task_type`，不得扩大节点范围。
- 报告结论超出任务范围：Review 不通过，并要求修正报告而不是启动无关研究分支。

## 8. 测试与验收

### 8.1 Router 单元测试

- 五种任务都能解析为唯一且稳定的执行计划。
- 每种计划的必需、支持、可选和屏蔽节点互不冲突。
- 非法任务类型被拒绝。
- `full` 节点和边与现有完整图一致。

### 8.2 图结构测试

- 每种任务只编译计划中的节点。
- 屏蔽节点没有节点事件、Provider 调用或 LLM 调用。
- 各任务能够到达 `report` 并结束，不因未启用前驱而等待。
- Review 重试后仍执行同一任务范围。

### 8.3 任务行为测试

- `industry` 不要求股票代码，不输出个股买卖结论。
- `fundamental` 不运行技术分析，边际变化缺失时可降级完成。
- 边际变化获取失败时，估值仍运行，报告包含跳过原因；代码错误不得被当作数据缺失跳过。
- `technical` 不读取研报、政策或财务预测来源。
- `market` 不要求股票代码或行业名称。
- `full` 保持现有综合决策和报告能力。
- 主动屏蔽不进入 `missing_items`；实际缺失仍可触发重试。

### 8.4 CLI 测试

- `--task` 五个合法值均可运行，默认值为 `full`。
- 非法值提示清楚并返回正确退出码。
- 交互向导能显示任务说明和执行摘要。
- JSON 输出字段稳定，stdout 不混入进度文本。

### 8.5 完成标准

- 全部自动化测试通过。
- `python -m diagram_langgraph_pipeline` 与安装后的命令行入口均完成冒烟测试。
- 对五种任务各运行一次离线或伪数据端到端测试。
- 报告明确区分任务范围、屏蔽节点、数据缺失和降级。
- 本周不包含前端网页、自然语言自动分类、逐节点手动选择和交易执行。
