"""Company market-cap valuation scenario node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import number, topic


SCENARIO_MULTIPLIERS = {"bear": 0.85, "base": 1.0, "bull": 1.15}


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "company_valuation", state)
    forecasts = state.get("profit_forecast_result", {}).get("forecasts", [])
    market_payload = state.get("stock_market_data", {}).get("stock", {})
    valuations = market_payload.get("valuations", [])
    current_market_cap = number(payload.get("current_market_cap"))
    if current_market_cap is None and valuations:
        current_market_cap = number(valuations[-1].get("market_cap"))

    target_forecast = forecasts[-1] if forecasts else {}
    forecast_profit = number(payload.get("forecast_profit"), number(target_forecast.get("net_profit_forecast")))
    base_pe = number(payload.get("base_pe"), number(target_forecast.get("pe_assumption")))
    scenarios = []
    if forecast_profit is not None and base_pe is not None:
        for name, multiplier in SCENARIO_MULTIPLIERS.items():
            assumed_pe = base_pe * multiplier
            estimated = forecast_profit * assumed_pe
            upside = estimated / current_market_cap - 1 if current_market_cap else None
            scenarios.append(
                {
                    "scenario_name": name,
                    "forecast_profit": forecast_profit,
                    "assumed_pe": round(assumed_pe, 4),
                    "estimated_market_cap": round(estimated, 4),
                    "upside_pct": round(upside, 6) if upside is not None else None,
                }
            )
    return {
        "company_valuation_result": {
            "current_market_cap": current_market_cap,
            "scenarios": scenarios,
            "valuation_percentile": state.get("stock_market_data_analysis", {}).get("valuation_percentile", {}),
            "assumptions": payload.get("assumptions", []),
            "confidence_score": payload.get("confidence_score", 0.5 if scenarios else 0.1),
        }
    }
