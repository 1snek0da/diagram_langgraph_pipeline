from diagram_langgraph_pipeline.routing import TaskType
from diagram_langgraph_pipeline.ui.models import AnalysisRun
from diagram_langgraph_pipeline.ui.state import (
    current_run,
    initialize_ui_state,
    navigate,
    save_run,
)


def sample_run(run_id="run-1"):
    return AnalysisRun(
        run_id=run_id,
        ticker="AAPL",
        task_type=TaskType.TECHNICAL,
        status="running",
        created_at="2026-08-06T00:00:00Z",
        updated_at="2026-08-06T00:01:00Z",
    )


def test_initialize_state_preserves_existing_navigation():
    state = {"page": "history"}

    initialize_ui_state(state)

    assert state["page"] == "history"
    assert state["selected_run_id"] is None
    assert state["run_cache"] == {}


def test_save_and_load_current_run_uses_id_and_view_cache():
    state = {}
    initialize_ui_state(state)
    run = sample_run()

    save_run(state, run)

    assert state["selected_run_id"] == "run-1"
    assert current_run(state) is run


def test_navigation_only_changes_page():
    state = {"selected_run_id": "run-1"}

    navigate(state, "report")

    assert state == {"selected_run_id": "run-1", "page": "report"}
