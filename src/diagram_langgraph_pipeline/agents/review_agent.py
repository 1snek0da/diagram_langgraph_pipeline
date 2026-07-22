"""Completeness, evidence, and logical consistency review node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


REQUIRED_RESULTS = {
    "industry_valuation_result": "缺少行业价值测算",
    "company_valuation_result": "缺少个股估值测算",
    "stock_market_data_analysis": "缺少个股市场数据分析",
    "index_analysis_result": "缺少大盘分析",
    "sector_technical_result": "缺少板块技术分析",
    "sentiment_result": "缺少市场情绪分析",
    "decision_result": "缺少综合决策",
}


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    missing = list(state.get("missing_items", []))
    for key, message in REQUIRED_RESULTS.items():
        if not state.get(key):
            missing.append(message)
    if len(state.get("evidence_refs", [])) < 3:
        missing.append("可追溯证据少于 3 条")

    coverage = state.get("stock_market_data_analysis", {}).get("data_coverage", {}).get("coverage_ratio", 0.0)
    completeness = max(0.0, 1.0 - len(set(missing)) * 0.08)
    evidence_score = min(1.0, len(state.get("evidence_refs", [])) / 6)
    logic_score = 0.9 if state.get("decision_result", {}).get("conflict_points") is not None else 0.5
    retry_count = int(state.get("retry_count", 0))
    max_retries = int(state.get("max_retries", 2))
    passed = completeness >= 0.75 and evidence_score >= 0.5 and coverage >= 0.8
    needs_retry = not passed and retry_count < max_retries
    next_retry_count = retry_count + 1 if needs_retry else retry_count
    unique_missing = list(dict.fromkeys(missing))
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
            "missing_items": unique_missing,
            "retry_tasks": [f"补采：{item}" for item in unique_missing],
            "review_comment": "校验通过" if passed else "证据或数据覆盖不足，报告必须降低置信度",
        },
    }
