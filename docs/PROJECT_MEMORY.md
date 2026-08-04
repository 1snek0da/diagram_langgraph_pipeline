# Diagram LangGraph Pipeline 项目记忆

> 迁移日期：2026-07-23
>
> 来源：父项目 `trading_agent_learn` 中与本项目直接相关的 Codex 历史任务，并已与
> 当前目录代码、Git 状态和测试结果交叉核对。重复任务已去重。

### Codex 任务继承范围

当前记忆已继承并去重以下同一项目历史任务：

- `019f8351-9ef6-7132-b665-f4d72725f7f9`：原始完整设计与实现历史；
- `019f8dcf-7afa-78f2-afc0-9e078578d122`、`019f8dcf-3333-7d91-b36c-b4b3af61cf91`：
  前述任务的重复副本，没有额外的独立产品决策；
- `019f8ddf-238e-7a92-96f4-7b6d88e2c130`：项目记忆迁移、行业/个股信息源
  规范化实现，以及 PostgreSQL 客户端、商业数据凭据和 GitHub 发布环境记录。

继承内容包括：原图驱动的流水线设计、从零重写与 Agent 文件拆分、数据库关系、
独立仓库发布、DDG-DA、TRA、实时交易与两篇论文研究、行业分析 DOCX 所导出的
信息源契约、信息源规范化实现和验证结果。一次性的对话措辞、重复输出和失效的
中间实现没有逐字复制；其有效决策均已固化在本文件、`AGENTS.md`、`PLAN.md`、
`docs/research_source_contract.md` 及两篇论文总结中。

## 1. 为什么创建本项目

最初需求是把一张股票研究流程图转成 LangGraph Agent 流水线，同时重构数据库并
输出详细 Markdown 计划。后续明确了几项长期有效的选择：

- 不沿用父项目原有完整多 Agent 结构，纯粹按示意图重建节点。
- 不修改父项目已有文件，所有代码放入新建的 `diagram_langgraph_pipeline/`。
- 个股分支必须包含“行情抓取”和“行情分析”两个明确节点。
- 每个不同 Agent 节点拆成独立文件并放在 `agents/` 中。
- 数据库关系需要有可读的图形化说明。
- 最终交付是研究报告，不是自动交易系统。

项目后来从父工作区分离为独立、可安装的 Python 仓库。

## 2. 已实现基线

### 2.1 LangGraph 流程

当前实现是实际的 `StateGraph`，而不是流程图占位代码：

```text
START -> planner
planner -> industry_entry / stock_entry / market_entry

industry_entry -> industry_report
industry_report -> upstream_capex + policy
upstream_capex + policy -> future_capex_forecast -> industry_valuation

stock_entry -> stock_data_fetch -> stock_data_analysis -> stock_technical
stock_entry -> business -> profit_forecast + marginal_change
profit_forecast + marginal_change + stock_data_analysis -> company_valuation

market_entry -> index_analysis + sector_technical + sentiment

industry_valuation
+ company_valuation
+ stock_technical
+ stock_data_analysis
+ index_analysis
+ sector_technical
+ sentiment
-> research_join -> decision -> review

review -> planner（需要补采且未达到重试上限）
review -> report -> END（通过或达到重试上限）
```

节点执行记录由图装配层统一包装，避免在二十多个 Agent 中重复审计逻辑。

### 2.2 State 与依赖边界

`DiagramBasedResearchState` 保存：

- 请求标识、股票、公司、行业、日期、投资周期和基准代码；
- 调用方提供的 `research_inputs`；
- 行业、个股、市场三条分支的中间结果；
- 汇总、决策、Review 和最终 Markdown；
- 证据引用、缺失项、风险点和重试计数。

外部能力通过协议和依赖注入隔离：

- `MarketDataProvider`：行情；
- `ResearchDataProvider`：研报、政策、公告、情绪等研究资料；
- `AnalysisRepository`：运行、节点、决策与报告持久化。
- `LanguageModelProvider`：2026-07-31 增加火山引擎 OpenAI 兼容可选实现，默认关闭；
  模型输出只进入报告辅助解读，不得覆盖确定性决策和 Review。

