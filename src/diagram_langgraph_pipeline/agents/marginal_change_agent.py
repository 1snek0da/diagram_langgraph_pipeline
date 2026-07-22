"""Marginal change and near-term catalyst node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "marginal_change", state)
    events = payload.get("events", [])
    positive = sum(item.get("impact_direction") == "positive" for item in events if isinstance(item, dict))
    negative = sum(item.get("impact_direction") == "negative" for item in events if isinstance(item, dict))
    direction = "positive" if positive > negative else "negative" if negative > positive else "neutral"
    return {
        "marginal_change_result": {
            "direction": payload.get("direction", direction),
            "events": events,
            "certainty": payload.get("certainty", "low" if not events else "medium"),
            "impact_horizon": payload.get("impact_horizon", "unknown"),
            "evidence": evidence_from(payload, "marginal_change"),
        }
    }
