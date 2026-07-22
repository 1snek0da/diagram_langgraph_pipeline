"""Industry development and technology iteration node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    report = state.get("industry_report_result", {})
    capex = state.get("upstream_capex_result", {})
    policy = state.get("policy_result", {})
    signals = [capex.get("direction"), policy.get("direction")]
    positive = sum(signal in {"up", "positive", "supportive"} for signal in signals)
    negative = sum(signal in {"down", "negative", "restrictive"} for signal in signals)
    trend = "positive" if positive > negative else "negative" if negative > positive else "neutral"
    return {
        "industry_trend_result": {
            "trend": trend,
            "technology_routes": report.get("technology_routes", []),
            "capex_signal": capex.get("direction", "unknown"),
            "policy_signal": policy.get("direction", "neutral"),
            "summary": f"资本开支信号为 {capex.get('direction', 'unknown')}，政策信号为 {policy.get('direction', 'neutral')}。",
        }
    }