默认 Provider 适合离线和测试。`YFinanceMarketDataProvider` 可提供生产行情的基础
接入，但真实部署仍需实现可靠的研究资料 Provider 和 PostgreSQL Repository。

2026-07-23 已将研究资料接口升级为 `SourceRequest -> SourceBatch` 类型化契约：

- 来源文档、指标事实、证据和覆盖率分别由 Pydantic v2 模型校验；
- 数值使用 `Decimal`，事实口径区分 `reported`、`extracted`、`estimated`、`derived`；
- 默认以旧 `research_inputs` 兼容层和授权文件目录离线运行；
- SEC、ECB、官方政策网页、Tushare、巨潮与 Wind/iFinD 作为可插拔适配器；
- 网络来源默认关闭，统一受超时、有限重试、限速、缓存和 `as_of_date` 控制；
- Alphabet、Amazon、Microsoft、Meta、Oracle 属于需求侧，NVIDIA 只作为供应侧指标；
- 通信 CapEx 无明确披露时保持空值，不按总 CapEx 比例静默补齐。

### 2.3 个股行情分析

现有指标层覆盖：

- 5/20/60/120/250 日区间收益；
- MA20/60/120/250 趋势结构；
- 年化波动率、最大回撤、ATR；
- 成交量放大/萎缩及量价信号；
- PE/PB/PS 当前值与历史分位；
- 跳空、单日异动、异常成交量、均线突破/跌破；
- 相对行业指数和大盘指数的强弱。

默认日线抓取窗口约 550 个自然日，以获得不少于 250 个交易日。

### 2.4 决策和 Review

长期有效的决策约束：

- 行业空间、上游资本开支、政策环境共同影响行业评分。
- 公司业务与高景气行业匹配且盈利预测上修时，提高基本面评分。
- 趋势向上、相对强势且量价健康时，提高技术与市场评分。
- 高估值、短期涨幅过大、异常放量或情绪拥挤时，降低追买强度。
- 明确订单、认证、产能和产品进展等边际变化可提高短期驱动评分。
- 大盘偏弱时，即使个股基本面较好，也应优先等待、分批或降低置信度。
- 数据或证据不足时不得给出高置信度方向结论。

Review 负责完整性、证据和逻辑一致性检查。达到 `max_retries` 后仍应生成报告，
但必须明确低置信度与缺失项，不能无限循环。

### 2.5 数据库

PostgreSQL 设计按 `run_id` 建立可追溯链，主要包括：

- 主数据：`industries`、`securities`；
- 资料与证据：`source_documents`、`evidence_items`；
- 行情与估值：`market_bars`、`market_valuation_metrics`、
  `stock_market_analysis`；
- 行业、公司、盈利、边际变化、技术和情绪分析表；
- `analysis_runs`、`node_runs`、`decision_records`、`review_records`、
  `final_reports`；
- 决策与证据、节点输出之间的关联表。

来源规范化后新增 `provider_fetch_runs`、`financial_metric_facts`、
`capex_allocations`、`capex_forecasts`、`policy_impact_assessments` 和
`company_classifications`，并通过 `database/migrations/001_research_source_normalization.sql`
对既有数据库做增量升级，不重建历史表。

原则是最终决策必须能追溯到原始资料、行情分析、节点运行和模型/规则版本。

## 3. 仓库与发布记忆

项目已整理为标准 `src/` 包：

- 包名：`diagram-langgraph-pipeline`
- 版本：`0.1.0`
- Python：`>=3.10`
- 运行依赖：Beautiful Soup、HTTPX、LangGraph、Pydantic v2、pypdf、
  python-docx、typing-extensions、yfinance
- 开发依赖：pytest
- 可选数据源依赖：Tushare
- CLI：`diagram-langgraph-pipeline`

独立仓库历史：

- GitHub：`1snek0da/diagram_langgraph_pipeline`
- 初始功能分支：`codex/initial-pipeline`
- 初始项目提交：`96adf49`
- 初始草稿 PR：`#1`
- 初始发布时 Python 3.10、3.11、3.12 CI 全部通过
- 父仓库通过本地 `.git/info/exclude` 忽略本目录，未把它作为嵌套仓库提交
- 未添加 LICENSE

