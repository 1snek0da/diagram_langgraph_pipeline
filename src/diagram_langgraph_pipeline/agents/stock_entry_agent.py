"""Stock branch entry node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    return {
        "stock_task_context": {
            "ticker": state["ticker"],
            "company_name": state.get("company_name", ""),
            "as_of_date": state.get("as_of_date"),
        }
    }
