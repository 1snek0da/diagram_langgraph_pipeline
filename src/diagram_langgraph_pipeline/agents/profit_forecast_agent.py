"""Profit forecast aggregation node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, number, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "profit_forecast", state)
    forecasts = []
    for item in payload.get("forecasts", []):
        forecasts.append(
            {
                **item,
                "forecast_year": item.get("forecast_year"),
                "revenue_forecast": number(item.get("revenue_forecast")),
                "net_profit_forecast": number(item.get("net_profit_forecast")),
                "eps_forecast": number(item.get("eps_forecast")),
                "pe_assumption": number(item.get("pe_assumption")),
            }
        )
    revisions = [number(item.get("revision_pct")) for item in forecasts]
    valid_revisions = [value for value in revisions if value is not None]
    revision_direction = "unchanged"
    if valid_revisions and sum(valid_revisions) / len(valid_revisions) >= 0.03:
        revision_direction = "up"
    elif valid_revisions and sum(valid_revisions) / len(valid_revisions) <= -0.03:
        revision_direction = "down"
    return {
        "profit_forecast_result": {
            "forecasts": forecasts,
            "revision_direction": payload.get("revision_direction", revision_direction),
            "consensus_summary": payload.get("consensus_summary", "未提供一致预期"),
            "evidence": evidence_from(payload, "profit_forecast"),
        }
    }