以上远程状态是历史快照；PR 是否仍为草稿、是否已合并，应在需要时重新查询。

迁移当日的本地快照：

- 当前分支仍为 `codex/initial-pipeline`；
- 接口规范化完成后的测试结果为 `23 passed`，并通过 CLI 离线冒烟测试；
- 当前独立目录使用项目 `.venv` 可复现 `23 passed`；未做 editable 安装的系统
  Python 无法直接导入 `src/` 包；
- `docs/papers/` 下的两篇 PDF 与中文总结尚未被当前 Git 提交跟踪；
- `src/*.egg-info/` 和虚拟环境属于本地生成物，不应提交。

### 3.1 本机工具与凭据边界

2026-07-23 的历史任务记录，以及 2026-07-30 的本项目运行更新：

- Windows 已安装 PostgreSQL 16。2026-07-30 已在项目忽略目录初始化独立开发实例，
  主 schema 与增量迁移均已实际执行；连接凭据只保存在 Git 忽略的本地环境文件。
- 商业数据账户、Token、密码和 Wind/iFinD SDK 不属于仓库记忆，不得写入 State、
  日志、数据库、示例配置或 Git。凭据存在性和授权范围每次使用前都要重新检查。
- 旧任务中的 Codex 沙箱没有附加可见终端，且其 GitHub CLI 凭据与 Windows 桌面
  会话隔离，曾返回 401。后续发布不得假定旧登录仍有效，应重新执行只读认证检查。
- GitHub 远程、PR 状态、已安装客户端和 PATH 都是本机历史快照，不是永久项目事实。

## 4. 已完成的专项研究

### 4.1 DDG-DA：市场动态与概念漂移

父工作区参考资料：

- `qlib/market_dynamics/papers/2201.04038_ddg_da_concept_drift.pdf`
- `qlib/code/qlib/contrib/rolling/ddgda.py`

核心记忆：

- DDG-DA 不直接输出市场状态或交易动作，而是预测面向下一阶段的历史样本权重。
- 它适合作为量化预测链路的前置动态适配层，不应替代行业、政策或决策 Agent。
- 优先建设 rolling task、严格时间隔离、无泄漏验证、RR/GF-Exp 基线、
  IC/ICIR 和漂移监控，再考虑完整 DDG-DA。
- 对渐进或重复漂移较有价值；对政策突变、黑天鹅等不可预测漂移必须回退。
- Qlib 官方示例的约 45 GB 内存要求来自全市场因子、多份 DataFrame/Tensor、
  重叠 Meta Task、稠密归属矩阵和并行复制，不是模型参数或显存需求。

未来若落地，可考虑新增 rolling task、分布快照、漂移评估、样本权重、模型版本和
样本外评估表；完整实现前应先做 `float32`、惰性任务、稀疏归属和并行度限制。

### 4.2 TRA：多预测头与时序路由

父工作区参考资料：

- `qlib/market_dynamics/papers/2106.12950_tra_temporal_routing_adaptor.pdf`
- `qlib/code/qlib/contrib/model/pytorch_tra.py`

核心记忆：

- TRA 是“共享时序骨干 + 多预测头 + Router + 历史误差 Memory”。
- 潜在模式是样本级统计模式，不能直接命名为牛市、熊市或震荡市。
- 行业、新闻和技术面 LLM Agent 不应被误当作 TRA 的预测头。
- TRA 最适合成为个股分支中的独立数值预测子图；现有描述性技术分析继续保留。
- 路由熵高、预测头分歧大、近期 IC/ICIR 失效或出现数据漂移时必须降级。
- 训练需要跨股票截面、严格时间切分、历史误差记忆、模型注册和 walk-forward
  评估；当前单股约 250 日 OHLCV 不足以训练可靠 TRA。

合理顺序是：特征与标签 → 单头基线 → 无泄漏 walk-forward → `K=3` TRA →
路由/漂移监控 → 仅在持续优于基线时进入决策评分。

### 4.3 实时交易与订单执行

当前仓库不是实时交易系统，缺少流式行情、L2 重建、组合仓位、订单状态机、成交
回报、TCA、Broker Adapter 和实盘硬风控。

