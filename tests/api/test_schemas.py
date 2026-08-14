from datetime import date

import pytest
from pydantic import ValidationError

from diagram_langgraph_pipeline.api.schemas import CreateAnalysisRunRequest
from diagram_langgraph_pipeline.routing import TaskType


def test_create_request_maps_all_router_fields():
    request = CreateAnalysisRunRequest(
        ticker="aapl",
        task_type=TaskType.TECHNICAL,
        as_of_date=date(2026, 8, 6),
        report_days=70,
        technical_days=251,
        offline=True,
    )

    options = request.to_options("run-1")

    assert options.run_id == "run-1"
    assert options.ticker == "AAPL"
    assert options.task_type is TaskType.TECHNICAL
    assert options.as_of == date(2026, 8, 6)
    assert options.offline is True


@pytest.mark.parametrize("ticker", ["", "   "])
def test_create_request_rejects_blank_ticker(ticker):
    with pytest.raises(ValidationError):
        CreateAnalysisRunRequest(ticker=ticker, task_type="market")


def test_create_request_rejects_inverted_windows():
    with pytest.raises(ValidationError, match="technical_days"):
        CreateAnalysisRunRequest(ticker="AAPL", report_days=70, technical_days=20)


def test_create_request_rejects_conflicting_data_modes():
    with pytest.raises(ValidationError, match="offline and refresh"):
        CreateAnalysisRunRequest(ticker="AAPL", offline=True, refresh=True)

