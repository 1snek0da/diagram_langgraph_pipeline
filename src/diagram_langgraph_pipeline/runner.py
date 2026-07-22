"""Public execution helper."""

from __future__ import annotations

from typing import Any

from .dependencies import AgentDependencies
from .graph import build_research_graph
from .state import DiagramBasedResearchState


def run_research(
    initial_state: DiagramBasedResearchState,
    deps: AgentDependencies,
    *,
    checkpointer: Any = None,
    recursion_limit: int = 100,
) -> DiagramBasedResearchState:
    graph = build_research_graph(deps, checkpointer=checkpointer)
    return graph.invoke(initial_state, {"recursion_limit": recursion_limit})
