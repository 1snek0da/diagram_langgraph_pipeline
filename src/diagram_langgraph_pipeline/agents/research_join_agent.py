"""Cross-branch research synthesis node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


RESULT_KEYS = (
    "industry_report_result",
    "upstream_capex_result",
    "policy_result",
    "future_capex_forecast_result",
    "industry_valuation_result",
    "business_result",
    "profit_forecast_result",
    "marginal_change_result",
    "company_valuation_result",
    "stock_market_data_analysis",
    "sentiment_result",
)


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for key in RESULT_KEYS:
        evidence.extend(state.get(key, {}).get("evidence", []))

    market_missing = (
        state.get("stock_market_data_analysis", {})
        .get("data_coverage", {})
        .get("missing_items", [])
    )
    technical_missing = state.get("stock_technical_result", {}).get("missing_items", [])
    sector_missing = state.get("sector_technical_result", {}).get("missing_items", [])
    research_missing: list[str] = []
    for key in RESULT_KEYS:
        result = state.get(key, {})
        research_missing.extend(result.get("missing_items", []))
        research_missing.extend(result.get("coverage", {}).get("missing_items", []))
    risks = list(state.get("business_result", {}).get("risks", []))
    if state.get("stock_technical_result", {}).get("high_position_risk"):
        risks.append("股价明显偏离 MA20，存在高位回撤风险")
    if state.get("sentiment_result", {}).get("crowding_risk") == "high":
        risks.append("市场情绪拥挤，追涨风险较高")

    joined = {
        "industry": {
            "future_capex_forecast": state.get("future_capex_forecast_result", {}),
            "valuation": state.get("industry_valuation_result", {}),
        },
        "stock": {
            "business": state.get("business_result", {}),
            "profit_forecast": state.get("profit_forecast_result", {}),
            "marginal_change": state.get("marginal_change_result", {}),
            "market_data": state.get("stock_market_data_analysis", {}),
            "valuation": state.get("company_valuation_result", {}),
            "technical": state.get("stock_technical_result", {}),
        },
        "market": {
            "index": state.get("index_analysis_result", {}),
            "sector": state.get("sector_technical_result", {}),
            "sentiment": state.get("sentiment_result", {}),
        },
    }
    return {
        "joined_research_result": joined,
        "evidence_refs": evidence,
        "missing_items": list(
            dict.fromkeys(
                [
                    *research_missing,
                    *market_missing,
                    *technical_missing,
                    *sector_missing,
                ]
            )
        ),
        "risk_points": list(dict.fromkeys(risks)),
    }