长期架构边界：

```text
LangGraph 低频研究
-> 目标仓位
-> 事前风险检查
-> 确定性执行计划
-> 订单路由与 Broker Adapter
-> 订单状态机 / 成交 / 仓位核对
-> TCA 与复盘
```

LangGraph 可负责目标仓位、风险预算、授权、部署审批和复盘；毫秒级控制循环必须是
独立、确定性、异步事件驱动服务。任何 RL 策略都不能绕过事前风控和 kill switch。

建议建设顺序：

1. 流式行情、交易时钟、序列缺口检查；
2. 模拟 Broker、订单状态机、幂等、仓位核对和 kill switch；
3. TWAP/VWAP/Almgren-Chriss、OFI、限价/市价路由和 TCA；
4. Queue-Reactive、ABIDES 或事件型盘口模拟；
5. 纸面交易后再评估 DQN/PPO/SAC。

### 4.4 非 Markov 做市论文

本仓库已保存：

- `docs/papers/2410.14504_reinforcement_learning_non_markov_market_making.pdf`
- `docs/papers/2410.14504_summary_zh.md`

结论：该论文是模拟环境中的做市可行性研究，不应直接改造现有
`decision_agent`。论文状态只含中间价和库存，未充分解决非 Markov 可观测性，
离散动作与高斯 SAC 输出的映射也不清楚；加入逆向选择后收益显著恶化。

若未来采用，应建设独立 L2/逐笔重放、订单簿与队列模拟、连续双边报价、OMS、
库存账本、markout 统计和不可绕过的硬风控。

### 4.5 A 股 LOB、OFI 与 Siamese 论文

本仓库已保存：

- `docs/papers/2505.22678_efficient_deep_learning_lob_stock_movement.pdf`
- `docs/papers/2505.22678_summary_zh.md`

结论：论文使用 14 只军工 A 股、约四个月 Level-2 十档数据，以最近 50 个 tick
预测未来 10/20/50 tick 的平均中间价变化。OFI 和买卖盘共享编码器的 Siamese
结构大多优于对应基线，但长周期样本外 `R²` 常接近零或为负，且没有手续费、滑点、
延迟、成交概率或策略回测。

它只适合作为未来短周期盘口分支：

```text
Level-2 -> 序列校验 -> 十档 OFI -> Siamese 序列模型
-> 成本/时效校准 -> 入场时机与流动性风险证据
```

该信号不应直接进入基本面总分，也不能直接输出订单。

## 5. 后续路线图

### P0：完成当前研究系统的生产闭环

- 接入可靠的行情、研报、政策、公告和情绪 Provider；
- 实现 PostgreSQL Repository 与节点级可追溯持久化；
- 配置 LangGraph checkpointer、中断恢复和人工复核；
- 用历史样本回放并校准现有决策阈值；
- 为输入输出建立结构化 schema、来源时间和数据覆盖度校验。

### P1：建立可验证的量化预测基础

- 跨股票面板、复权、停牌和幸存者偏差处理；
- 因子与标签版本、严格时间切分、embargo gap；
- 单模型基线、walk-forward、IC/Rank IC/ICIR、换手、回撤和成本评估；
- 模型注册、数据漂移、性能衰减和回退机制。

### P2：按证据逐步引入 DDG-DA 或 TRA

只在稳定优于简单基线且通过样本外验证后，把模型输出作为综合决策中的一个受限
信号。不要同时引入多个复杂模型，以免无法归因。

### P3：独立建设实时执行或微观结构系统

只有在低频研究、目标仓位、硬风控、模拟 Broker 和 TCA 成熟后，再建设 Level-2、
订单执行或做市分支；不要把实时交易逻辑塞入当前同步研究图。

## 6. 维护本记忆的规则

- 新功能完成后，把它从“路线图/建议”移动到“已实现基线”，并附测试依据。
- 易变化的远程状态、分支、PR 和测试数量应标注日期，不写成永久事实。
- 论文精读以对应 `docs/papers/*_summary_zh.md` 为准，本文件只保留影响架构的结论。
- 若记忆与代码冲突，以当前代码和测试为准，并同步修正文档。
