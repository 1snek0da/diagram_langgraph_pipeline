from diagram_langgraph_pipeline.ui.pages.history import render

from .fakes import FakeGateway, FakeStreamlit


def test_history_sends_filters_to_gateway():
    gateway = FakeGateway(runs=[])
    st = FakeStreamlit(
        values={"证券代码": "AAPL", "任务类型": "technical", "状态": "completed"}
    )

    render(st, gateway, {})

    assert gateway.last_filters == {
        "ticker": "AAPL",
        "task_type": "technical",
        "status": "completed",
    }

