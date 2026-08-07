from datetime import date
from uuid import UUID

from fastapi.testclient import TestClient

from diagram_langgraph_pipeline.api.app import create_app


RUN_ID = "00000000-0000-0000-0000-000000000001"


class FakeJobs:
    def __init__(self, run_id=UUID(RUN_ID)):
        self.run_id = run_id

    def submit(self, request):
        return self.run_id

    def recover(self):
        return 0

    def shutdown(self):
        return None


class FakeRepository:
    def __init__(self, *, run=None, report=None, node_records=None, bars=None):
        self.run = run
        self.report = report
        self.node_records = node_records or []
        self.bars = bars or []
        self.list_filters = None

    def check_health(self):
        return {"ok": True}

    def get_run_record(self, run_id):
        return self.run

    def get_report_record(self, run_id):
        return self.report

    def list_node_records(self, run_id):
        return self.node_records

    def list_run_records(self, **filters):
        self.list_filters = filters
        return ([self.run] if self.run else []), (1 if self.run else 0)

    def get_market_bar_records(self, ticker, start_date, end_date):
        self.market_args = (ticker, start_date, end_date)
        return self.bars


def complete_run_record(task_type="technical"):
    return {
        "id": RUN_ID,
        "ticker": "AAPL",
        "industry_name": "Technology",
        "task_type": task_type,
        "status": "completed",
        "as_of_date": "2026-08-06",
        "investment_horizon": "medium",
        "created_at": "2026-08-06T00:00:00Z",
        "updated_at": "2026-08-06T00:01:00Z",
        "error_code": None,
        "error_summary": None,
    }


def client_for(repository, *, settings=None):
    return TestClient(
        create_app(
            repository=repository,
            job_service=FakeJobs(),
            settings=settings or {},
        )
    )


def test_submit_returns_202_and_poll_url():
    response = client_for(FakeRepository()).post(
        "/api/v1/analysis-runs",
        json={
            "ticker": "AAPL",
            "task_type": "technical",
            "as_of_date": "2026-08-06",
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "run_id": RUN_ID,
        "status": "pending",
        "poll_url": f"/api/v1/analysis-runs/{RUN_ID}",
    }


def test_validation_failure_uses_stable_error_envelope():
    response = client_for(FakeRepository()).post(
        "/api/v1/analysis-runs", json={"ticker": "   "}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["retryable"] is False


def test_task_catalog_uses_server_side_paid_provider_configuration():
    response = client_for(
        FakeRepository(), settings={"TUSHARE_TOKEN": "server-only-secret"}
    ).get("/api/v1/task-types")

    assert response.status_code == 200
    assert len(response.json()) == 5
    assert all(item["paid_sources_available"] is True for item in response.json())
    assert "server-only-secret" not in response.text


def test_get_run_and_missing_run():
    repository = FakeRepository(run=complete_run_record())

    response = client_for(repository).get(f"/api/v1/analysis-runs/{RUN_ID}")
    missing = client_for(FakeRepository()).get(
        f"/api/v1/analysis-runs/{RUN_ID}"
    )

    assert response.status_code == 200
    assert response.json()["run_id"] == RUN_ID
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_history_passes_bound_filters_and_pagination_to_repository():
    repository = FakeRepository(run=complete_run_record())

    response = client_for(repository).get(
        "/api/v1/analysis-runs",
        params={
            "ticker": "aapl",
            "task_type": "technical",
            "status": "completed",
            "date_from": "2026-08-01",
            "date_to": "2026-08-07",
            "limit": 20,
            "offset": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert repository.list_filters == {
        "ticker": "aapl",
        "task_type": "technical",
        "status": "completed",
        "date_from": date(2026, 8, 1),
        "date_to": date(2026, 8, 7),
        "limit": 20,
        "offset": 5,
    }


def test_nodes_include_actual_and_synthetic_router_records():
    run = complete_run_record(task_type="technical")
    repository = FakeRepository(
        run=run,
        node_records=[
            {
                "node_name": "stock_technical",
                "status": "completed",
                "attempt_no": 1,
                "started_at": None,
                "ended_at": None,
                "error_summary": None,
            }
        ],
    )

    response = client_for(repository).get(
        f"/api/v1/analysis-runs/{RUN_ID}/nodes"
    )

    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()["items"]}
    assert by_name["stock_technical"]["role"] == "required"
    assert by_name["stock_technical"]["status"] == "completed"
    assert by_name["planner"]["role"] == "support"
    assert by_name["planner"]["status"] == "pending"
    assert by_name["industry_report"] == {
        "name": "industry_report",
        "role": "skipped",
        "status": "skipped",
        "attempt_no": None,
        "started_at": None,
        "ended_at": None,
        "error_summary": None,
    }


def test_report_not_ready_returns_retryable_409():
    run = complete_run_record()
    run["status"] = "running"
    response = client_for(FakeRepository(run=run)).get(
        f"/api/v1/analysis-runs/{RUN_ID}/report"
    )

    assert response.status_code == 409
    assert response.json()["error"]["retryable"] is True


def test_report_response_never_exposes_server_path():
    repository = FakeRepository(
        run=complete_run_record(),
        report={
            "id": "report-id",
            "run_id": RUN_ID,
            "report_markdown": "# Report",
            "created_at": "2026-08-06T00:01:00Z",
        },
    )

    response = client_for(repository).get(
        f"/api/v1/analysis-runs/{RUN_ID}/report"
    )

    assert response.status_code == 200
    assert response.json()["report_markdown"] == "# Report"
    assert "path" not in response.text.lower()


def test_market_bars_are_returned_with_bound_dates():
    repository = FakeRepository(
        bars=[
            {
                "trade_date": "2026-08-06",
                "open": "1.0",
                "high": "2.0",
                "low": "0.5",
                "close": "1.5",
                "adj_close": "1.5",
                "volume": "100",
                "turnover_amount": None,
                "turnover_rate": None,
                "source": "yfinance",
            }
        ]
    )

    response = client_for(repository).get(
        "/api/v1/market-bars",
        params={
            "ticker": "aapl",
            "start_date": "2026-08-01",
            "end_date": "2026-08-06",
        },
    )

    assert response.status_code == 200
    assert response.json()["ticker"] == "AAPL"
    assert repository.market_args == (
        "AAPL",
        date(2026, 8, 1),
        date(2026, 8, 6),
    )
