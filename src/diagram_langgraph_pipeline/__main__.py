"""Run an offline demonstration with: python -m diagram_langgraph_pipeline."""

from __future__ import annotations

from .demo_data import demo_research_inputs, make_market_payload
from .dependencies import AgentDependencies
from .providers import InMemoryMarketDataProvider
from .runner import run_research


def main() -> None:
    payloads = {
        "DEMO": make_market_payload(20.0, 0.0010),
        "BENCH": make_market_payload(100.0, 0.0003),
        "SECTOR": make_market_payload(50.0, 0.0006),
    }
    state = run_research(
        {
            "ticker": "DEMO",
            "company_name": "示例公司",
            "industry_name": "示例行业",
            "as_of_date": "2026-07-21",
            "investment_horizon": "medium",
            "user_request": "完整研究",
            "benchmark_ticker": "BENCH",
            "sector_index_ticker": "SECTOR",
            "research_inputs": demo_research_inputs(),
            "retry_count": 0,
            "max_retries": 1,
        },
        AgentDependencies(market_data=InMemoryMarketDataProvider(payloads)),
    )
    print(state["final_markdown"])


if __name__ == "__main__":
    main()
