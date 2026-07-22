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
            "evidence": evidence_from(payload, "industry_report"),
        }
    }
