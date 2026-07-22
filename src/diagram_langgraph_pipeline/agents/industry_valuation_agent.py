"""Industry future-value scenario node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import number, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "industry_valuation", state)
    current_market_cap = number(payload.get("current_market_cap"))
    scenarios = []
    for item in payload.get("scenarios", []):
        future_profit = number(item.get("future_profit"))
        future_revenue = number(item.get("future_revenue"))
        assumed_pe = number(item.get("assumed_pe"))
        assumed_ps = number(item.get("assumed_ps"))
        estimated = None
        method = None
        if future_profit is not None and assumed_pe is not None:
            estimated = future_profit * assumed_pe
            method = "PE"
        elif future_revenue is not None and assumed_ps is not None:
            estimated = future_revenue * assumed_ps
            method = "PS"
        upside = estimated / current_market_cap - 1 if estimated and current_market_cap else None
        scenarios.append({**item, "method": method, "estimated_market_cap": estimated, "upside_pct": upside})
    return {
        "industry_valuation_result": {
            "current_market_cap": current_market_cap,
            "scenarios": scenarios,
            "assumptions": payload.get("assumptions", []),
            "confidence_score": payload.get("confidence_score", 0.4 if scenarios else 0.1),
        }
    }
