"""Public execution helper."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .dependencies import AgentDependencies
from .graph import build_research_graph
from .profiles import apply_run_profile
from .state import DiagramBasedResearchState


def run_research(
    initial_state: DiagramBasedResearchState,
    deps: AgentDependencies,
    *,
    checkpointer: Any = None,
    recursion_limit: int = 100,
) -> DiagramBasedResearchState:
    prepared_state = apply_run_profile(initial_state)
    prepared_state.setdefault("run_id", str(uuid4()))
    bootstrap = getattr(deps.repository, "bootstrap_run", None)
    if callable(bootstrap):
        bootstrap(prepared_state)
    graph = build_research_graph(deps, checkpointer=checkpointer)
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
