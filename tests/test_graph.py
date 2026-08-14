import pytest

pytest.importorskip("langgraph")

from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.agents import planner_agent
from diagram_langgraph_pipeline.graph import build_research_graph
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider
from diagram_langgraph_pipeline.routing import TaskType, get_execution_plan


PLAN_FIELDS = (
    "required_nodes",
    "support_nodes",
    "optional_nodes",
    "skipped_nodes",
    "required_inputs",
    "required_outputs",
    "result_keys",
    "conclusion_scope",
)


def planner_state(task_type=TaskType.TECHNICAL):
    plan = get_execution_plan(task_type)
    state = {
        "task_type": plan.task_type.value,
        "required_nodes": list(plan.required_nodes),
        "support_nodes": list(plan.support_nodes),
        "optional_nodes": list(plan.optional_nodes),
        "skipped_nodes": list(plan.skipped_nodes),
        "required_inputs": list(plan.required_inputs),
        "required_outputs": list(plan.required_outputs),
        "result_keys": list(plan.result_keys),
        "conclusion_scope": plan.conclusion_scope,
    }
    state.update(
        {
            "ticker": "TEST",
            "industry_name": "Test Industry",
            "as_of_date": "2026-08-05",
            "investment_horizon": "medium",
        }
    )
    return state


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
    plan = get_execution_plan(TaskType.TECHNICAL)
    result = planner_agent.run(
        {"task_type": "technical", "ticker": "TEST", "as_of_date": "2026-08-05"},
        deps,
    )

    assert result["planner_tasks"] == {
        "task_type": "technical",
        "enabled_nodes": [
            name
            for name in plan.enabled_nodes
            if name not in {"planner", "review", "report"}
        ],
        "retry_tasks": [],
        "conclusion_scope": plan.conclusion_scope,
    }
    assert result["task_type"] == plan.task_type.value
    assert {field: result[field] for field in PLAN_FIELDS} == {
        "required_nodes": list(plan.required_nodes),
        "support_nodes": list(plan.support_nodes),
        "optional_nodes": list(plan.optional_nodes),
        "skipped_nodes": list(plan.skipped_nodes),
        "required_inputs": list(plan.required_inputs),
        "required_outputs": list(plan.required_outputs),
        "result_keys": list(plan.result_keys),
        "conclusion_scope": plan.conclusion_scope,
    }


def test_planner_preserves_string_retry_tasks_from_review():
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    state = planner_state()
    state["review_result"] = {"retry_tasks": ["补采：缺少技术指标"]}

    result = planner_agent.run(state, deps)

    assert result["planner_tasks"]["retry_tasks"] == ["补采：缺少技术指标"]


def test_planner_filters_structured_retry_tasks_outside_enabled_plan():
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    state = planner_state()
    state["review_result"] = {
        "retry_tasks": [
            {"node": "stock_technical", "reason": "refresh"},
            {"node": "business", "reason": "outside plan"},
        ]
    }

    result = planner_agent.run(state, deps)

    assert result["planner_tasks"]["retry_tasks"] == [
        {"node": "stock_technical", "reason": "refresh"}
    ]


@pytest.mark.parametrize("retry_tasks", [[42], "not-a-list"])
def test_planner_rejects_invalid_retry_task_types(retry_tasks):
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    state = planner_state()
    state["review_result"] = {"retry_tasks": retry_tasks}

    with pytest.raises(TypeError, match="retry_tasks"):
        planner_agent.run(state, deps)


@pytest.mark.parametrize("missing_field", PLAN_FIELDS)
def test_planner_rejects_each_partially_injected_plan_field(missing_field):
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    state = planner_state()
    state.pop(missing_field)

    with pytest.raises(ValueError, match=missing_field):
        planner_agent.run(state, deps)
