"""Final Markdown research report node."""

from __future__ import annotations

import json
from typing import Any

from ..dependencies import AgentDependencies
from ..routing import get_execution_plan


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    task_type = state.get("task_type", "full")
    advisory = (
        {"status": "disabled"}
        if state.get("llm_scope") == "all_nodes" or task_type != "full"
        else _generate_llm_advisory(state, deps)
    )
    if task_type == "full":
        conclusion = dict(state.get("decision_result", {}))
        if advisory["status"] != "disabled":
            conclusion["llm_advisory"] = advisory
    else:
        conclusion = {
            "conclusion_scope": state.get("conclusion_scope"),
            "selected_results": _selected_results(state, task_type),
        }

    scope_section = _section(
        "任务执行范围",
        {
            "task_type": task_type,
            "required_nodes": state.get("required_nodes", []),
            "support_nodes": state.get("support_nodes", []),
            "optional_nodes": state.get("optional_nodes", []),
            "skipped_nodes": state.get("skipped_nodes", []),
            "completed_nodes": state.get("completed_nodes", []),
            "failed_nodes": state.get("failed_nodes", []),
            "optional_node_statuses": state.get("optional_node_statuses", {}),
            "conclusion_scope": state.get("conclusion_scope", "完整综合研究"),
        },
    )
    section_builder = SECTION_BUILDERS.get(task_type, _full_sections)
    sections = [scope_section, *section_builder(state, conclusion)]
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
    return {"final_markdown": markdown, "llm_advisory_result": advisory}


def _full_sections(state: dict[str, Any], conclusion: dict[str, Any]) -> list[str]:
    decision = state.get("decision_result", {})
    return [
        _section("1. 结论摘要", conclusion),
        _section("2. 行业分析", state.get("industry_report_result", {})),
        _section(
            "3. 上游资本开支与政策影响",
            {
                "capex": state.get("upstream_capex_result", {}),
                "policy": state.get("policy_result", {}),
            },
        ),
        _section(
            "4. 未来资本开支预测与行业价值测算",
            {
                "future_capex_forecast": state.get("future_capex_forecast_result", {}),
                "industry_valuation": state.get("industry_valuation_result", {}),
            },
        ),
        _section("5. 公司业务与行业增长匹配度", state.get("business_result", {})),
        _section(
            "6. 盈利预测与估值测算",
            {
                "forecast": state.get("profit_forecast_result", {}),
                "valuation": state.get("company_valuation_result", {}),
            },
        ),
        _section("7. 边际变化分析", state.get("marginal_change_result", {})),
        _section("8. 个股股市数据分析", state.get("stock_market_data_analysis", {})),
        _section("9. 个股技术形态分析", state.get("stock_technical_result", {})),
        _section(
            "10. 大盘与板块环境",
            {
                "index": state.get("index_analysis_result", {}),
                "sector": state.get("sector_technical_result", {}),
            },
        ),
        _section("11. 市场情绪分析", state.get("sentiment_result", {})),
        _section("12. 综合买卖点判断", decision),
        _section(
            "13. 主要风险与失效条件",
            {
                "risks": state.get("risk_points", []),
                "invalid_condition": decision.get("invalid_condition"),
            },
        ),
        _section(
            "14. 证据引用与数据缺口",
            {
                "evidence": state.get("evidence_refs", []),
                "missing_items": state.get("missing_items", []),
            },
        ),
        _section("15. Reflection 校验结果", state.get("review_result", {})),
    ]


def _industry_sections(
    state: dict[str, Any], conclusion: dict[str, Any]
) -> list[str]:
    return [
        _section("1. 行业研究结论", conclusion),
        _section("2. 行业分析", state.get("industry_report_result", {})),
        _section(
            "3. 上游资本开支与政策影响",
            {
                "capex": state.get("upstream_capex_result", {}),
                "policy": state.get("policy_result", {}),
            },
        ),
        _section(
            "4. 未来资本开支预测与行业价值测算",
            {
                "future_capex_forecast": state.get(
                    "future_capex_forecast_result", {}
                ),
                "industry_valuation": state.get("industry_valuation_result", {}),
            },
        ),
        *_partial_review_sections(state, 5),
    ]


def _fundamental_sections(
    state: dict[str, Any], conclusion: dict[str, Any]
) -> list[str]:
    return [
        _section("1. 基本面与估值结论", conclusion),
        _section("2. 公司业务与行业增长匹配度", state.get("business_result", {})),
        _section(
            "3. 盈利预测与估值测算",
            {
                "forecast": state.get("profit_forecast_result", {}),
                "valuation": state.get("company_valuation_result", {}),
            },
        ),
        _section("4. 边际变化分析", state.get("marginal_change_result", {})),
        *_partial_review_sections(state, 5),
    ]


