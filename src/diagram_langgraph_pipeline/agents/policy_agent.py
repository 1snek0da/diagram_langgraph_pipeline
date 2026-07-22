"""Policy impact analysis node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "policy", state)
    return {
        "policy_result": {
            "direction": payload.get("direction", "neutral"),
            "impact_horizon": payload.get("impact_horizon", "unknown"),
            "summary": payload.get("summary", "未提供可核验政策资料"),
            "events": payload.get("events", []),
            "evidence": evidence_from(payload, "policy"),
        }
    }
