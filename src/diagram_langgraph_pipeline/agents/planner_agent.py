"""Research planning node."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    ticker = state.get("ticker", "").strip()
    industry = state.get("industry_name", "").strip()
    if not ticker or not industry:
        raise ValueError("ticker and industry_name are required")

    retry_tasks = state.get("review_result", {}).get("retry_tasks", [])
    return {
        "run_id": state.get("run_id") or str(uuid4()),
        "as_of_date": state.get("as_of_date"),
        "investment_horizon": state.get("investment_horizon", "medium"),
        "retry_count": int(state.get("retry_count", 0)),
        "max_retries": int(state.get("max_retries", 2)),
        "planner_tasks": {
            "industry": ["industry_report", "upstream_capex", "policy", "industry_trend", "industry_valuation"],
            "stock": [
                "stock_data_fetch",
                "stock_data_analysis",
                "business",
                "profit_forecast",
                "marginal_change",
                "company_valuation",
                "stock_technical",
            ],
            "market": ["index_analysis", "sector_technical", "sentiment"],
            "retry_tasks": retry_tasks,
        },
    }
