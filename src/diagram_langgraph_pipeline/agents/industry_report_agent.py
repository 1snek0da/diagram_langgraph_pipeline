"""Industry report parsing node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "industry_report", state)
    return {
        "industry_report_result": {
            "summary": payload.get("summary", "未提供行业研报摘要"),
            "market_size": payload.get("market_size"),
            "value_chain": payload.get("value_chain", {}),
            "technology_routes": payload.get("technology_routes", []),
            "key_data": payload.get("key_data", []),
            "reports": payload.get("reports", []),
            "policy_leads": payload.get("policy_leads", []),
            "capex_facts": payload.get("capex_facts", []),
            "source_documents": payload.get("source_documents", []),
            "metric_facts": payload.get("metric_facts", []),
            "source_coverage": payload.get("source_coverage", {}),
            "source_warnings": payload.get("source_warnings", []),
            "source_errors": payload.get("source_errors", []),
            "evidence": evidence_from(payload, "industry_report"),
        }
    }
