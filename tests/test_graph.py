import pytest

pytest.importorskip("langgraph")

from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.graph import build_research_graph
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


def test_graph_contains_all_separate_agent_nodes():
    graph = build_research_graph(AgentDependencies(market_data=InMemoryMarketDataProvider({})))
    nodes = set(graph.get_graph().nodes)
    assert {
        "planner",
        "industry_report",
        "future_capex_forecast",
        "stock_data_fetch",
        "stock_data_analysis",
        "company_valuation",
        "research_join",
        "decision",
        "review",
        "report",
    }.issubset(nodes)
