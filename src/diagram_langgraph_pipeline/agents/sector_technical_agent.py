"""Sector-index technical analysis node."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..analysis.market_metrics import analyze_market_payload
from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    ticker = state.get("sector_index_ticker", "")
    if not ticker:
        return {
            "sector_technical_result": {
                "target_code": None,
                "trend": "unknown",
                "cycle_position": "unknown",
                "missing_items": ["未提供行业指数代码"],
            }
        }
    end_date = date.fromisoformat(state["as_of_date"]) if state.get("as_of_date") else date.today()
    payload = state.get("stock_market_data", {}).get("sector")
    if payload is None:
        payload = deps.market_data.fetch(ticker, end_date - timedelta(days=550), end_date)
    analysis = analyze_market_payload(payload)
    positions = [
        analysis.get("ma_status", {}).get(f"ma{window}", {}).get("price_position")
        for window in (20, 60, 120)
    ]
    trend = "up" if all(item == "above" for item in positions) else "down" if all(item == "below" for item in positions) else "sideways"
    return {
        "sector_technical_result": {
            "target_code": ticker,
            "trend": trend,
            "cycle_position": "expansion" if trend == "up" else "contraction" if trend == "down" else "transition",
            "market_metrics": analysis,
            "missing_items": [],
        }
    }
