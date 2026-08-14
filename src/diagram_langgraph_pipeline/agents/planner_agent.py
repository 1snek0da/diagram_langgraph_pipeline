"""Research planning node."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..dependencies import AgentDependencies
from ..routing import TaskType, get_execution_plan


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


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    present_plan_fields = [field for field in PLAN_FIELDS if field in state]
    if not present_plan_fields:
        plan = get_execution_plan(state.get("task_type", TaskType.FULL))
        state = {
            **state,
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
    else:
        missing_plan_fields = [field for field in PLAN_FIELDS if field not in state]
        if "task_type" not in state:
            missing_plan_fields.append("task_type")
        if missing_plan_fields:
            raise ValueError(
                "Incomplete task execution plan; missing fields: "
                + ", ".join(missing_plan_fields)
            )
    enabled = [
        *state.get("required_nodes", []),
        *state.get("support_nodes", []),
        *state.get("optional_nodes", []),
    ]
    missing_inputs = [name for name in state["required_inputs"] if not state.get(name)]
    if missing_inputs:
        raise ValueError(f"Missing required task inputs: {', '.join(missing_inputs)}")
    requested_retry_tasks = state.get("review_result", {}).get("retry_tasks", [])
    if not isinstance(requested_retry_tasks, list):
        raise TypeError("review_result.retry_tasks must be a list")
    retry_tasks: list[str | dict[str, Any]] = []
    for index, task in enumerate(requested_retry_tasks):
        if isinstance(task, str):
            retry_tasks.append(task)
        elif isinstance(task, dict):
            if task.get("node") in enabled:
                retry_tasks.append(task)
        else:
            raise TypeError(
                f"review_result.retry_tasks[{index}] must be a string or dict"
            )
    return {
        "run_id": state.get("run_id") or str(uuid4()),
        "task_type": state["task_type"],
        "as_of_date": state.get("as_of_date"),
        "investment_horizon": state.get("investment_horizon", "medium"),
        "retry_count": int(state.get("retry_count", 0)),
        "max_retries": int(state.get("max_retries", 2)),
        "required_nodes": list(state["required_nodes"]),
        "support_nodes": list(state["support_nodes"]),
        "optional_nodes": list(state["optional_nodes"]),
        "skipped_nodes": list(state["skipped_nodes"]),
        "required_inputs": list(state["required_inputs"]),
        "required_outputs": list(state["required_outputs"]),
        "result_keys": list(state["result_keys"]),
        "conclusion_scope": state["conclusion_scope"],
        "planner_tasks": {
            "task_type": state["task_type"],
            "enabled_nodes": [
                name for name in enabled if name not in {"planner", "review", "report"}
            ],
            "retry_tasks": retry_tasks,
            "conclusion_scope": state["conclusion_scope"],
        },
    }
