"""Cross-branch research synthesis node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


OPTIONAL_RESULT_NODES = {"marginal_change_result": "marginal_change"}


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    result_keys = tuple(state.get("result_keys", ()))
    skipped_optional_nodes = {
        node
        for node, status in state.get("optional_node_statuses", {}).items()
        if status.get("status") == "skipped"
    }
    selected_results = {
        key: state.get(key, {})
        for key in result_keys
        if not (
            OPTIONAL_RESULT_NODES.get(key) in skipped_optional_nodes
            or (
                OPTIONAL_RESULT_NODES.get(key) is not None
                and state.get(key, {}).get("status") == "skipped"
            )
        )
    }

    evidence: list[dict[str, Any]] = []
    research_missing: list[str] = []
    risks: list[str] = []
    for key, result in selected_results.items():
        evidence.extend(result.get("evidence", []))
        research_missing.extend(result.get("missing_items", []))
        research_missing.extend(result.get("coverage", {}).get("missing_items", []))
        research_missing.extend(
            result.get("data_coverage", {}).get("missing_items", [])
        )
        risks.extend(result.get("risks", []))

    if selected_results.get("stock_technical_result", {}).get("high_position_risk"):
        risks.append("股价明显偏离 MA20，存在高位回撤风险")
    if selected_results.get("sentiment_result", {}).get("crowding_risk") == "high":
        risks.append("市场情绪拥挤，追涨风险较高")

    joined = {
        "task_type": state.get("task_type", "full"),
        "conclusion_scope": state.get("conclusion_scope", "完整综合研究"),
        "selected_results": selected_results,
    }
    return {
        "joined_research_result": joined,
        "evidence_refs": evidence,
        "missing_items": list(dict.fromkeys(research_missing)),
        "risk_points": list(dict.fromkeys(risks)),
    }
