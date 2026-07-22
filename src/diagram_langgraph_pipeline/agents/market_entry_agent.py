"""Market branch entry node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    return {
        "market_task_context": {
            "benchmark_ticker": state.get("benchmark_ticker", "000300.SS"),
            "sector_index_ticker": state.get("sector_index_ticker", ""),
            "as_of_date": state.get("as_of_date"),
        }
    }
