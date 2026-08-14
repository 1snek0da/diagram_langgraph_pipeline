from diagram_langgraph_pipeline.ui.models import AnalysisRun
from diagram_langgraph_pipeline.ui.pages.workspace import render
from diagram_langgraph_pipeline.routing import TaskType

from .fakes import FakeGateway, FakeStreamlit


def run(run_id, status):
    return AnalysisRun(
        run_id=run_id,
        ticker="AAPL",
        task_type=TaskType.TECHNICAL,
        status=status,
        created_at="2026-08-06T00:00:00Z",
        updated_at="2026-08-06T00:01:00Z",
    )


def test_workspace_metrics_count_terminal_states():
    st = FakeStreamlit()
    gateway = FakeGateway(
        runs=[
            run("1", "running"),
            run("2", "failed"),
            run("3", "interrupted"),
            run("4", "completed"),
            run("5", "degraded"),
        ]
    )

    render(st, gateway, {})

    metrics = dict(st.metrics)
    assert metrics["总运行"] == 5
    assert metrics["运行中"] == 1
    assert metrics["失败/中断"] == 2
    assert metrics["已完成"] == 2

