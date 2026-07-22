"""Industry branch entry node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    return {
        "industry_task_context": {
            "industry_name": state["industry_name"],
            "as_of_date": state.get("as_of_date"),
            "horizon": state.get("investment_horizon", "medium"),
        }
    }
