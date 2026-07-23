# 研究信息源接口规范

## 1. 公共调用契约

所有来源适配器实现同一接口：

```python
class ResearchSourceAdapter(Protocol):
    name: str
    capabilities: frozenset[DatasetKind]

    def fetch(self, request: SourceRequest) -> SourceBatch: ...
```

`SourceRequest` 必须包含 `dataset_kind`、`run_id` 和 `as_of_date`。历史窗口默认五年，
预测年度默认是 `as_of_date` 后两个自然年，基准币种默认 CNY。标的统一使用
`EntityRef`，海外资本开支实体的 `role` 明确为 `demand` 或 `supply`。

`SourceBatch` 始终返回：

- `data`：通过主题模型校验的节点输入；
- `documents`：来源、外部 ID、发布时间、URL/文件路径、哈希与授权范围；
- `facts`：`Decimal` 数值、币种、单位、缩放倍数、期间及事实口径；
- `evidence`：声明、摘录、页码/段落、提取方式和置信度；
- `coverage`：请求项、覆盖项、缺失项、覆盖率和来源错误；
- `warnings`、`errors`：局部失败与使用限制，不以单个来源失败中断全图。

主题模型禁止未声明顶层字段；旧 `research_inputs[topic]` 先通过兼容 Adapter 转成
相同的 `SourceBatch`，新节点不会直接接收任意字典。

## 2. 时间与数值规则

- 网络请求、财务记录、政策、研报和事件均按 `published_at <= as_of_date` 截断。
- 无发布日期的盈利预测和边际事件不会进入计算。
- `reported` 只用于官方披露事实；文件抽取得到的数值使用 `extracted`；
  机构或模型估算分别使用 `estimated`、`derived`。
- `value × scale` 转成同币种绝对金额后才能汇总；原单位与缩放倍数必须保留。
- 通信 CapEx 缺失时保持 `null`。总 CapEx 不能隐式替代通信 CapEx。
- 汇率保留原币、交叉货币、汇率值和汇率日期。

## 3. 授权报告 sidecar

授权 PDF、DOCX、HTML 或 TXT 可使用同名 `.扩展名.json` sidecar 提供人工核验后的
结构化内容。例如 `report.pdf.json`：

```json
{
  "published_at": "2026-07-01T00:00:00+08:00",
  "publisher": "授权研究机构",
  "license_scope": "authorized_local_use",
  "facts": [
    {
      "metric_key": "communication_capex",
      "entity_id": "alphabet",
      "fiscal_year": 2025,
      "value": "12.5",
      "currency": "USD",
      "unit": "billion",gh auth login -h github.com
gh auth status
      "scale": "1000000000",
      "basis": "extracted"
    }
  ],
  "evidence": [
    {
      "claim_text": "通信相关资本开支为125亿美元",
      "page_no": 12,
      "quote_text": "经授权核验的短摘录"
    }
  ]
}
```

适配器只读取用户有权使用的本地导出文件，不访问或绕过登录保护页面。

## 4. 行业与个股节点输出

- `upstream_capex_result`：需求侧、供应侧、年度汇总、同比、通信占比和公司覆盖率。
- `future_capex_forecast_result`：未来两年 bear/base/bull、历史区间、方法、置信度和缺失项。
- `industry_valuation_result`：原币、汇率、CNY 金额、估值区间、当前行业市值和差异。
- `business_result`：公司类型、分类证据、收入构成、排名、基础及调整后 PE。
- `profit_forecast_result`：按机构、发布日期、预测年度和口径保存预测并隔离未来数据。
- `marginal_change_result`：订单、认证、产能、客户、产品、管理层和政策事件。
- `company_valuation_result`：预测利润、最终 PE 区间、合理市值区间和上下行空间。

所有新输出只使用 `future_capex_forecast_result`；旧名称仅允许在调用方迁移前的输入
兼容边界处理，不再由图或报告产生。
