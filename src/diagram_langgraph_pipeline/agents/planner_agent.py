"""Research planning node."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..dependencies import AgentDependencies
from ..routing import TaskType, get_execution_plan


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    plan_fields = (
        "required_nodes",
        "support_nodes",
        "optional_nodes",
        "skipped_nodes",
        "required_inputs",
        "required_outputs",
        "result_keys",
        "conclusion_scope",
    )
    if not any(field in state for field in plan_fields):
        plan = get_execution_plan(state.get("task_type", TaskType.FULL))
        state = {
            **state,
            "task_type": plan.task_type.value,
            "required_nodes": list(plan.required_nodes),
            "support_nodes": list(plan.support_nodes),
            "optional_nodes": list(plan.optional_nodes),
            "required_inputs": list(plan.required_inputs),
            "conclusion_scope": plan.conclusion_scope,
        }
    enabled = [
        *state.get("required_nodes", []),
        *state.get("support_nodes", []),
        *state.get("optional_nodes", []),
    ]
    missing_inputs = [name for name in state["required_inputs"] if not state.get(name)]
    if missing_inputs:
        raise ValueError(f"Missing required task inputs: {', '.join(missing_inputs)}")
    retry_tasks = [
        task
        for task in state.get("review_result", {}).get("retry_tasks", [])
        if task.get("node") in enabled
    ]
    return {
        "run_id": state.get("run_id") or str(uuid4()),
        "as_of_date": state.get("as_of_date"),
        "investment_horizon": state.get("investment_horizon", "medium"),
        "retry_count": int(state.get("retry_count", 0)),
        "max_retries": int(state.get("max_retries", 2)),
        "planner_tasks": {
            "task_type": state["task_type"],
            "enabled_nodes": [
                name for name in enabled if name not in {"planner", "review", "report"}
            ],
            "retry_tasks": retry_tasks,
            "conclusion_scope": state["conclusion_scope"],
        },
    }
