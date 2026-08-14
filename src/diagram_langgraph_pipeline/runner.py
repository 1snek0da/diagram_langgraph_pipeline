"""Public execution helper."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .dependencies import AgentDependencies
from .graph import build_research_graph
from .profiles import apply_run_profile
from .routing import TaskType, get_execution_plan
from .state import DiagramBasedResearchState


def run_research(
    initial_state: DiagramBasedResearchState,
    deps: AgentDependencies,
    *,
    checkpointer: Any = None,
    recursion_limit: int = 100,
) -> DiagramBasedResearchState:
    plan = get_execution_plan(initial_state.get("task_type", TaskType.FULL))
    prepared_state = apply_run_profile(initial_state)
    prepared_state.update(
        {
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
    )
    prepared_state.setdefault("run_id", str(uuid4()))
    bootstrap = getattr(deps.repository, "bootstrap_run", None)
    if callable(bootstrap):
        bootstrap(prepared_state)
    graph = build_research_graph(
        deps, task_type=plan.task_type, checkpointer=checkpointer
    )
    try:
        result = graph.invoke(prepared_state, {"recursion_limit": recursion_limit})
    except Exception as exc:
        mark_failed = getattr(deps.repository, "mark_run_failed", None)
        if callable(mark_failed):
            mark_failed(str(prepared_state["run_id"]), str(exc))
        raise
    persist_result = getattr(deps.repository, "save_analysis_result", None)
    if callable(persist_result):
        persist_result(result)
    return result
