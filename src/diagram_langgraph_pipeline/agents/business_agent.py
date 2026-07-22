"""Company business-understanding node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "business", state)
    return {
        "business_result": {
            "business_summary": payload.get("business_summary", "未提供公司业务资料"),
            "revenue_segments": payload.get("revenue_segments", []),
            "industry_linkage": payload.get("industry_linkage", "unknown"),
            "growth_drivers": payload.get("growth_drivers", []),
            "risks": payload.get("risks", []),
            "evidence": evidence_from(payload, "company_business"),
        }
    }
