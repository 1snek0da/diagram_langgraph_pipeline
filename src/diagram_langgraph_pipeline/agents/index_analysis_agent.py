"""Broad-market index analysis node."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..analysis.market_metrics import analyze_market_payload
from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    ticker = state.get("benchmark_ticker", "000300.SS")
    end_date = date.fromisoformat(state["as_of_date"]) if state.get("as_of_date") else date.today()
    payload = state.get("stock_market_data", {}).get("benchmark")
    if payload is None:
        payload = deps.market_data.fetch(ticker, end_date - timedelta(days=550), end_date)
    analysis = analyze_market_payload(payload)
    ma = analysis.get("ma_status", {})
    above = sum(ma.get(f"ma{window}", {}).get("price_position") == "above" for window in (20, 60, 120))
    trend = "up" if above == 3 else "down" if above == 0 else "sideways"
    return {
        "index_analysis_result": {
            "index_code": ticker,
            "trend_view": trend,
            "risk_preference": "risk_on" if trend == "up" else "risk_off" if trend == "down" else "neutral",
            "market_metrics": analysis,
        }
    }
