"""Completeness, evidence, and logical consistency review node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


REQUIRED_RESULTS = {
    "future_capex_forecast_result": "缺少未来资本开支预测",
    "industry_valuation_result": "缺少行业价值测算",
    "company_valuation_result": "缺少个股估值测算",
    "stock_market_data_analysis": "缺少个股市场数据分析",
    "stock_technical_result": "缺少个股技术形态分析",
    "index_analysis_result": "缺少大盘分析",
    "sector_technical_result": "缺少板块技术分析",
    "sentiment_result": "缺少市场情绪分析",
    "decision_result": "缺少综合决策",
}

RESULT_NODES = {
    "industry_report_result": "industry_report",
    "upstream_capex_result": "upstream_capex",
    "policy_result": "policy",
    "future_capex_forecast_result": "future_capex_forecast",
    "industry_valuation_result": "industry_valuation",
    "business_result": "business",
    "profit_forecast_result": "profit_forecast",
    "marginal_change_result": "marginal_change",
    "company_valuation_result": "company_valuation",
    "stock_market_data_analysis": "stock_data_analysis",
    "stock_technical_result": "stock_technical",
    "index_analysis_result": "index_analysis",
    "sector_technical_result": "sector_technical",
    "sentiment_result": "sentiment",
    "decision_result": "decision",
}


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    task_type = state.get("task_type", "full")
    required_outputs = tuple(
        state.get("required_outputs", tuple(REQUIRED_RESULTS))
    )
    skipped_nodes = set(state.get("skipped_nodes", ()))
    skipped_nodes.update(
        node
        for node, status in state.get("optional_node_statuses", {}).items()
        if status.get("status") == "skipped"
    )
    effective_required_outputs = tuple(
        key for key in required_outputs if RESULT_NODES.get(key) not in skipped_nodes
    )
    missing = _scoped_missing_items(state, effective_required_outputs, skipped_nodes)
    missing_required: list[str] = []
    for key in effective_required_outputs:
        if not state.get(key):
            missing_required.append(key)
            missing.append(f"缺少必需结果：{key}")

    evidence_required = task_type in {"full", "industry", "fundamental", "market"}
    if evidence_required and len(state.get("evidence_refs", [])) < 3:
        missing.append("可追溯证据少于 3 条")

    coverage = (
        state.get("stock_market_data_analysis", {})
        .get("data_coverage", {})
        .get("coverage_ratio", 0.0)
    )
    industry_coverage = (
        state.get("upstream_capex_result", {})
        .get("company_coverage", {})
        .get("coverage_ratio", 0.0)
    )
    market_coverage_required = task_type in {"full", "technical"}
    industry_coverage_required = task_type in {"full", "industry"}
    if market_coverage_required and coverage < 0.8:
        missing.append("个股市场数据覆盖率低于 0.8")
    if industry_coverage_required and industry_coverage < 0.6:
        missing.append("行业公司覆盖率低于 0.6")

    completeness = max(0.0, 1.0 - len(set(missing)) * 0.08)
    evidence_score = min(1.0, len(state.get("evidence_refs", [])) / 6)
    logic_score = (
        0.9
        if state.get("decision_result", {}).get("conflict_points") is not None
        else 0.5
    )
    retry_count = int(state.get("retry_count", 0))
    max_retries = int(state.get("max_retries", 2))
    has_required_results = not missing_required
    if task_type == "technical":
        passed = has_required_results and coverage >= 0.8
    elif task_type == "industry":
        passed = (
            has_required_results
            and evidence_score >= 0.5
            and industry_coverage >= 0.6
        )
    elif task_type in {"fundamental", "market"}:
        passed = has_required_results and evidence_score >= 0.5
    else:
        passed = (
            has_required_results
            and completeness >= 0.75
            and evidence_score >= 0.5
            and coverage >= 0.8
            and industry_coverage >= 0.6
        )
    needs_retry = not passed and retry_count < max_retries
    next_retry_count = retry_count + 1 if needs_retry else retry_count
    unique_missing = list(dict.fromkeys(missing))
    retry_tasks: list[str | dict[str, Any]] = [
        {
            "node": RESULT_NODES[key],
            "result_key": key,
            "reason": f"缺少必需结果：{key}",
        }
        for key in missing_required
        if RESULT_NODES.get(key) not in skipped_nodes
    ]
    required_messages = {f"缺少必需结果：{key}" for key in missing_required}
    retry_tasks.extend(
        f"补采：{item}" for item in unique_missing if item not in required_messages
    )
    return {
        "retry_count": next_retry_count,
        "missing_items": unique_missing,
        "review_result": {
            "passed": passed,
            "needs_retry": needs_retry,
            "retry_exhausted": not passed and retry_count >= max_retries,
            "completeness_score": round(completeness, 4),
            "evidence_score": round(evidence_score, 4),
            "logic_score": logic_score,
            "market_data_coverage": coverage,
            "industry_company_coverage": industry_coverage,
            "missing_items": unique_missing,
            "retry_tasks": retry_tasks,
            "review_comment": (
                "校验通过" if passed else "证据或数据覆盖不足，报告必须降低置信度"
            ),
        },
    }


def _scoped_missing_items(
    state: dict[str, Any],
    required_outputs: tuple[str, ...],
    skipped_nodes: set[str],
) -> list[str]:
    required = set(required_outputs)
    legacy_messages = {message: key for key, message in REQUIRED_RESULTS.items()}
    scoped: list[str] = []
    for item in state.get("missing_items", []):
        result_key = legacy_messages.get(item)
        if item.startswith("缺少必需结果："):
            result_key = item.removeprefix("缺少必需结果：")
        if result_key is not None and result_key not in required:
            continue
        if any(
            key in item and node in skipped_nodes
            for key, node in RESULT_NODES.items()
        ):
            continue
        scoped.append(item)
    return scoped
