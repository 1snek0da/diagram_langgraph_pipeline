from diagram_langgraph_pipeline.routing import TaskType
from diagram_langgraph_pipeline.ui.models import AnalysisRun, NodeView
from diagram_langgraph_pipeline.ui.pages.workflow import render

from .fakes import FakeGateway, FakeStreamlit


def running_run():
    return AnalysisRun(
        run_id="run-1",
        ticker="AAPL",
        task_type=TaskType.FUNDAMENTAL,
        status="running",
        created_at="2026-08-06T00:00:00Z",
        updated_at="2026-08-06T00:01:00Z",
    )


def test_workflow_refreshes_non_terminal_run_and_groups_node_roles():
    gateway = FakeGateway(
        run=running_run(),
        nodes=[
            NodeView(name="business", role="required", status="completed"),
            NodeView(name="marginal_change", role="optional", status="degraded"),
            NodeView(name="stock_technical", role="skipped", status="skipped"),
        ],
    )
    st = FakeStreamlit(buttons={"刷新状态": True})

    render(st, gateway, {"selected_run_id": "run-1"})

    assert gateway.get_run_calls == ["run-1"]
    assert "可选节点" in st.rendered_text
    assert "主动跳过" in st.rendered_text
    assert "失败" not in st.text_for("stock_technical")

