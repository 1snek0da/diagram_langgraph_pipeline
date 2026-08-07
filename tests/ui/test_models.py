from datetime import date

import pytest
from pydantic import ValidationError

from diagram_langgraph_pipeline.routing import TaskType
from diagram_langgraph_pipeline.ui.models import AnalysisRequest, AnalysisRun


def test_analysis_request_accepts_all_router_tasks():
    for task_type in TaskType:
        request = AnalysisRequest(ticker="aapl", task_type=task_type)
        assert request.task_type is task_type
        assert request.ticker == "AAPL"


def test_analysis_request_rejects_blank_ticker_and_inverted_windows():
    with pytest.raises(ValidationError):
        AnalysisRequest(ticker="   ", task_type=TaskType.FULL)
    with pytest.raises(ValidationError, match="technical_days"):
        AnalysisRequest(ticker="AAPL", report_days=70, technical_days=20)


def test_analysis_models_are_immutable():
    request = AnalysisRequest(
        ticker="AAPL", task_type=TaskType.MARKET, as_of_date=date(2026, 8, 6)
    )
    run = AnalysisRun(
        run_id="run-1",
        ticker="AAPL",
        task_type=TaskType.MARKET,
        status="running",
        created_at="2026-08-06T00:00:00Z",
        updated_at="2026-08-06T00:01:00Z",
    )

    with pytest.raises(ValidationError):
        request.ticker = "MSFT"
    with pytest.raises(ValidationError):
        run.status = "completed"

