from diagram_langgraph_pipeline.routing import TaskType
from diagram_langgraph_pipeline.ui.pages.new_analysis import render

from .fakes import FakeGateway, FakeStreamlit, five_task_views


def test_analysis_page_submits_selected_market_task():
    st = FakeStreamlit(
        submit=True,
        values={"任务类型": "market", "证券代码": "AAPL"},
    )
    gateway = FakeGateway(task_types=five_task_views())
    state = {}

    render(st, gateway, state)

    assert gateway.created_request.task_type is TaskType.MARKET
    assert gateway.created_request.ticker == "AAPL"
    assert state["selected_run_id"] == "run-created"


def test_analysis_page_uses_router_metadata_for_scope_preview():
    st = FakeStreamlit(
        submit=False,
        values={"任务类型": "fundamental"},
    )
    gateway = FakeGateway(task_types=five_task_views())

    render(st, gateway, {})

    rendered = " ".join(st.rendered_text)
    assert "business" in rendered
    assert "marginal_change" in rendered
    assert "stock_technical" in rendered

