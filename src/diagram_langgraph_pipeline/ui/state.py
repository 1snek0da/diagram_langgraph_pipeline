"""Small Streamlit session-state helpers."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from .models import AnalysisRun


def initialize_ui_state(state: MutableMapping[str, Any]) -> None:
    state.setdefault("page", "workspace")
    state.setdefault("selected_run_id", None)
    state.setdefault("run_cache", {})


def save_run(state: MutableMapping[str, Any], run: AnalysisRun) -> None:
    cache = state.setdefault("run_cache", {})
    cache[run.run_id] = run
    state["selected_run_id"] = run.run_id


def current_run(state: MutableMapping[str, Any]) -> AnalysisRun | None:
    run_id = state.get("selected_run_id")
    if not run_id:
        return None
    return state.get("run_cache", {}).get(run_id)


def navigate(state: MutableMapping[str, Any], page: str) -> None:
    state["page"] = page
