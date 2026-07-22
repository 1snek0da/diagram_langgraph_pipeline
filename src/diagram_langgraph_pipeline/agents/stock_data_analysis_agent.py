"""Stock market-data analysis node."""

from __future__ import annotations

from typing import Any

from ..analysis.market_metrics import analyze_market_payload
from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    market_data = state.get("stock_market_data", {})
    analysis = analyze_market_payload(
        market_data.get("stock", {}),
        benchmark_payload=market_data.get("benchmark"),
        sector_payload=market_data.get("sector"),
    )
    analysis["ticker"] = state["ticker"]
    analysis["analysis_window"] = "latest_250_trading_days"
    return {"stock_market_data_analysis": analysis}
