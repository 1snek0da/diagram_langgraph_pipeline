import pytest

pytest.importorskip("langgraph")

from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.agents import planner_agent
from diagram_langgraph_pipeline.graph import build_research_graph
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider
from diagram_langgraph_pipeline.routing import TaskType, get_execution_plan


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


@pytest.mark.parametrize("task_type", list(TaskType))
def test_graph_contains_exactly_the_selected_task_nodes(task_type):
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    graph = build_research_graph(deps, task_type=task_type)
    actual = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    assert actual == set(get_execution_plan(task_type).enabled_nodes)


def test_technical_graph_does_not_compile_research_or_market_nodes():
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    graph = build_research_graph(deps, task_type="technical")
    nodes = set(graph.get_graph().nodes)
    assert "stock_technical" in nodes
    assert "industry_report" not in nodes
    assert "business" not in nodes
    assert "sentiment" not in nodes
    assert "decision" not in nodes


def test_planner_legacy_direct_call_uses_authoritative_task_plan():
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    result = planner_agent.run(
        {"task_type": "technical", "ticker": "TEST", "as_of_date": "2026-08-05"},
        deps,
    )

    assert result["planner_tasks"] == {
        "task_type": "technical",
        "enabled_nodes": [
            name
            for name in get_execution_plan(TaskType.TECHNICAL).enabled_nodes
            if name not in {"planner", "review", "report"}
        ],
        "retry_tasks": [],
        "conclusion_scope": get_execution_plan(TaskType.TECHNICAL).conclusion_scope,
    }


def test_planner_does_not_fill_a_partially_injected_plan():
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))

    with pytest.raises(KeyError, match="required_inputs"):
        planner_agent.run({"required_nodes": ["stock_technical"]}, deps)
