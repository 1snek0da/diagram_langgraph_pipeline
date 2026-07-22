"""Final Markdown research report node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    decision = state.get("decision_result", {})
    sections = [
        _section("1. 结论摘要", decision),
        _section("2. 行业分析", state.get("industry_report_result", {})),
        _section("3. 上游资本开支与政策影响", {"capex": state.get("upstream_capex_result", {}), "policy": state.get("policy_result", {})}),
        _section("4. 行业未来价值测算", state.get("industry_valuation_result", {})),
        _section("5. 公司业务与行业增长匹配度", state.get("business_result", {})),
        _section("6. 盈利预测与估值测算", {"forecast": state.get("profit_forecast_result", {}), "valuation": state.get("company_valuation_result", {})}),
        _section("7. 边际变化分析", state.get("marginal_change_result", {})),
        _section("8. 个股股市数据分析", state.get("stock_market_data_analysis", {})),
        _section("9. 个股技术形态分析", state.get("stock_technical_result", {})),
        _section("10. 大盘与板块环境", {"index": state.get("index_analysis_result", {}), "sector": state.get("sector_technical_result", {})}),
        _section("11. 市场情绪分析", state.get("sentiment_result", {})),
        _section("12. 综合买卖点判断", decision),
        _section("13. 主要风险与失效条件", {"risks": state.get("risk_points", []), "invalid_condition": decision.get("invalid_condition")}),
        _section("14. 证据引用与数据缺口", {"evidence": state.get("evidence_refs", []), "missing_items": state.get("missing_items", [])}),
        _section("15. Reflection 校验结果", state.get("review_result", {})),
    ]
    title = f"# {state.get('company_name') or state.get('ticker')} 股票研究报告"
    metadata = (
        f"- 股票代码：{state.get('ticker')}\n"
        f"- 行业：{state.get('industry_name')}\n"
        f"- 分析日期：{state.get('as_of_date')}\n"
        f"- 投资周期：{state.get('investment_horizon', 'medium')}\n"
        "- 声明：本报告仅用于研究辅助，不构成投资建议。"
    )
    markdown = "\n\n".join([title, metadata, *sections]) + "\n"
    deps.repository.save_final_report(str(state.get("run_id", "")), markdown)
    return {"final_markdown": markdown}


def _section(title: str, value: Any) -> str:
    return f"## {title}\n\n{_render(value)}"


LABELS = {
    "action_bias": "决策倾向",
    "confidence_score": "置信度",
    "conviction": "确信程度",
    "supporting_points": "支持理由",
    "conflict_points": "冲突说明",
    "risk_points": "风险点",
    "invalid_condition": "失效条件",
    "summary": "摘要",
    "trend": "趋势",
    "trend_view": "趋势判断",
    "direction": "方向",
    "scenarios": "估值情景",
    "forecasts": "预测明细",
    "missing_items": "数据缺口",
    "evidence": "证据",
    "review_comment": "校验意见",
    "passed": "是否通过",
}


def _render(value: Any, level: int = 3) -> str:
    if isinstance(value, dict):
        if not value:
            return "暂无可用数据。"
        lines: list[str] = []
        for key, item in value.items():
            label = LABELS.get(key, key.replace("_", " "))
            if isinstance(item, (dict, list)):
                lines.append(f"{'#' * min(level, 6)} {label}")
                lines.append("")
                lines.append(_render(item, level + 1))
            else:
                lines.append(f"- **{label}**：{_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "暂无。"
        if all(not isinstance(item, (dict, list)) for item in value):
            return "\n".join(f"- {_scalar(item)}" for item in value)
        blocks = []
        for index, item in enumerate(value, start=1):
            blocks.append(f"{'#' * min(level, 6)} 条目 {index}\n\n{_render(item, level + 1)}")
        return "\n\n".join(blocks)
    return _scalar(value)


def _scalar(value: Any) -> str:
    if value is None:
        return "暂无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