def _technical_sections(
    state: dict[str, Any], conclusion: dict[str, Any]
) -> list[str]:
    return [
        _section("1. 技术面结论", conclusion),
        _section("2. 个股股市数据分析", state.get("stock_market_data_analysis", {})),
        _section("3. 个股技术形态分析", state.get("stock_technical_result", {})),
        *_partial_review_sections(state, 4),
    ]


def _market_sections(state: dict[str, Any], conclusion: dict[str, Any]) -> list[str]:
    return [
        _section("1. 市场环境结论", conclusion),
        _section(
            "2. 大盘与板块环境",
            {
                "index": state.get("index_analysis_result", {}),
                "sector": state.get("sector_technical_result", {}),
            },
        ),
        _section("3. 市场情绪分析", state.get("sentiment_result", {})),
        *_partial_review_sections(state, 4),
    ]


def _partial_review_sections(state: dict[str, Any], start: int) -> list[str]:
    return [
        _section(
            f"{start}. 主要风险与失效条件",
            {
                "risks": state.get("risk_points", []),
                "invalid_conditions": _partial_invalid_conditions(state),
            },
        ),
        _section(
            f"{start + 1}. 证据引用与数据缺口",
            {
                "evidence": state.get("evidence_refs", []),
                "missing_items": state.get("missing_items", []),
            },
        ),
        _section(
            f"{start + 2}. Reflection 校验结果", state.get("review_result", {})
        ),
    ]


def _selected_results(state: dict[str, Any], task_type: str) -> dict[str, Any]:
    joined = state.get("joined_research_result", {}).get("selected_results")
    plan = get_execution_plan(task_type)
    if joined is None:
        result_keys = state.get("result_keys", plan.result_keys)
        joined = {key: state.get(key, {}) for key in result_keys}
    optional_nodes = set(state.get("optional_nodes", getattr(plan, "optional_nodes", ())))
    skipped_optional_nodes = {
        node
        for node, status in state.get("optional_node_statuses", {}).items()
        if status.get("status") == "skipped"
    }
    return {
        key: result
        for key, result in joined.items()
        if not (
            key.removesuffix("_result") in skipped_optional_nodes
            or (
                key.removesuffix("_result") in optional_nodes
                and result.get("status") == "skipped"
            )
        )
    }


def _partial_invalid_conditions(state: dict[str, Any]) -> list[str]:
    conditions: list[str] = []
    for result in _selected_results(state, state.get("task_type", "full")).values():
        for field in ("invalid_condition", "invalid_conditions"):
            value = result.get(field)
            if isinstance(value, str) and value:
                conditions.append(value)
            elif isinstance(value, list):
                conditions.extend(str(item) for item in value if item)
    if not conditions:
        conditions.append(
            "核心数据、假设或适用市场状态发生重大变化时，本任务结论失效"
        )
    return list(dict.fromkeys(conditions))


SECTION_BUILDERS = {
    "full": _full_sections,
    "industry": _industry_sections,
    "fundamental": _fundamental_sections,
    "technical": _technical_sections,
    "market": _market_sections,
}


def _generate_llm_advisory(
    state: dict[str, Any], deps: AgentDependencies
) -> dict[str, Any]:
    if deps.llm is None:
        return {"status": "disabled"}
    prompt_payload = {
        "ticker": state.get("ticker"),
        "as_of_date": state.get("as_of_date"),
        "decision": state.get("decision_result", {}),
        "market": state.get("stock_market_data_analysis", {}),
        "technical": state.get("stock_technical_result", {}),
        "review": state.get("review_result", {}),
        "missing_items": state.get("missing_items", []),
        "evidence_claims": [
            item.get("claim_text") for item in state.get("evidence_refs", [])[:20]
        ],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是证券研究报告的辅助解读器。只能总结用户提供的结构化结果，"
                "不得引入新事实、不得修改决策倾向、评分、置信度、买卖区间或 Review，"
                "不得给出下单指令。明确说明关键冲突、数据缺口与失效条件，使用简洁中文。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                prompt_payload, ensure_ascii=False, default=str, separators=(",", ":")
            ),
        },
    ]
    try:
        result = deps.llm.generate(messages)
    except (
        Exception
    ) as exc:  # provider failures must not suppress the deterministic report
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "authoritative": False,
        }
    return {
        "status": "completed",
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "request_id": result.request_id,
        "finish_reason": result.finish_reason,
        "usage": result.usage,
        "authoritative": False,
        "scope": "仅辅助解读；不参与规则决策与 Review",
    }


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
    "invalid_conditions": "失效条件",
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
    "trend_scoring": "趋势评分（满分100）",
    "pattern_scoring": "技术形态评分（满分10）",
    "composite_scoring": "趋势与形态综合评分",
    "annual_valuations": "逐年合理市值",
    "investment_signal": "文档估值阈值信号",
    "adjusted_forecasts": "两阶段修正后盈利预测",
    "llm_advisory": "LLM 辅助解读",
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
            blocks.append(
                f"{'#' * min(level, 6)} 条目 {index}\n\n{_render(item, level + 1)}"
            )
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
