"""Upstream capital-expenditure analysis node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, mean_or_none, number, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "upstream_capex", state)
    records = payload.get("records", [])
    changes = [number(item.get("capex_change_pct")) for item in records if isinstance(item, dict)]
    average_change = mean_or_none(changes)
    if average_change is None:
        direction = "unknown"
    elif average_change >= 0.1:
        direction = "up"
    elif average_change <= -0.1:
        direction = "down"
    else:
        direction = "flat"
    return {
        "upstream_capex_result": {
            "direction": payload.get("direction", direction),
            "average_change_pct": average_change,
            "demand_signal": payload.get("demand_signal", "证据不足"),
            "records": records,
            "evidence": evidence_from(payload, "upstream_capex"),
        }
    }
