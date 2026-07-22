"""LangGraph assembly for the diagram-driven stock research workflow."""

from __future__ import annotations

from functools import partial, wraps
from typing import Any, Callable, Literal

from .agents import (
    business_agent,
    company_valuation_agent,
    decision_agent,
    index_analysis_agent,
    industry_entry_agent,
    industry_report_agent,
    industry_trend_agent,
    industry_valuation_agent,
    marginal_change_agent,
    market_entry_agent,
    planner_agent,
    policy_agent,
    profit_forecast_agent,
    report_agent,
    research_join_agent,
    review_agent,
    sector_technical_agent,
    sentiment_agent,
    stock_data_analysis_agent,
    stock_data_fetch_agent,
    stock_entry_agent,
    stock_technical_agent,
    upstream_capex_agent,
)
from .dependencies import AgentDependencies
from .state import DiagramBasedResearchState


NodeFunction = Callable[[dict[str, Any], AgentDependencies], dict[str, Any]]


def build_research_graph(deps: AgentDependencies, checkpointer: Any = None) -> Any:
    """Build and compile the complete LangGraph workflow."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError('LangGraph is required. Run: pip install -e ".[dev]"') from exc

    graph = StateGraph(DiagramBasedResearchState)
    nodes: dict[str, NodeFunction] = {
        "planner": planner_agent.run,
        "industry_entry": industry_entry_agent.run,
        "industry_report": industry_report_agent.run,
        "upstream_capex": upstream_capex_agent.run,
        "policy": policy_agent.run,
        "industry_trend": industry_trend_agent.run,
        "industry_valuation": industry_valuation_agent.run,
        "stock_entry": stock_entry_agent.run,
        "stock_data_fetch": stock_data_fetch_agent.run,
        "stock_data_analysis": stock_data_analysis_agent.run,
        "business": business_agent.run,
        "profit_forecast": profit_forecast_agent.run,
        "marginal_change": marginal_change_agent.run,
        "company_valuation": company_valuation_agent.run,
        "stock_technical": stock_technical_agent.run,
        "market_entry": market_entry_agent.run,
        "index_analysis": index_analysis_agent.run,
        "sector_technical": sector_technical_agent.run,
        "sentiment": sentiment_agent.run,
        "research_join": research_join_agent.run,
        "decision": decision_agent.run,
        "review": review_agent.run,
        "report": report_agent.run,
    }
    for node_name, function in nodes.items():
        graph.add_node(node_name, _instrument(node_name, function, deps))

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "industry_entry")
    graph.add_edge("planner", "stock_entry")
    graph.add_edge("planner", "market_entry")

    graph.add_edge("industry_entry", "industry_report")
    graph.add_edge("industry_report", "upstream_capex")
    graph.add_edge("industry_report", "policy")
    graph.add_edge(["upstream_capex", "policy"], "industry_trend")
    graph.add_edge("industry_trend", "industry_valuation")

    graph.add_edge("stock_entry", "stock_data_fetch")
    graph.add_edge("stock_entry", "business")
    graph.add_edge("stock_data_fetch", "stock_data_analysis")
    graph.add_edge("business", "profit_forecast")
    graph.add_edge("business", "marginal_change")
    graph.add_edge(["profit_forecast", "marginal_change", "stock_data_analysis"], "company_valuation")
    graph.add_edge("stock_data_analysis", "stock_technical")

    graph.add_edge("market_entry", "index_analysis")
    graph.add_edge("market_entry", "sector_technical")
    graph.add_edge("market_entry", "sentiment")

    graph.add_edge(
        [
            "industry_valuation",
            "company_valuation",
            "stock_technical",
            "stock_data_analysis",
            "index_analysis",
            "sector_technical",
            "sentiment",
        ],
        "research_join",
    )
    graph.add_edge("research_join", "decision")
    graph.add_edge("decision", "review")
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"retry": "planner", "report": "report"},
    )
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


def route_after_review(state: DiagramBasedResearchState) -> Literal["retry", "report"]:
    return "retry" if state.get("review_result", {}).get("needs_retry", False) else "report"


def _instrument(name: str, function: NodeFunction, deps: AgentDependencies) -> Callable[[dict[str, Any]], dict[str, Any]]:
    @wraps(function)
    def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        run_id = str(state.get("run_id", "pending"))
        try:
            output = function(state, deps)
            deps.repository.record_node_run(run_id, name, "completed", dict(state), output)
            return output
        except Exception as exc:
            deps.repository.record_node_run(run_id, name, "failed", dict(state), None, str(exc))
            raise

    return wrapped
