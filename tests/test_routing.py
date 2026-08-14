import pytest

from diagram_langgraph_pipeline.routing import (
    ALL_NODE_NAMES,
    TaskType,
    get_execution_plan,
)


@pytest.mark.parametrize("task_type", list(TaskType))
def test_every_task_has_a_closed_execution_plan(task_type):
    plan = get_execution_plan(task_type)
    enabled = set(plan.enabled_nodes)
    classified = set(plan.required_nodes) | set(plan.support_nodes) | set(plan.optional_nodes)
    assert classified == enabled
    assert not (set(plan.required_nodes) & set(plan.support_nodes))
    assert not (set(plan.required_nodes) & set(plan.optional_nodes))
    assert not (set(plan.support_nodes) & set(plan.optional_nodes))
    assert set(plan.skipped_nodes) == set(ALL_NODE_NAMES) - enabled
    assert "planner" in enabled
    assert "research_join" in enabled
    assert "review" in enabled
    assert "report" in enabled
    for source, target in plan.edges:
        sources = source if isinstance(source, tuple) else (source,)
        assert set(sources) - {"__start__"} <= enabled
        assert target in enabled


def test_only_full_enables_decision():
    assert "decision" in get_execution_plan(TaskType.FULL).enabled_nodes
    for task_type in TaskType:
        if task_type is not TaskType.FULL:
            assert "decision" not in get_execution_plan(task_type).enabled_nodes


def test_fundamental_attempts_marginal_change_as_optional():
    plan = get_execution_plan("fundamental")
    assert "marginal_change" in plan.optional_nodes
    assert "company_valuation_result" in plan.required_outputs
    assert "stock_technical" in plan.skipped_nodes


def test_unknown_task_is_rejected():
    with pytest.raises(ValueError, match="Unsupported task type"):
        get_execution_plan("unknown")
